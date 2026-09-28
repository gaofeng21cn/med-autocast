#!/usr/bin/env python3
"""Measure narration loudness; acoustic checks never approve emotional tone."""
from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
from pathlib import Path


def measure(path: Path, start=None, end=None) -> dict:
    command = ["ffmpeg", "-hide_banner", "-nostats"]
    if start is not None:
        command += ["-ss", str(start), "-t", str(end - start)]
    command += ["-i", str(path), "-vn", "-af", "loudnorm=I=-16:TP=-1:LRA=7:print_format=json", "-f", "null", "-"]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    data, _ = json.JSONDecoder().raw_decode(result.stderr[result.stderr.rfind("{"):])
    return {key: float(data[key]) for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset")}


def normalize(source: Path, output: Path) -> dict:
    values = measure(source)
    if not all(math.isfinite(v) for v in values.values()):
        raise ValueError("Cannot normalize silent or invalid audio")
    filter_text = ("loudnorm=I=-16:TP=-1:LRA=7:linear=true:"
                   f"measured_I={values['input_i']}:measured_TP={values['input_tp']}:"
                   f"measured_LRA={values['input_lra']}:measured_thresh={values['input_thresh']}:"
                   f"offset={values['target_offset']}")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", filter_text,
                    "-ar", "24000", "-ac", "1", str(output)], check=True)
    return measure(output)


def inspect_audio(source: Path, beats: list[dict] | None = None) -> dict:
    metadata = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_entries",
        "format=duration", "-of", "json", str(source)], text=True))
    duration = float(metadata["format"]["duration"])
    rows = []
    previous = 0.0
    for beat in beats or []:
        start, end = float(beat["start"]), float(beat["end"])
        if not all(math.isfinite(v) for v in (start, end)) or start < previous - .002 or not 0 <= start < end <= duration + .05:
            raise ValueError("Invalid or overlapping narration beat interval")
        previous = end
        rows.append({"id": beat["id"], "start": start, "end": end, **measure(source, start, end)})
    finite = [row["input_i"] for row in rows if math.isfinite(row["input_i"])]
    center = statistics.median(finite) if finite else None
    flags = []
    for row in rows:
        if not math.isfinite(row["input_i"]):
            flags.append({"id": row["id"], "reason": "silent_or_unmeasurable"})
        elif abs(row["input_i"] - center) > 3:
            flags.append({"id": row["id"], "reason": "scene_loudness_outlier", "delta_lu": round(row["input_i"] - center, 2)})
    overall = measure(source)
    if not math.isfinite(overall["input_i"]) or abs(overall["input_i"] + 16) > 1 or overall["input_tp"] > -.8:
        flags.append({"reason": "outside_narration_loudness_target"})
    result = {"schema": "medical_narration_audio_qa/v1", "audio": str(source.resolve()),
              "duration": duration, "overall": overall, "scenes": rows, "flags": flags,
              "acoustic_status": "needs_audio_review" if flags else "passed",
              "scene_check": "measured" if rows else "not_measured",
              "full_listening": "pending", "tone_consistency": "pending",
              "note": "Loudness is not emotion. Review scene transitions and the full narration by listening."}
    # JSON must remain portable when silence produces an infinite measurement.
    def clean(value):
        if isinstance(value, float) and not math.isfinite(value): return None
        if isinstance(value, dict): return {k: clean(v) for k, v in value.items()}
        if isinstance(value, list): return [clean(v) for v in value]
        return value
    return clean(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--beats", type=Path)
    parser.add_argument("--report", required=True, type=Path)
    args = parser.parse_args()
    beats = json.loads(args.beats.read_text())["beats"] if args.beats else None
    report = inspect_audio(args.audio, beats)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False))


if __name__ == "__main__":
    main()
