#!/usr/bin/env python3
"""Bind per-episode rebuild, audio and visual-review evidence to current bytes."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import yaml


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def values(value, keys: set[str]):
    found = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key in keys and isinstance(child, str):
                found.append(child)
            found.extend(values(child, keys))
    elif isinstance(value, list):
        for child in value:
            found.extend(values(child, keys))
    return found


def report_episode(data: dict, path: Path | None = None, series_ids: set[str] | None = None) -> tuple[str | None, str | None, str | None, list[str]]:
    if not isinstance(data, dict):
        return None, None, None, []
    series = data.get("series_id") or data.get("series")
    episode = data.get("episode_id") or data.get("episode_key") or data.get("episode")
    if isinstance(episode, str) and "/" in episode:
        embedded_series, episode = episode.split("/", 1)
        series = series or embedded_series
    # Legacy reports often carry only an episode id. Infer the series from a
    # filename only when the prefix is an exact registered series id; otherwise
    # leave it unbound instead of risking a cross-series match.
    if not series and path and series_ids:
        name = path.stem
        matches = [sid for sid in series_ids if name.startswith(sid + "-") or name.startswith(sid + "_")]
        if len(matches) == 1:
            series = matches[0]
    scores = values(data, {"score_sha256", "current_score_sha256", "source_score_sha256"})
    notes = []
    for key in ("findings_before", "open_findings", "remaining", "remaining_debt", "quality_debt"):
        value = data.get(key)
        if isinstance(value, list):
            notes.extend(str(item) for item in value if item)
    return series, episode, data.get("status"), notes[:8]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--reviews", type=Path, default=Path("work/audit-20261014/reviews"))
    parser.add_argument("--rebuild", type=Path, default=Path("work/audit-20261014/rebuild-20261015"))
    parser.add_argument("--lineage", type=Path, default=Path("work/audit-20261014/finalization/audio-lineage-post-rebuild"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    reviews = args.reviews if args.reviews.is_absolute() else root / args.reviews
    rebuild = args.rebuild if args.rebuild.is_absolute() else root / args.rebuild
    lineage = args.lineage if args.lineage.is_absolute() else root / args.lineage
    config = yaml.safe_load((root / "workbench.yaml").read_text(encoding="utf-8")) or {}
    series_ids = set((config.get("series") or {}).keys())
    review_index: dict[tuple[str, str], list[dict]] = {}
    for path in reviews.rglob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        series, episode, status, notes = report_episode(data, path, series_ids)
        if series and episode:
            review_index.setdefault((series, episode), []).append({
                "path": str(path), "status": status,
                "score_hashes": values(data, {"score_sha256", "current_score_sha256", "source_score_sha256"}),
                "notes": notes,
            })
    rows = []
    for series, spec in sorted((config.get("series") or {}).items()):
        for episode, item in sorted((spec.get("episodes") or {}).items()):
            project = (root / item["project"]).resolve()
            score = project / "score.json"
            rebuild_file = rebuild / series / f"{episode}.json"
            lineage_file = lineage / series / f"{episode}.json"
            rebuild_data = json.loads(rebuild_file.read_text()) if rebuild_file.is_file() else {}
            lineage_data = json.loads(lineage_file.read_text()) if lineage_file.is_file() else {}
            score_hash = sha(score)
            bound_reviews = [r for r in review_index.get((series, episode), []) if score_hash and score_hash in r["score_hashes"]]
            stale_reviews = [r for r in review_index.get((series, episode), []) if r not in bound_reviews]
            rows.append({
                "series": series, "episode": episode, "project": str(project),
                "current_score_sha256": score_hash,
                "rebuild_status": "complete" if rebuild_data.get("failed_stage") is None and len(rebuild_data.get("completed_stages", [])) == 6 else "incomplete",
                "rebuild_receipt": str(rebuild_file) if rebuild_file.is_file() else None,
                "lineage_flags": len(lineage_data.get("flags", [])),
                "visual_review_current": bool(bound_reviews),
                "visual_review_reports": [r["path"] for r in bound_reviews],
                "stale_visual_reports": [r["path"] for r in stale_reviews],
                "known_review_notes": [note for r in bound_reviews for note in r["notes"]][:8],
                "semantic_review": "pending" if not bound_reviews else "candidate_reviewed_pending_continuous_dynamic",
                "full_listening": "pending", "medical_review": "pending", "release_eligible": False,
            })
    summary = {
        "schema": "current_episode_status/v1", "episodes": len(rows),
        "rebuild_complete": sum(r["rebuild_status"] == "complete" for r in rows),
        "lineage_clean": sum(r["lineage_flags"] == 0 for r in rows),
        "visual_review_bound_to_current_score": sum(r["visual_review_current"] for r in rows),
        "visual_review_pending_or_stale": sum(not r["visual_review_current"] for r in rows),
        "full_listening_complete": 0, "medical_review_complete": 0, "release_eligible": 0,
        "notes": "逐集状态表只绑定当前工程和证据；连续动态、完整听感、医学审核和公开发布必须逐集真实完成。",
        "episodes_detail": rows,
    }
    output = args.output if args.output.is_absolute() else root / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md = output.with_suffix(".md")
    lines = ["# 89 集当前状态表", "", summary["notes"], "", f"共 {len(rows)} 集；六阶段完成 {summary['rebuild_complete']}；血缘无旗标 {summary['lineage_clean']}；视觉报告与当前 Score 绑定 {summary['visual_review_bound_to_current_score']}。", "", "| 系列 | 集数 | 重建 | 血缘 | 当前视觉报告 | 剩余状态 |", "| --- | --- | --- | --- | --- | --- |"]
    for row in rows:
        lines.append(f"| {row['series']} | {row['episode']} | {row['rebuild_status']} | {row['lineage_flags']} flags | {'有' if row['visual_review_current'] else '待绑定/过期'} | 连续动态/听辨/医学待审 |")
    md.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("episodes", "rebuild_complete", "lineage_clean", "visual_review_bound_to_current_score", "visual_review_pending_or_stale")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
