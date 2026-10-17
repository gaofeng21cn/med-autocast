#!/usr/bin/env python3
"""Compare every registered source take with its exact slice in narration.wav.

This is the narrow machine check for the historical ``lost first words`` bug.
It intentionally compares the pre-normalized PCM track: loudness normalization
may change sample values, but it must never change frame addresses or remove a
source take. It does not approve pronunciation, tone, or the final MP4.
"""
from __future__ import annotations

import argparse
import array
import hashlib
import json
import math
import subprocess
import wave
from datetime import datetime, timezone
from pathlib import Path


def sha(path: Path) -> str | None:
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def decode(path: Path, rate: int) -> array.array:
    payload = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-ar", str(rate),
        "-ac", "1", "-f", "s16le", "-",
    ])
    samples = array.array("h")
    samples.frombytes(payload)
    return samples


def inspect(project: Path) -> dict:
    receipt_path = project / "audio/narration_beats.json"
    raw_path = project / "audio/narration.wav"
    result = {"project": str(project), "flags": [], "beats": [],
              "status": "needs_repair", "source_takes_checked": 0,
              "generated_at": datetime.now(timezone.utc).isoformat(),
              "method": "exact decoded source PCM containment in raw narration",
              "note": (
                  "Exact PCM containment proves source samples were not cut from the raw splice; "
                  "it does not prove pronunciation, tone, listening, or final MP4 lineage."
              )}
    if not receipt_path.is_file() or not raw_path.is_file():
        result["flags"].append("missing_receipt_or_raw_narration")
        return result
    try:
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        result["flags"].append("unreadable_narration_receipt")
        return result
    if not isinstance(receipt, dict):
        result["flags"].append("invalid_narration_receipt")
        return result
    beats = receipt.get("beats")
    if not isinstance(beats, list) or not beats:
        result["flags"].append("missing_or_empty_beats")
        return result
    splice = receipt.get("splice") or {}
    if not isinstance(splice, dict) or splice.get("schema") != "narration_splice/v2":
        result["flags"].append("legacy_splice_receipt")
    rate = 24000
    try:
        with wave.open(str(raw_path), "rb") as handle:
            raw_rate = handle.getframerate()
            if handle.getnchannels() != 1 or handle.getsampwidth() != 2:
                result["flags"].append("raw_track_is_not_mono_s16_pcm")
                return result
            raw = array.array("h")
            raw.frombytes(handle.readframes(handle.getnframes()))
    except (OSError, wave.Error, EOFError):
        result["flags"].append("unreadable_raw_narration")
        return result
    if not raw:
        result["flags"].append("empty_raw_narration")
    if raw_rate != rate:
        result["flags"].append(f"unexpected_raw_sample_rate:{raw_rate}")
        rate = raw_rate
    previous_end = 0
    seen_ids = set()

    def record(row: dict) -> None:
        result["beats"].append(row)
        result["flags"].extend(f"{row.get('id') or '?'}:{flag}" for flag in row["flags"])

    for index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            record({"id": f"row_{index + 1}", "flags": ["invalid_beat_metadata"]})
            continue
        row = {"id": beat.get("id"), "flags": []}
        beat_id = str(beat.get("id") or "")
        if not beat_id or beat_id in seen_ids:
            row["flags"].append("missing_or_duplicate_beat_id")
        seen_ids.add(beat_id)
        try:
            start = float(beat["start"])
            end = float(beat["end"])
            if not math.isfinite(start) or not math.isfinite(end) or start < 0 or end <= start:
                raise ValueError("invalid range")
        except (KeyError, TypeError, ValueError, OverflowError):
            row["flags"].append("invalid_beat_time_range")
            record(row)
            continue
        source = Path(str(beat.get("audio", "")))
        if not source.is_absolute():
            source = project / source
        if not source.is_file():
            row["flags"].append("missing_source_take")
            record(row)
            continue
        try:
            source_samples = decode(source, rate)
        except (OSError, subprocess.CalledProcessError, ValueError):
            row["flags"].append("source_take_decode_failed")
            record(row)
            continue
        result["source_takes_checked"] += 1
        if not source_samples:
            row["flags"].append("empty_decoded_source_take")
        start_frame = round(start * rate)
        end_frame = round(end * rate)
        actual = raw[start_frame:end_frame]
        if start_frame < previous_end:
            row["flags"].append("beat_overlap")
        if end_frame - start_frame != len(source_samples):
            row["flags"].append("receipt_frame_count_differs_from_source")
        if actual != source_samples:
            # Report the first differing frame; a full waveform diff is not
            # useful in the season report and may be very large.
            limit = min(len(actual), len(source_samples))
            first = next((i for i in range(limit) if actual[i] != source_samples[i]), limit)
            row["flags"].append("raw_track_does_not_contain_exact_source_take")
            row["first_difference_frame"] = start_frame + first
        row.update({
            "source": str(source),
            "source_sha256": sha(source),
            "source_frames": len(source_samples),
            "start_frame": start_frame,
            "end_frame": end_frame,
            "head_trim_seconds": beat.get("trimmed_head_seconds", 0),
            "tail_trim_seconds": beat.get("trimmed_tail_seconds", 0),
        })
        record(row)
        previous_end = max(previous_end, end_frame)
    result["raw_sha256"] = sha(raw_path)
    result["beats_registered"] = len(beats)
    result["status"] = "passed" if not result["flags"] else "needs_repair"
    return result


def projects(workspace: Path):
    import yaml
    config = yaml.safe_load((workspace / "workbench.yaml").read_text(encoding="utf-8")) or {}
    for series in (config.get("series") or {}).values():
        for row in (series.get("episodes") or {}).values():
            if row.get("project"):
                project = (workspace / row["project"]).resolve()
                yield project


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    details = [inspect(project) for project in projects(workspace)]
    report = {
        "schema": "narration_sample_integrity_audit/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "method": "exact decoded source PCM containment in raw narration",
        "episodes_checked": len(details),
        "passed": sum(row["status"] == "passed" for row in details),
        "needs_repair": sum(row["status"] != "passed" for row in details),
        "source_takes_checked": sum(row.get("source_takes_checked", 0) for row in details),
        "detail": details,
        "note": "Exact raw PCM containment is a structural gate, not a listening or medical review.",
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: report[k] for k in ("episodes_checked", "passed", "needs_repair", "source_takes_checked")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
