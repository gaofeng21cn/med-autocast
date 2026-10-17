#!/usr/bin/env python3
"""Repair registered narration only; animation retiming/mix/render stay explicit."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import wave
from pathlib import Path

from audio_baseline import normalize
from narration_splice import join
from scan_narration_boundaries import current_projects


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rebuild(project, backup_root, gap_ms=180):
    receipt_path = project / "audio/narration_beats.json"
    receipt = json.loads(receipt_path.read_text())
    project_config = json.loads((project / "project.json").read_text())
    series, episode = project_config["series_id"], project_config["episode_id"]
    backup = backup_root / series / episode
    backup.mkdir(parents=True, exist_ok=True)
    for relative in ("audio/narration.wav", "audio/narration-normalized.wav",
                     "audio/narration_beats.json", "audio/pronunciation-review.json",
                     "score.json", "project.json"):
        original = project / relative
        destination = backup / relative
        if original.is_file() and not destination.exists():
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(original, destination)
    sources = []
    for beat in receipt["beats"]:
        path = Path(beat["audio"])
        if not path.is_absolute():
            path = project / path
        if not path.is_file():
            raise FileNotFoundError(f"{beat['id']}: {path}")
        sources.append(path)
    audio = project / "audio"
    with tempfile.TemporaryDirectory(prefix=".lossless-narration-", dir=audio) as temporary:
        raw = Path(temporary) / "narration.wav"
        norm = Path(temporary) / "narration-normalized.wav"
        rows = join(sources, raw, gap_ms=gap_ms, lead_ms=320, tail_ms=700)
        normalize(raw, norm)
        with wave.open(str(raw)) as handle:
            duration = handle.getnframes() / handle.getframerate()
        with wave.open(str(norm)) as handle:
            normalized_duration = handle.getnframes() / handle.getframerate()
        if abs(normalized_duration - duration) > 1 / 24000:
            raise ValueError("Normalization unexpectedly changed the source timeline")
        raw.replace(audio / "narration.wav")
        norm.replace(audio / "narration-normalized.wav")
    for beat, row, path in zip(receipt["beats"], rows, sources):
        beat.update(audio=str(path), start=row["placed_at"], end=row["placed_end"],
                    trimmed_head_seconds=0.0, trimmed_tail_seconds=0.0,
                    source_sample_rate=row["source_sample_rate"],
                    source_sha256=sha(path))
        row["id"] = beat["id"]
        row["source_sha256"] = sha(path)
    old_duration = receipt.get("duration")
    receipt.update(audio=str(audio / "narration-normalized.wav"), duration=duration,
                   full_listening="pending", tone_consistency="pending")
    receipt["splice"] = {
        "schema": "narration_splice/v2", "policy": "resample_correctly_preserve_all_source_samples",
        "gap_seconds": gap_ms / 1000, "lead_seconds": .32, "tail_seconds": .7,
        "sample_rate": 24000, "takes": rows,
        "raw_sha256": sha(audio / "narration.wav"),
        "normalized_sha256": sha(audio / "narration-normalized.wav"),
        "review": "source signal is preserved; actual pronunciation and full listening remain pending",
    }
    # The source path in migrated receipts may still name the previous version.
    narration_source = project / project_config.get("narration", "preproduction/narration.json")
    if narration_source.is_file():
        receipt["source"] = str(narration_source)
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    pronunciation = audio / "pronunciation-review.json"
    if pronunciation.is_file():
        review = json.loads(pronunciation.read_text())
        review.update(voice=str(audio / "narration-normalized.wav"),
                      voice_sha256=sha(audio / "narration-normalized.wav"), status="pending")
        by_id = {beat["id"]: beat for beat in receipt["beats"]}
        for row in review.get("beats", []):
            beat = by_id.get(row.get("id"))
            if beat:
                row.update(start=beat["start"], end=beat["end"], audio=beat["audio"])
        pronunciation.write_text(json.dumps(review, ensure_ascii=False, indent=2) + "\n")
    return {"series": series, "episode": episode, "project": str(project),
            "status": "narration_ready_needs_retime_mix_render", "duration": duration,
            "old_receipt_duration": old_duration,
            "old_render_duration": json.loads((backup / "score.json").read_text())["duration"],
            "beats": len(rows), "voice_sha256": receipt["splice"]["normalized_sha256"],
            "backup": str(backup), "project_pointers_changed": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--backup-root", type=Path, required=True)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--series")
    parser.add_argument("--episode")
    parser.add_argument("--gap-ms", type=int, default=180)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    rows = []
    for project in current_projects(args.workspace.resolve()):
        config = json.loads((project / "project.json").read_text())
        if args.series and config["series_id"] != args.series:
            continue
        if args.episode and config["episode_id"] != args.episode:
            continue
        row = (rebuild(project, args.backup_root.resolve(), args.gap_ms) if args.apply
               else {"project": str(project), "status": "planned"})
        rows.append(row)
        args.manifest.parent.mkdir(parents=True, exist_ok=True)
        args.manifest.write_text(json.dumps({"schema": "lossless_narration_repair/v1", "detail": rows},
                                           ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(row, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
