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
from workbench_config import production_root_for, resolve_font, series_paths


EPISODE_RE = re.compile(r"^(\d{2})_(.+)$")
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
    audio_root = (episode_dir / plan.get("audio", {}).get("source", "audio/local_voice/index-tts25-narration.wav")).parent
    if (audio_root / "narration_beats.json").is_file():
        return {
            "srt": episode_dir / plan.get("subtitles", {}).get("source", str((audio_root / "narration.srt").relative_to(episode_dir))),
            "manifest": audio_root / "narration_beats.json",
            "alignment": audio_root / "whisper-alignment.json",
            "approved_text": None,
            "legacy_whisper": None,
        }
    return {
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

    selected = set(args.episode or [])
    series_reports = []
    series_frames = []
    failures = []
    for episode_dir in sorted(args.production_root.iterdir()):
        match = EPISODE_RE.match(episode_dir.name)
        if not match or (selected and episode_dir.name not in selected):
            continue
        video = episode_dir / "final/video.mp4"
        plan_path = episode_dir / "production_plan.yaml"
        if not plan_path.is_file():
            failures.append({"episode": episode_dir.name, "missing_files": [str(plan_path)]})
            continue
        plan = yaml.safe_load(plan_path.read_text(encoding="utf-8"))
        inputs = episode_inputs(episode_dir, plan)
        srt = inputs["srt"]
        animation_report = animation_gate(episode_dir, plan)
        if animation_report["status"] != "passed":
            report = {
                "episode_id": episode_dir.name,
                "status": "animation_generation_required",
                "delivery_class": "animatic_only",
                "video": None,
                "animation_gate": animation_report,
                "technical_qa": "not_run_until_animation_gate_passes",
            }
            review_dir = episode_dir / "qa/final-review"
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

        review_dir = episode_dir / "qa/final-review"
        subtitle_dir = review_dir / "subtitle-frames"
        boundary_dir = review_dir / "boundary-frames"
        cues = parse_srt(srt)
        if inputs["manifest"]:
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
        if max(len(cue["lines"]) for cue in cues) > 2:
            subtitle_violations.append("more_than_two_lines")
        if max(len(line) for cue in cues for line in cue["lines"]) > 20:
            subtitle_violations.append("line_longer_than_20_characters")
        if max(sum(len(line) for line in cue["lines"]) for cue in cues) > 30:
            subtitle_violations.append("cue_longer_than_30_characters")
        if trailing:
            subtitle_violations.append("trailing_punctuation")
        approved_text_matches = alignment_text(approved_text) == alignment_text(subtitle_text)
        if not approved_text_matches:
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
        if actual_audio != ("aac", 22050, 1):
            media_violations.append("unexpected_audio_stream")
        technical_violations = (
            (["sampled_black_frames"] if black_frames else []) + subtitle_violations + media_violations
        )
        report = {
            "episode_id": episode_dir.name,
            "status": (
                "delivery_qa_passed_visual_and_medical_review_required"
                if not technical_violations
                else "technical_qa_failed"
            ),
            "delivery_class": "final_animation",
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
