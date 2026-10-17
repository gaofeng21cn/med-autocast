#!/usr/bin/env python3
"""Build technical QA reports and review contact sheets for finished episodes."""

import argparse
import difflib
import hashlib
import json
import re
import subprocess
from pathlib import Path

import yaml

from delivery_contract import animation_gate
from workbench_config import load_workbench, production_root_for, resolve_font, series_paths, workspace_path


EPISODE_RE = re.compile(r"^(?:e)?(\d{2})_(.+)$", re.IGNORECASE)
TRAILING_PUNCTUATION_RE = re.compile(r"[，。；：、！？,.!?;:]+$")
ALIGNMENT_IGNORED_RE = re.compile(r"[\s，。；：、！？,.!?;:、“”‘’（）()《》<>\-�]+")


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def alignment_text(text: str) -> str:
    return ALIGNMENT_IGNORED_RE.sub("", text).upper()


def parse_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, milliseconds = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def parse_srt(path: Path) -> list[dict]:
    cues = []
    for block in re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip()):
        lines = block.splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = [part.strip() for part in lines[1].split("-->")]
        cues.append(
            {
                "start": parse_timestamp(start),
                "end": parse_timestamp(end),
                "lines": lines[2:],
            }
        )
    return cues


def paper_cues(score: dict) -> list[dict]:
    """Return Score captions in the same shape as parsed SRT cues.

    Paper-theatre projects keep captions in ``score.json`` because the Canvas
    player and the renderer share that timeline.  Do not write a synthetic SRT
    just to satisfy the legacy QA path; retaining the source makes the report
    explicit about where the captions came from.
    """
    return [
        {
            "start": float(cue["start"]),
            "end": float(cue["end"]),
            "lines": str(cue.get("text", "")).splitlines() or [""],
        }
        for cue in score.get("cues", [])
        if "start" in cue and "end" in cue
    ]


def paper_project_candidates(episode_dir: Path) -> list[Path]:
    """Find paper-theatre project roots without guessing an old YAML plan."""
    direct = episode_dir / "project.json"
    candidates = [direct] if direct.is_file() else []
    if not candidates:
        candidates = sorted(
            child / "project.json"
            for child in episode_dir.iterdir()
            if child.is_dir() and (child / "project.json").is_file()
        )
    return [path.parent for path in candidates]


def registered_paper_projects(series_id: str | None, production_root: Path | None = None) -> dict[str, Path]:
    """Read explicit current project pointers when the workbench has them.

    Version-directory discovery remains a fallback for relocated workspaces;
    the registry pointer wins whenever it exists.
    """
    try:
        workbench = load_workbench()
    except (OSError, ValueError):
        return {}
    if not series_id and production_root is not None:
        matches = [key for key, row in workbench.get("series", {}).items()
                   if workspace_path(row.get("production_root", f"productions/{key}")).resolve() == production_root.resolve()]
        series_id = matches[0] if len(matches) == 1 else None
    if not series_id:
        return {}
    series = workbench.get("series", {}).get(series_id, {})
    projects = {}
    for episode_id, entry in (series.get("episodes") or {}).items():
        if isinstance(entry, dict) and entry.get("project"):
            projects[episode_id] = workspace_path(entry["project"])
    return projects


def select_paper_project(episode_dir: Path, registered: dict[str, Path]) -> Path | None:
    """Resolve a current paper project while preserving Progress First.

    A registered pointer is authoritative.  An unregistered directory with a
    single project can still be inspected.  Multiple versions need an explicit
    pointer; a version sort must not silently choose the evidence under review.
    """
    registered_path = registered.get(episode_dir.name)
    if registered_path:
        if not (registered_path / "project.json").is_file():
            raise ValueError("当前 project 指针失效，不能静默改读历史版本：" + str(registered_path))
        return registered_path
    candidates = paper_project_candidates(episode_dir)
    if not candidates:
        return None
    if len(candidates) > 1:
        raise ValueError("多个纸剧场修订，请用 --series 读取 workbench.yaml 的当前 project 指针：" + str(episode_dir))
    return candidates[0]


def read_paper_project(project_dir: Path) -> tuple[dict, dict, dict | None]:
    config = json.loads((project_dir / "project.json").read_text(encoding="utf-8"))
    if config.get("schema") != "paper_project/v1":
        raise ValueError(f"不是纸剧场项目：{project_dir / 'project.json'}")
    score = json.loads((project_dir / config.get("score", "score.json")).read_text(encoding="utf-8"))
    current_path = project_dir / "out/current.json"
    current = json.loads(current_path.read_text(encoding="utf-8")) if current_path.is_file() else None
    return config, score, current


def paper_format(project_dir: Path, score: dict) -> dict:
    """Read the actual Canvas dimensions from the project entry when present."""
    width, height = 1280, 720
    entry = project_dir / "index.html"
    if entry.is_file():
        html = entry.read_text(encoding="utf-8", errors="replace")
        canvas = re.search(r"<canvas\b[^>]*>", html, re.IGNORECASE)
        if canvas:
            width_attr = re.search(r"\bwidth\s*=\s*[\"']?(\d+)", canvas.group(), re.IGNORECASE)
            height_attr = re.search(r"\bheight\s*=\s*[\"']?(\d+)", canvas.group(), re.IGNORECASE)
            if width_attr and height_attr:
                width, height = int(width_attr.group(1)), int(height_attr.group(1))
    return {"width": width, "height": height, "fps": int(score.get("fps", 24))}


def paper_plan(project_dir: Path, config: dict, score: dict, current: dict | None) -> dict:
    """Adapt paper-theatre Score data to the read-only parts of this QA tool."""
    shots = score.get("shots", [])
    return {
        "__paper_project": True,
        "__paper_project_dir": project_dir,
        "__paper_config": config,
        "__paper_score": score,
        "__paper_current": current,
        "format": paper_format(project_dir, score),
        "visual_timeline": [
            {
                "segment_id": shot["id"],
                "start": float(shot.get("start", 0.0)),
                "end": float(shot.get("end", 0.0)),
                "source": "paper_project://Canvas",
            }
            for shot in shots
            if shot.get("id")
        ],
        "subtitles": {
            "source": f"{config.get('score', 'score.json')}#/cues",
            "timing": "score_cues",
            "layout_owner": "paper_project_score",
        },
    }


def paper_inputs(project_dir: Path, config: dict, score: dict, current: dict | None) -> dict:
    beats_path = project_dir / "audio/narration_beats.json"
    beats = json.loads(beats_path.read_text(encoding="utf-8")) if beats_path.is_file() else None
    video = None
    if current and current.get("path"):
        video = Path(current["path"])
        if not video.is_absolute():
            video = project_dir / video
    return {
        "kind": "paper_project",
        "project": project_dir,
        "config": config,
        "score": score,
        "current": current,
        "video": video,
        "cues": paper_cues(score),
        "manifest": beats,
        "beats_path": beats_path if beats_path.is_file() else None,
    }


def paper_alignment_metrics(inputs: dict) -> dict:
    beats = (inputs.get("manifest") or {}).get("beats", [])
    cues = inputs.get("cues", [])
    approved = alignment_text("".join(str(beat.get("text", "")) for beat in beats))
    observed = alignment_text("".join("".join(cue["lines"]) for cue in cues))
    ratio = difflib.SequenceMatcher(None, approved, observed, autojunk=False).ratio() if approved else None
    return {
        "mode": "paper_score_cues_vs_narration_beats",
        "approved_caption_match_ratio": round(ratio, 6) if ratio is not None else None,
        "audio_recognition_performed": False,
        "narration_beats_available": bool(beats),
        "source": "audio/narration_beats.json + score.json#/cues",
    }


def paper_animation_gate(inputs: dict) -> dict:
    """Technical candidate gate for paper projects.

    This deliberately does not require the old visual manifest or mark a
    project release-eligible. Missing semantic/medical review is reported as a
    quality debt and remains visible to the caller.
    """
    project_dir = inputs["project"]
    config = inputs["config"]
    score = inputs["score"]
    current = inputs.get("current") or {}
    violations = []
    quality_debt = list(current.get("quality_debt", []))
    if not inputs.get("video") or not inputs["video"].is_file():
        violations.append("paper_render_missing_current_video")
    if not (project_dir / "dist/build-receipt.json").is_file():
        violations.append("paper_build_receipt_missing")
    if not score.get("shots"):
        violations.append("paper_score_missing_shots")
    if not score.get("cues"):
        violations.append("paper_score_missing_cues")
    score_path = project_dir / config.get("score", "score.json")
    binding_paths = {
        "sha256": inputs.get("video"),
        "score_sha256": score_path,
        "bundle_sha256": project_dir / "dist/film.js",
        "audio_sha256": project_dir / config.get("audio", "audio.wav"),
    }
    bindings = {}
    for key, path in binding_paths.items():
        declared = current.get(key)
        actual = sha256(path) if path is not None and path.is_file() else None
        status = "matched" if declared and actual and declared == actual else "missing" if not declared else "mismatch"
        bindings[key] = {"declared": declared, "actual": actual, "status": status}
        if status == "mismatch":
            violations.append("paper_render_binding_mismatch:" + key)
        elif status == "missing":
            quality_debt.append({
                "code": "paper_render_binding_missing:" + key,
                "blocks_stage_progress": False,
                "blocks_quality_export": True,
            })
    return {
        "status": "passed" if not violations else "failed",
        "candidate_class": "paper_theatre_js",
        "visual_style": (score.get("style") or {}).get("styleId") or config.get("style_id", "paper_collage"),
        "renderer": (score.get("style") or {}).get("renderer") or config.get("renderer_id", "canvas2d"),
        "manifest": None,
        "project": str(project_dir / "project.json"),
        "animated_segments": [shot.get("id") for shot in score.get("shots", []) if shot.get("id")],
        "static_segments": [],
        "violations": sorted(set(violations)),
        "semantic_review_required": True,
        "medical_review_required": True,
        "release_eligible": False,
        "current_release_eligible": current.get("release_eligible") is True,
        "render_bindings": bindings,
        "quality_debt": quality_debt,
    }


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def probe(path: Path) -> dict:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def image_mean(path: Path) -> float:
    result = subprocess.run(
        ["magick", "identify", "-format", "%[fx:mean]", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout)


def extract_frame(video: Path, timestamp: float, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{timestamp:.3f}",
            "-i", str(video), "-frames:v", "1", "-update", "1", str(target),
        ]
    )


def montage(frames: list[Path], target: Path, font: Path, columns: int = 4) -> None:
    if not frames:
        return
    run(
        [
            "magick", "montage", *[str(path) for path in frames], "-thumbnail", "304x176",
            "-tile", f"{columns}x", "-geometry", "+6+6", "-font", str(font),
            "-background", "#F5F3EF", str(target),
        ]
    )


def alignment_metrics(manifest: dict, alignment: dict) -> dict:
    alignment_by_id = {beat["id"]: beat for beat in alignment["beats"]}
    ratios = []
    coverages = []
    for beat in manifest["beats"]:
        aligned = alignment_by_id[beat["id"]]
        approved = alignment_text(beat["text"])
        observed = alignment_text(aligned["asr_text"])
        ratios.append(difflib.SequenceMatcher(None, approved, observed, autojunk=False).ratio())
        coverages.append(float(aligned["word_timing_coverage"]))
    return {
        "mode": "per_beat_whisper_word_alignment",
        "minimum_approved_asr_match_ratio": round(min(ratios), 6),
        "average_approved_asr_match_ratio": round(sum(ratios) / len(ratios), 6),
        "minimum_word_timing_coverage": round(min(coverages), 6),
    }


def episode_inputs(episode_dir: Path, plan: dict) -> dict:
    audio_root = (episode_dir / plan.get("audio", {}).get("source", "audio/local_voice/narration-normalized.wav")).parent
    if (audio_root / "narration_beats.json").is_file():
        return {
            "kind": "production_plan",
            "srt": episode_dir / plan.get("subtitles", {}).get("source", str((audio_root / "narration.srt").relative_to(episode_dir))),
            "manifest": audio_root / "narration_beats.json",
            "alignment": audio_root / "whisper-alignment.json",
            "approved_text": None,
            "legacy_whisper": None,
        }
    return {
        "kind": "production_plan",
        "srt": episode_dir / plan.get("subtitles", {}).get("source", str((audio_root / "narration_index.srt").relative_to(episode_dir))),
        "manifest": None,
        "alignment": None,
        "approved_text": episode_dir / "narration.txt",
        "legacy_whisper": episode_dir / "qa/whisper-index/index-tts25-narration.json",
    }


def legacy_alignment_metrics(approved_text: str, whisper_path: Path) -> dict:
    whisper = json.loads(whisper_path.read_text(encoding="utf-8"))
    approved = alignment_text(approved_text)
    observed = alignment_text(whisper["text"])
    words = [word for segment in whisper.get("segments", []) for word in segment.get("words", [])]
    timed_words = [word for word in words if "start" in word and "end" in word]
    return {
        "mode": "legacy_full_track_whisper_word_alignment",
        "approved_asr_match_ratio": round(
            difflib.SequenceMatcher(None, approved, observed, autojunk=False).ratio(), 6
        ),
        "word_timing_coverage": round(len(timed_words) / len(words), 6) if words else 0.0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--series")
    parser.add_argument("--font", type=Path)
    parser.add_argument("--episode", action="append")
    args = parser.parse_args()
    args.production_root = production_root_for(args.series, args.production_root)
    args.font = resolve_font(args.font)
    qa_path = series_paths(args.series)["technical_qa"] if args.series else args.production_root / "series-final-qa.json"
    registered = registered_paper_projects(args.series, args.production_root)

    selected = set(args.episode or [])
    series_reports = []
    series_frames = []
    failures = []
    for episode_dir in sorted(args.production_root.iterdir()):
        match = EPISODE_RE.match(episode_dir.name)
        if not match or (selected and episode_dir.name not in selected):
            continue
        paper_dir = select_paper_project(episode_dir, registered)
        if paper_dir:
            config, score, current = read_paper_project(paper_dir)
            plan = paper_plan(paper_dir, config, score, current)
            inputs = paper_inputs(paper_dir, config, score, current)
            video = inputs["video"]
            project_root = paper_dir
        else:
            plan = None
            inputs = None
            video = episode_dir / "final/video.mp4"
            project_root = episode_dir
        plan_path = episode_dir / "production_plan.yaml"
        if plan is None and not plan_path.is_file():
            failures.append({"episode": episode_dir.name, "missing_files": [str(plan_path)]})
            continue
        if plan is None:
            plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
            inputs = episode_inputs(episode_dir, plan)
        srt = inputs.get("srt")
        animation_report = (
            paper_animation_gate(inputs)
            if inputs.get("kind") == "paper_project"
            else animation_gate(episode_dir, plan)
        )
        if animation_report["status"] != "passed":
            report = {
                "episode_id": episode_dir.name,
                "status": (
                    "paper_project_technical_qa_blocked"
                    if inputs.get("kind") == "paper_project"
                    else "animation_generation_required"
                ),
                "delivery_class": (
                    "paper_theatre_candidate"
                    if inputs.get("kind") == "paper_project"
                    else "animatic_only"
                ),
                "video": str(video) if video else None,
                "animation_gate": animation_report,
                "technical_qa": (
                    "paper_project_inputs_need_repair"
                    if inputs.get("kind") == "paper_project"
                    else "not_run_until_animation_gate_passes"
                ),
                "release_eligible": False,
            }
            review_dir = project_root / "qa/final-review"
            review_dir.mkdir(parents=True, exist_ok=True)
            (review_dir / "technical-report.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
            series_reports.append(report)
            failures.append(
                {"episode": episode_dir.name, "animation_gate": animation_report["violations"]}
            )
            print(
                json.dumps(
                    {"episode": episode_dir.name, "status": report["status"]},
                    ensure_ascii=False,
                )
            )
            continue
        if inputs.get("kind") == "paper_project":
            required = [video, paper_dir / "project.json", paper_dir / plan["__paper_config"].get("score", "score.json")]
            required.extend(path for path in (inputs.get("beats_path"),) if path is not None)
        else:
            required = [video, srt, plan_path]
            required.extend(
                path
                for path in (
                    inputs["manifest"], inputs["alignment"], inputs["approved_text"], inputs["legacy_whisper"]
                )
                if path is not None
            )
        missing = [str(path) for path in required if not path.is_file()]
        if missing:
            failures.append({"episode": episode_dir.name, "missing_files": missing})
            continue

        review_dir = project_root / "qa/final-review"
        subtitle_dir = review_dir / "subtitle-frames"
        boundary_dir = review_dir / "boundary-frames"
        cues = inputs["cues"] if inputs.get("kind") == "paper_project" else parse_srt(srt)
        if inputs.get("kind") == "paper_project":
            manifest = inputs.get("manifest")
            approved_text = "".join(str(beat.get("text", "")) for beat in (manifest or {}).get("beats", []))
            alignment_report = paper_alignment_metrics(inputs)
        elif inputs["manifest"]:
            manifest = json.loads(inputs["manifest"].read_text(encoding="utf-8"))
            alignment = json.loads(inputs["alignment"].read_text(encoding="utf-8"))
            approved_text = "".join(beat["text"] for beat in manifest["beats"])
            alignment_report = alignment_metrics(manifest, alignment)
        else:
            approved_text = inputs["approved_text"].read_text(encoding="utf-8")
            alignment_report = legacy_alignment_metrics(approved_text, inputs["legacy_whisper"])

        subtitle_frames = []
        for index, cue in enumerate(cues, 1):
            midpoint = (cue["start"] + cue["end"]) / 2
            frame = subtitle_dir / f"cue-{index:03d}-{midpoint:07.3f}.png"
            extract_frame(video, midpoint, frame)
            subtitle_frames.append(frame)
        montage(subtitle_frames, review_dir / "subtitle-contact-sheet.png", args.font)

        boundary_frames = []
        for item in plan["visual_timeline"][1:]:
            boundary = float(item["start"])
            for suffix, offset in (("before", -0.08), ("after", 0.08)):
                frame = boundary_dir / f"{item['segment_id']}-{suffix}-{boundary:07.3f}.png"
                extract_frame(video, max(0.0, boundary + offset), frame)
                boundary_frames.append(frame)
        montage(boundary_frames, review_dir / "boundary-contact-sheet.png", args.font)
        sampled_frames = subtitle_frames + boundary_frames
        black_frames = [str(path) for path in sampled_frames if image_mean(path) < 0.08]

        media = probe(video)
        run(["ffmpeg", "-v", "error", "-i", str(video), "-f", "null", "-"])
        video_stream = next(stream for stream in media["streams"] if stream["codec_type"] == "video")
        audio_stream = next(stream for stream in media["streams"] if stream["codec_type"] == "audio")
        subtitle_text = "".join(line for cue in cues for line in cue["lines"])
        trailing = [line for cue in cues for line in cue["lines"] if TRAILING_PUNCTUATION_RE.search(line)]
        subtitle_violations = []
        paper_quality_debt = []
        if max(len(cue["lines"]) for cue in cues) > 2:
            subtitle_violations.append("more_than_two_lines")
        if inputs.get("kind") != "paper_project":
            if max(len(line) for cue in cues for line in cue["lines"]) > 20:
                subtitle_violations.append("line_longer_than_20_characters")
            if max(sum(len(line) for line in cue["lines"]) for cue in cues) > 30:
                subtitle_violations.append("cue_longer_than_30_characters")
        if trailing and inputs.get("kind") != "paper_project":
            subtitle_violations.append("trailing_punctuation")
        elif trailing:
            paper_quality_debt.append({
                "code": "paper_caption_trailing_punctuation",
                "blocks_stage_progress": False,
                "blocks_quality_export": False,
                "lines": trailing,
            })
        approved_text_matches = alignment_text(approved_text) == alignment_text(subtitle_text)
        if inputs.get("kind") == "paper_project" and not (manifest or {}).get("beats"):
            paper_quality_debt.append({
                "code": "paper_narration_beats_missing",
                "blocks_stage_progress": False,
                "blocks_quality_export": True,
                "source": "audio/narration_beats.json",
            })
        if not approved_text_matches:
            if inputs.get("kind") == "paper_project":
                # Score cues are the current Canvas caption source, while the
                # narration beat text remains the approved spoken source. Keep
                # the discrepancy visible without turning it into a hard
                # technical stop; semantic subtitle review owns this decision.
                paper_quality_debt.append({
                    "code": "paper_score_cues_do_not_match_narration",
                    "blocks_stage_progress": False,
                    "blocks_quality_export": True,
                    "source": "score.json#/cues vs audio/narration_beats.json",
                })
            else:
                subtitle_violations.append("approved_text_mismatch")

        media_violations = []
        actual_video = (
            video_stream["codec_name"], int(video_stream["width"]), int(video_stream["height"]),
            video_stream["avg_frame_rate"], video_stream["pix_fmt"],
        )
        canvas = plan.get("format", {})
        expected_video = ("h264", int(canvas.get("width", 608)), int(canvas.get("height", 352)),
                          f"{int(canvas.get('fps', 24))}/1", "yuv420p")
        if actual_video != expected_video:
            media_violations.append("unexpected_video_stream")
        actual_audio = (
            audio_stream["codec_name"], int(audio_stream["sample_rate"]), int(audio_stream["channels"]),
        )
        expected_audio = ("aac", 48000, 2) if inputs.get("kind") == "paper_project" else ("aac", 22050, 1)
        if actual_audio != expected_audio:
            media_violations.append("unexpected_audio_stream")
        technical_violations = (
            (["sampled_black_frames"] if black_frames else []) + subtitle_violations + media_violations
        )
        report = {
            "episode_id": episode_dir.name,
            "status": (
                (
                    "paper_project_technical_qa_passed_semantic_review_required"
                    if not technical_violations
                    else "paper_project_technical_qa_failed"
                )
                if inputs.get("kind") == "paper_project"
                else (
                    "delivery_qa_passed_visual_and_medical_review_required"
                    if not technical_violations
                    else "technical_qa_failed"
                )
            ),
            "delivery_class": "paper_theatre_candidate" if inputs.get("kind") == "paper_project" else "final_animation",
            "video": str(video),
            "sha256": sha256(video),
            "duration_seconds": round(float(media["format"]["duration"]), 6),
            "video_stream": {
                "codec": video_stream["codec_name"],
                "width": int(video_stream["width"]),
                "height": int(video_stream["height"]),
                "frame_rate": video_stream["avg_frame_rate"],
                "pixel_format": video_stream["pix_fmt"],
            },
            "audio_stream": {
                "codec": audio_stream["codec_name"],
                "sample_rate": int(audio_stream["sample_rate"]),
                "channels": int(audio_stream["channels"]),
            },
            "full_decode": "passed",
            "sampled_black_frame_violations": black_frames,
            "subtitles": {
                "cue_count": len(cues),
                "maximum_lines": max(len(cue["lines"]) for cue in cues),
                "maximum_characters_per_line": max(len(line) for cue in cues for line in cue["lines"]),
                "maximum_characters_per_cue": max(sum(len(line) for line in cue["lines"]) for cue in cues),
                "trailing_punctuation_violations": trailing,
                "approved_text_exact_after_normalization": approved_text_matches,
                "timing": plan["subtitles"].get("timing", plan["subtitles"].get("timing_source")),
                "layout_owner": plan["subtitles"].get("layout_owner", str(srt)),
                "violations": subtitle_violations,
            },
            "alignment": alignment_report,
            "animation_gate": animation_report,
            "media_violations": media_violations,
            "visual_segments": len(plan["visual_timeline"]),
            "source_kind": inputs.get("kind"),
            "release_eligible": False,
            "quality_debt": paper_quality_debt,
            "review_artifacts": {
                "subtitle_contact_sheet": str(review_dir / "subtitle-contact-sheet.png"),
                "boundary_contact_sheet": str(review_dir / "boundary-contact-sheet.png"),
            },
        }
        report_path = review_dir / "technical-report.json"
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        series_reports.append(report)
        if technical_violations:
            failures.append({"episode": episode_dir.name, "violations": technical_violations})

        representative = review_dir / "representative.png"
        extract_frame(video, float(media["format"]["duration"]) * 0.5, representative)
        series_frames.append(representative)
        print(json.dumps({"episode": episode_dir.name, "sha256": report["sha256"]}, ensure_ascii=False))

    montage(series_frames, args.production_root / "series-final-contact-sheet.png", args.font, columns=4)
    if selected and qa_path.is_file():
        previous = json.loads(qa_path.read_text(encoding="utf-8"))
        series_reports = [item for item in previous if item["episode_id"] not in selected] + series_reports
        series_reports.sort(key=lambda item: item["episode_id"])
    qa_path.parent.mkdir(parents=True, exist_ok=True)
    qa_path.write_text(
        json.dumps(series_reports, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if failures:
        raise SystemExit(f"Technical QA failed: {json.dumps(failures, ensure_ascii=False)}")


if __name__ == "__main__":
    main()
