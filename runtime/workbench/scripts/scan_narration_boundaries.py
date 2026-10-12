#!/usr/bin/env python3
"""Report every current episode whose narration takes carry head silence.

The defect this finds is invisible to duration and loudness checks: a take that
starts late still has the right length and the right RMS, but the first syllable
after every boundary is inaudible.

Scope is the episodes registered in workbench.yaml, not every version directory
under productions/. Historical revisions are deliberately preserved unmodified so
an old take can still be compared against the repaired one; scanning them would
also inflate the episode count, since one episode can hold many revisions.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from narration_splice import speech_report


def current_projects(workspace: Path):
    """Read the episodes the workbench currently ships, not every revision on disk."""
    import yaml

    config = yaml.safe_load((workspace / "workbench.yaml").read_text()) or {}
    seen = []
    for series in (config.get("series") or {}).values():
        for episode in (series.get("episodes") or {}).values():
            project = episode.get("project")
            if not project:
                continue
            resolved = (workspace / project).resolve()
            if resolved.is_dir() and resolved not in seen:
                seen.append(resolved)
    return seen


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--threshold", type=float, default=0.08)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--repair-normalized", action="store_true",
                        help="re-join already spliced takes so narration-normalized.wav is rebuilt")
    args = parser.parse_args()

    affected, checked = [], 0
    workspace = args.workspace.resolve()
    for project in current_projects(workspace):
        beats_file = project / "audio" / "narration_beats.json"
        if not beats_file.is_file():
            continue
        data = json.loads(beats_file.read_text())
        beats = [b for b in data.get("beats", []) if Path(b.get("audio", "")).is_file()]
        if not beats:
            continue
        checked += 1
        reports = [speech_report(Path(b["audio"])) for b in beats]
        worst = max(r["head_silence"] for r in reports)
        # Judge the joined track the listener actually hears, not the raw takes.
        joined = data.get("splice")
        track = beats_file.parent / "narration.wav"
        joined_gap = None
        if joined and track.is_file():
            joined_gap = joined.get("gap_seconds")
        elif worst <= args.threshold:
            continue
        entry = {
            "series": project.parent.parent.name,
            "episode": project.name,
            "revision": project.name if project.name.startswith("v") else "",
            "beats": len(beats),
            "worst_head_silence": round(worst, 3),
            "affected_beats": [b["id"] for b, r in zip(beats, reports)
                                if r["head_silence"] > args.threshold],
            "joined_gap_seconds": joined_gap,
            "source": "splice_repaired" if joined else "raw_takes",
        }
        if (args.apply and not joined) or (args.repair_normalized and joined):
            from narration_splice import join

            audio_dir = beats_file.parent
            target = audio_dir / "narration.wav"
            score = beats_file.parents[1] / "score.json"
            video_seconds = None
            if score.is_file():
                video_seconds = float(json.loads(score.read_text()).get("duration") or 0) or None
            splice = join([Path(b["audio"]) for b in beats], target,
                          total_seconds=video_seconds)
            backup = audio_dir / "narration-before-splice-fix.wav"
            if not backup.exists() and target.is_file():
                backup.write_bytes(target.read_bytes())
            # The mix stage reads narration-normalized.wav, so the same repair
            # has to land there too or the shipped episode keeps the old splice.
            normalized = audio_dir / "narration-normalized.wav"
            if normalized.is_file():
                normalized_backup = audio_dir / "narration-normalized-before-splice-fix.wav"
                if not normalized_backup.exists():
                    normalized_backup.write_bytes(normalized.read_bytes())
                spliced_normalized = audio_dir / ".narration-spliced-for-normalize.wav"
                join([Path(b["audio"]) for b in beats], spliced_normalized,
                     total_seconds=video_seconds)
                from audio_baseline import normalize

                normalize(spliced_normalized, normalized)
                spliced_normalized.unlink(missing_ok=True)
            data["splice"] = {
                "policy": "按实测语音边界裁掉前导与尾部静音，再按固定短停顿拼接",
                "gap_seconds": 0.26,
                "lead_seconds": 0.32,
                "takes": splice,
                "review": "拼接处应可听到完整首字；实际听辨仍待审",
            }
            if video_seconds:
                data["splice"]["target_duration_seconds"] = round(video_seconds, 3)
            for beat, report in zip(beats, splice):
                beat["start"] = report["placed_at"]
                beat["end"] = report["placed_end"]
            beats_file.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            entry["repaired"] = str(target)
        affected.append(entry)

    print(json.dumps({"schema": "narration_boundary_scan/v1",
                      "threshold_seconds": args.threshold,
                      "episodes_checked": checked, "affected": len(affected),
                      "applied": args.apply, "detail": affected}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
