#!/usr/bin/env python3
import argparse
import json
import math
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

import yaml

from workbench_config import load_author_profile, resolve_font, workspace_path


@dataclass(frozen=True)
class Canvas:
    width: int = 608
    height: int = 352

    @classmethod
    def from_plan(cls, plan: dict) -> "Canvas":
        spec = plan.get("format", {})
        width, height = int(spec.get("width", 608)), int(spec.get("height", 352))
        if min(width, height) < 32 or width % 2 or height % 2:
            raise ValueError("Video canvas must use positive even dimensions >= 32")
        if int(spec.get("fps", 24)) != 24:
            raise ValueError("This episode builder supports 24 fps")
        return cls(width, height)

    @property
    def size(self) -> str:
        return f"{self.width}x{self.height}"

    def px(self, value: float) -> int:
        return max(1, round(value * min(self.width / 608, self.height / 352)))

    def offset(self, value: str) -> str:
        match = re.fullmatch(r"([+-]\d+)([+-]\d+)", value)
        if not match:
            raise ValueError(f"Expected signed pixel offset, got {value!r}")
        x, y = map(int, match.groups())
        return f"{round(x * self.width / 608):+d}{round(y * self.height / 352):+d}"


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def probe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def parse_timestamp(value: str) -> float:
    hours, minutes, rest = value.split(":")
    seconds, milliseconds = rest.split(",")
    return int(hours) * 3600 + int(minutes) * 60 + int(seconds) + int(milliseconds) / 1000


def strip_line_end_punctuation(text: str) -> str:
    return re.sub(r"[，。；：、！？,.!?;:]+$", "", text.strip())


def parse_srt(path: Path) -> list[tuple[float, float, str]]:
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8-sig").strip())
    cues = []
    for block in blocks:
        lines = block.splitlines()
        if len(lines) < 3:
            continue
        match = re.match(r"(.+?)\s+-->\s+(.+)", lines[1])
        if not match:
            continue
        text = "\n".join(lines[2:]).strip()
        cues.append((parse_timestamp(match.group(1)), parse_timestamp(match.group(2)), text))
    return cues


def normalize_cues(cues: list[tuple[float, float, str]]) -> list[tuple[float, float, str]]:
    normalized = []
    previous_end = 0.0
    for start, end, text in cues:
        start = max(start, previous_end)
        if end <= start:
            continue
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines or len(lines) > 2 or any(len(line) > 20 for line in lines):
            raise SystemExit(f"Subtitle layout must be final in SRT: {text!r}")
        if any(strip_line_end_punctuation(line) != line for line in lines):
            raise SystemExit(f"Subtitle line has trailing punctuation: {text!r}")
        normalized.append((start, end, "\n".join(lines)))
        previous_end = end
    return normalized


def load_visual_timeline(plan: Path, candidates: Path) -> list[dict]:
    data = yaml.safe_load(plan.read_text(encoding="utf-8"))
    timeline = data.get("visual_timeline") or []
    if not timeline:
        raise SystemExit(f"No visual_timeline entries found in {plan}")

    resolved = []
    previous_end = 0.0
    for index, item in enumerate(timeline, 1):
        start = float(item["start"])
        end = float(item["end"])
        if abs(start - previous_end) > 0.002:
            raise SystemExit(
                f"Timeline segment {index} is not contiguous: "
                f"expected {previous_end:.3f}, got {start:.3f}"
            )
        if end <= start:
            raise SystemExit(f"Timeline segment {index} has invalid range {start:.3f}-{end:.3f}")
        source = candidates / item["source"]
        if not source.is_file():
            raise SystemExit(f"Timeline source does not exist: {source}")
        resolved.append(
            {
                **item,
                "start": start,
                "end": end,
                "duration": end - start,
                "source_start": float(item.get("source_start", 0.0)),
                "source_end": float(item["source_end"]) if "source_end" in item else None,
                "source_path": source,
            }
        )
        previous_end = end
    return resolved


def validate_visual_timeline(
    timeline: list[dict], cues: list[tuple[float, float, str]], audio_duration: float
) -> None:
    if abs(timeline[-1]["end"] - audio_duration) > 0.300:
        raise SystemExit(
            f"Timeline ends at {timeline[-1]['end']:.3f}s but audio is {audio_duration:.3f}s"
        )
    # Visual rhythm is related to narration, but it no longer has to mirror each
    # subtitle boundary. Contiguity is validated while loading the timeline.


def build_visual_base(timeline: list[dict], audio_duration: float, target: Path, canvas: Canvas = Canvas()) -> None:
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "2"]
    for segment in timeline:
        command += ["-i", str(segment["source_path"])]

    filters = []
    for index, segment in enumerate(timeline):
        source_duration = probe_duration(segment["source_path"])
        source_start = segment["source_start"]
        source_end = segment["source_end"] or source_duration
        target_duration = segment["duration"]
        if source_start < 0 or source_start >= source_duration or source_end <= source_start:
            raise SystemExit(
                f"Invalid source range {source_start:.3f}-{source_end:.3f} "
                f"for {segment['source_path']} "
                f"({source_duration:.3f}s)"
            )
        available_duration = min(source_duration - source_start, source_end - source_start)
        usable_duration = min(target_duration, available_duration)
        speed_factor = target_duration / usable_duration
        filters.append(
            f"[{index}:v]trim=start={source_start:.3f}:duration={usable_duration:.3f},"
            f"setpts=(PTS-STARTPTS)*{speed_factor:.9f},"
            f"scale={canvas.width}:{canvas.height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={canvas.width}:{canvas.height}:(ow-iw)/2:(oh-ih)/2:color=0xf5f1e8,setsar=1,fps=24,format=yuv420p,"
            f"trim=duration={target_duration:.3f},setpts=PTS-STARTPTS[v{index}]"
        )
    inputs = "".join(f"[v{index}]" for index in range(len(timeline)))
    filters.append(f"{inputs}concat=n={len(timeline)}:v=1:a=0[sequence]")
    target_duration = audio_duration + 0.45
    filters.append(
        f"[sequence]tpad=stop_mode=clone:stop_duration=1,trim=duration={target_duration:.3f},"
        f"setpts=PTS-STARTPTS[video]"
    )
    command += [
        "-filter_complex",
        ";".join(filters),
        "-map",
        "[video]",
        "-an",
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-pix_fmt",
        "yuv420p",
        str(target),
    ]
    run(command)


def make_text_overlay(text: str, font: Path, target: Path, point_size: int, gravity: str, offset: str,
                      text_color: str = "white", outline_color: str = "#252525", canvas: Canvas = Canvas()) -> None:
    run(
        [
            "magick",
            "-size",
            canvas.size,
            "xc:none",
            "-gravity",
            gravity,
            "-font",
            str(font),
            "-pointsize",
            str(canvas.px(point_size)),
            "-interline-spacing",
            str(canvas.px(4)),
            "-fill",
            text_color,
            "-stroke",
            outline_color,
            "-strokewidth",
            str(canvas.px(3)),
            "-annotate",
            canvas.offset(offset),
            text,
            "-stroke",
            "none",
            "-fill",
            text_color,
            "-annotate",
            canvas.offset(offset),
            text,
            str(target),
        ]
    )


def build_subtitle_video(
    cues: list[tuple[float, float, str]],
    font: Path,
    audio_duration: float,
    work_dir: Path,
    target: Path,
    annotations: list[dict] | None = None,
    canvas: Canvas = Canvas(),
    cue_offsets: dict | None = None,
) -> list[tuple[float, float, str]]:
    offsets = {}
    for key, value in (cue_offsets or {}).items():
        index = int(key)
        if str(index) != str(key) or not 1 <= index <= len(cues) or index in offsets:
            raise ValueError(f"Invalid subtitle cue offset index: {key}")
        canvas.offset(value)
        offsets[index] = value
    cue_dir = work_dir / "subtitle_frames"
    cue_dir.mkdir(parents=True, exist_ok=True)
    blank = cue_dir / "blank.png"
    run(["magick", "-size", canvas.size, "xc:none", f"PNG32:{blank}"])
    cue_paths = []
    for index, (start, end, text) in enumerate(cues, 1):
        cue_path = cue_dir / f"cue-{index:03d}.png"
        make_text_overlay(text, font, cue_path, 18, "south", offsets.get(index, "+0+16"), canvas=canvas)
        cue_paths.append(cue_path)

    overlay_ranges = [(start, end) for start, end, _ in cues]
    for index, annotation in enumerate(annotations or [], 1):
        start, end = float(annotation["start"]), float(annotation["end"])
        text = annotation["text"].strip()
        if not (0 <= start < end <= audio_duration + 0.001):
            raise ValueError(f"Invalid annotation range: {annotation}")
        if not text or len(text.splitlines()) > 2 or any(len(line) > 20 for line in text.splitlines()):
            raise ValueError(f"Annotation does not fit the video: {text!r}")
        annotation_path = cue_dir / f"annotation-{index:03d}.png"
        make_text_overlay(text, font, annotation_path, 17, "northwest", annotation.get("offset", "+16+16"),
                          "#24404A", "white", canvas=canvas)
        cue_paths.append(annotation_path)
        overlay_ranges.append((start, end))

    duration = audio_duration + 0.45
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-filter_complex_threads", "2",
        "-loop", "1", "-framerate", "24", "-t", f"{duration:.3f}", "-i", str(blank),
    ]
    for cue_path in cue_paths:
        command += [
            "-loop", "1", "-framerate", "24", "-t", f"{duration:.3f}", "-i", str(cue_path)
        ]
    filters = ["[0:v]format=rgba[base]"]
    previous = "base"
    for index, (start, end) in enumerate(overlay_ranges, 1):
        output = f"caption{index}"
        filters.append(
            f"[{previous}][{index}:v]overlay=shortest=0:"
            f"enable='between(t,{start:.3f},{end:.3f})'[{output}]"
        )
        previous = output
    filters.append(f"[{previous}]fps=24,format=rgba[subtitles]")
    command += [
        "-filter_complex", ";".join(filters), "-map", "[subtitles]", "-an", "-t",
        f"{duration:.3f}", "-c:v", "qtrle", str(target),
    ]
    run(command)
    return cues


def make_brand(font: Path, target: Path, text: str, canvas: Canvas = Canvas()) -> None:
    if not text:
        run(["magick", "-size", canvas.size, "xc:none", f"PNG32:{target}"])
        return
    run(
        [
            "magick",
            "-size",
            canvas.size,
            "xc:none",
            "-gravity",
            "northeast",
            "-font",
            str(font),
            "-pointsize",
            str(canvas.px(15)),
            "-fill",
            "#214F55",
            "-stroke",
            "white",
            "-strokewidth",
            str(canvas.px(2)),
            "-annotate",
            canvas.offset("+14+10"),
            text,
            "-stroke",
            "none",
            "-fill",
            "#214F55",
            "-annotate",
            canvas.offset("+14+10"),
            text,
            f"PNG32:{target}",
        ]
    )


def make_avatar(source: Path, target: Path, canvas: Canvas = Canvas()) -> None:
    side = canvas.px(108)
    size = f"{side}x{side}"
    crop = target.with_name("avatar-crop.png")
    mask = target.with_name("avatar-mask.png")
    run(
        [
            "magick",
            str(source),
            "-resize",
            size + "^",
            "-gravity",
            "center",
            "-extent",
            size,
            str(crop),
        ]
    )
    run(
        [
            "magick",
            "-size",
            size,
            "xc:none",
            "-fill",
            "white",
            "-stroke",
            "#2F777C",
            "-strokewidth",
            str(canvas.px(4)),
            "-draw",
            f"circle {side/2},{side/2} {side/2},{canvas.px(3)}",
            str(mask),
        ]
    )
    run(["magick", str(crop), str(mask), "-alpha", "off", "-compose", "CopyOpacity", "-composite", str(target)])


def build_final(
    visual: Path,
    subtitles: Path,
    brand: Path,
    avatar: Path,
    audio: Path,
    bgm: Path | None,
    audio_duration: float,
    avatar_enable_expression: str,
    target: Path,
    mix: dict,
    canvas: Canvas = Canvas(),
) -> None:
    command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-filter_complex_threads", "2",
            "-i",
            str(visual),
            "-i",
            str(subtitles),
            "-loop",
            "1",
            "-framerate",
            "24",
            "-i",
            str(brand),
            "-loop",
            "1",
            "-framerate",
            "24",
            "-i",
            str(avatar),
            "-i",
            str(audio),
        ]
    if bgm:
        command += ["-i", str(bgm)]
    audio_filter = "[4:a]apad=pad_dur=0.45"
    if bgm:
        audio_filter += ",asplit=2[narration_sc][narration_mix]"
        bgm_start = max(0.0, audio_duration - mix["fade_out_seconds"])
        audio_filter += (
            f";[5:a]atrim=duration={audio_duration + 0.45:.3f},"
            f"volume={mix['gain_db']:.6f}dB,"
            f"afade=t=in:st=0:d={mix['fade_in_seconds']},"
            f"afade=t=out:st={bgm_start:.3f}:d={mix['fade_out_seconds']}[bgm]"
            ";[bgm][narration_sc]sidechaincompress="
            "threshold=0.025:ratio=8:attack=25:release=300:makeup=1:mix=1[ducked]"
            ";[narration_mix][ducked]amix=inputs=2:duration=first:dropout_transition=2:normalize=0,"
            "aresample=22050,pan=mono|c0=c0[mixed]"
        )
    else:
        audio_filter += ",aresample=22050,pan=mono|c0=c0[mixed]"
    command += [
            "-filter_complex",
            (
                "[0:v][1:v]overlay=shortest=1[v1];"
                "[v1][2:v]overlay=shortest=1[v2];"
                f"[v2][3:v]overlay="
                f"x='if(gte(t,3.2),{round(482*canvas.width/608)},{round(18*canvas.width/608)})':"
                f"y='if(gte(t,3.2),{round(32*canvas.height/352)},{round(18*canvas.height/352)})':"
                f"enable='{avatar_enable_expression}'[video];"
                + audio_filter
            ),
            "-map",
            "[video]",
            "-map",
            "[mixed]",
            "-t",
            f"{audio_duration + 0.45:.3f}",
            "-c:v",
            "libx264",
            "-preset",
            "slow",
            "-crf",
            "18",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-ar",
            "22050",
            "-ac",
            "1",
            "-movflags",
            "+faststart",
            str(target),
        ]
    run(command)


def audio_mean_db(path: Path, duration: float) -> float:
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-i", str(path), "-t", str(duration),
         "-af", "volumedetect", "-vn", "-f", "null", "-"],
        check=True, capture_output=True, text=True,
    )
    match = re.search(r"mean_volume:\s*(-?[0-9.]+) dB", result.stderr)
    if not match:
        raise ValueError(f"Cannot measure audio level: {path}")
    return float(match.group(1))


def resolve_mix(config: dict, audio: Path, bgm: Path | None, duration: float) -> dict:
    mix = {key: float(config.get(key, default)) for key, default in
           (("fade_in_seconds", 1.2), ("fade_out_seconds", 2.5))}
    if any(not math.isfinite(value) or value < 0 for value in mix.values()):
        raise ValueError("Audio fades must be finite nonnegative seconds")
    levels = config.get("target_relative_level_db", [-24, -18])
    if len(levels) != 2 or not all(math.isfinite(float(x)) for x in levels) or not float(levels[0]) <= float(levels[1]) <= 0:
        raise ValueError("target_relative_level_db must be [low, high], low <= high <= 0")
    mix["target_relative_level_db"] = sum(map(float, levels)) / 2
    mix["gain_db"] = 0.0
    if bgm:
        mix["gain_db"] = audio_mean_db(audio, duration) - audio_mean_db(bgm, duration) + mix["target_relative_level_db"]
    return mix


def avatar_enable_expression(timeline: list[dict], brand_segments: set[str], audio_duration: float) -> str:
    if brand_segments:
        return "0"
    windows = [(0.0, min(3.2, audio_duration)), (max(0.0, audio_duration - 5.5), audio_duration + 0.45)]
    expressions = []
    for start, end in windows:
        overlaps_brand_character = any(
            item["segment_id"] in brand_segments
            and float(item["start"]) < end
            and float(item["end"]) > start
            for item in timeline
        )
        if not overlaps_brand_character and end > start:
            expressions.append(f"between(t,{start:.3f},{end:.3f})")
    return "+".join(expressions) or "0"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidates", type=Path, required=True)
    parser.add_argument("--audio", type=Path, required=True)
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--no-bgm", action="store_true")
    parser.add_argument("--author-profile", type=Path)
    parser.add_argument("--series")
    parser.add_argument("--srt", type=Path, required=True)
    parser.add_argument("--font", type=Path)
    parser.add_argument("--avatar", type=Path)
    parser.add_argument("--no-avatar", action="store_true")
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args()

    author_path, author = load_author_profile(profile_path=args.author_profile, series_id=args.series)
    plan_data = yaml.safe_load(args.plan.read_text(encoding="utf-8"))
    canvas = Canvas.from_plan(plan_data)
    plan_author = plan_data.get("delivery", {}).get("author_profile")
    if plan_author and plan_author != author["profile_id"]:
        raise ValueError(f"Plan author {plan_author!r} differs from selected author {author['profile_id']!r}")
    args.font = resolve_font(args.font)
    brand_config = author.get("brand", {})
    mix_config = author.get("audio_mix", {})
    if args.avatar is None and brand_config.get("avatar_source"):
        args.avatar = workspace_path(brand_config["avatar_source"])
    if args.no_avatar or brand_config.get("avatar_usage") == "disabled":
        args.avatar = None
    if args.bgm is None and mix_config.get("background_music"):
        args.bgm = workspace_path(mix_config["background_music"])
    if args.no_bgm:
        args.bgm = None
    brand_text = str(brand_config.get("overlay_text", "")) if brand_config.get("enabled", True) else ""

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.work_dir.mkdir(parents=True, exist_ok=True)
    audio_duration = probe_duration(args.audio)
    timeline = load_visual_timeline(args.plan, args.candidates)
    brand_segments = set(plan_data.get("director_contract", {}).get("brand_character_segments", []))
    avatar_expression = avatar_enable_expression(timeline, brand_segments, audio_duration)
    mix = resolve_mix(mix_config, args.audio, args.bgm, audio_duration)
    cues = normalize_cues(parse_srt(args.srt))
    validate_visual_timeline(timeline, cues, audio_duration)

    visual = args.work_dir / "visual-base.mp4"
    subtitle_video = args.work_dir / "subtitles.mov"
    brand = args.work_dir / "brand.png"
    avatar = args.work_dir / "avatar.png"
    build_visual_base(timeline, audio_duration, visual, canvas)
    annotations = plan_data.get("visual_annotations", [])
    cue_offsets = plan_data.get("subtitles", {}).get("cue_offsets", {})
    cues = build_subtitle_video(cues, args.font, audio_duration, args.work_dir, subtitle_video,
                               annotations, canvas, cue_offsets)
    make_brand(args.font, brand, brand_text, canvas)
    if args.avatar:
        make_avatar(args.avatar, avatar, canvas)
    else:
        run(["magick", "-size", f"{canvas.px(108)}x{canvas.px(108)}", "xc:none", f"PNG32:{avatar}"])
        avatar_expression = "0"
    build_final(
        visual, subtitle_video, brand, avatar, args.audio, args.bgm, audio_duration,
        avatar_expression, args.output, mix, canvas,
    )

    manifest = {
        "format": {"width": canvas.width, "height": canvas.height, "fps": 24},
        "overlay_coordinate_space": "608x352_scaled_to_canvas",
        "author_profile": author["profile_id"],
        "author_profile_path": str(author_path),
        "brand_text": brand_text,
        "audio_mix": mix,
        "visual_timeline": [
            {
                "segment_id": item["segment_id"],
                "start": item["start"],
                "end": item["end"],
                "duration": item["duration"],
                "source": str(item["source_path"]),
                "source_start": item["source_start"],
                "source_end": item["source_end"],
                "shot_type": item.get("shot_type"),
                "topic_relation": item.get("topic_relation", item.get("purpose")),
            }
            for item in timeline
        ],
        "audio_duration_seconds": audio_duration,
        "bgm": str(args.bgm) if args.bgm else None,
        "avatar_overlay_expression": avatar_expression,
        "final_duration_seconds": probe_duration(args.output),
        "normalized_subtitle_cues": [
            {"start": start, "end": end, "text": text} for start, end, text in cues
        ],
        "visual_annotations": annotations,
        "subtitle_cue_offsets": cue_offsets,
    }
    (args.work_dir / "build-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
