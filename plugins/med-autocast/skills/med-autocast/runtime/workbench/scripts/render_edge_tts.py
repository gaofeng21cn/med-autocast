#!/usr/bin/env python3
"""Render approved narration with the local Edge TTS fallback voice."""

from __future__ import annotations

import argparse
import asyncio
import json
import shutil
import subprocess
import tempfile
from pathlib import Path
from audio_baseline import normalize, inspect_audio


def read_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError(f"Narration is empty: {path}")
    return text


def scene_intervals(text: str, boundaries: list[dict], duration: float) -> list[dict]:
    """Match paragraph text exactly; boundaries provide diagnostic intervals only."""
    paragraphs = [line.strip() for line in text.splitlines() if line.strip()]
    rows = []
    cursor = 0
    for index, paragraph in enumerate(paragraphs):
        combined = ""
        first = cursor
        while cursor < len(boundaries) and len(combined) < len(paragraph):
            combined += boundaries[cursor]["text"]
            cursor += 1
        if combined != paragraph:
            raise ValueError("Edge sentence text does not match narration paragraphs; alignment needs review")
        rows.append({"id": f"B{index + 1:02d}", "start": boundaries[first]["start"]})
    if cursor != len(boundaries):
        raise ValueError("Unmatched Edge sentence boundaries")
    for index, row in enumerate(rows):
        row["end"] = rows[index + 1]["start"] if index + 1 < len(rows) else duration
    return rows


async def synthesize(text: str, voice: str, target: Path, rate: str, pitch: str, volume: str) -> list[dict]:
    try:
        import edge_tts
    except ImportError as exc:
        raise SystemExit("Install the local fallback with: python3 -m pip install edge-tts") from exc
    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch, volume=volume,
                                      boundary="SentenceBoundary")
    boundaries = []
    with target.open("wb") as output:
        async for event in communicate.stream():
            if event["type"] == "audio":
                output.write(event["data"])
            elif event["type"] == "SentenceBoundary":
                boundaries.append({"text": event["text"], "start": event["offset"] / 10_000_000,
                                   "end": (event["offset"] + event["duration"]) / 10_000_000})
    return boundaries


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--text", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--voice", default="zh-CN-XiaoyiNeural")
    parser.add_argument("--rate", default="-8%")
    parser.add_argument("--pitch", default="+0Hz")
    parser.add_argument("--volume", default="+0%")
    args = parser.parse_args()
    if any(shutil.which(tool) is None for tool in ("ffmpeg", "ffprobe")):
        raise SystemExit("ffmpeg and ffprobe are required")
    if args.output.exists():
        raise SystemExit("Output already exists; use a new revision path")
    if args.output.suffix.lower() not in (".wav", ".mp3"):
        raise SystemExit("Output must be WAV or MP3")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    narration = read_text(args.text)
    with tempfile.TemporaryDirectory(prefix="edge-narration-") as temporary:
        raw = Path(temporary) / "raw.mp3"
        boundaries = asyncio.run(synthesize(narration, args.voice, raw, args.rate, args.pitch, args.volume))
        normalize(raw, args.output)
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(args.output)],
        check=True,
        capture_output=True,
        text=True,
    )
    duration = float(json.loads(probe.stdout)["format"]["duration"])
    try:
        intervals = scene_intervals(narration, boundaries, duration)
        alignment_error = None
    except ValueError as exc:
        intervals, alignment_error = [], str(exc)
    report = inspect_audio(args.output, intervals)
    report.update({"backend": "edge_tts_local", "source_text": str(args.text.resolve()),
        "submitted_text": narration, "synthesis_scope": "whole_narration_single_communicate",
        "baseline": {"voice": args.voice, "rate": args.rate, "pitch": args.pitch, "volume": args.volume,
                     "target_lufs": -16, "true_peak_limit_db": -1},
        "sentence_boundaries": boundaries, "alignment_review": "pending",
        "scene_measurement": "measured_from_unreviewed_boundaries" if intervals else "pending",
        "alignment_error": alignment_error})
    args.output.with_suffix(".receipt.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "rendered", "voice": args.voice, "output": str(args.output), "duration": round(duration, 3)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
