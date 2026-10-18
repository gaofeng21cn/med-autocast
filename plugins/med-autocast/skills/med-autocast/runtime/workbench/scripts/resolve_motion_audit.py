#!/usr/bin/env python3
"""Export existing motion declarations for review; never modify production inputs.

The legacy writer inferred phases, directions, holds and continuity without
observing frames. Those are unverified declarations, not source/runtime evidence.
This compatibility entry now only locates actual scores and emits a review packet.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

DECLARATIONS = (
    "shot_recipe", "motion_arc", "event_phases", "phase_evidence", "hold_reason",
    "carrier", "transition", "motion_directions", "motion_quality_review",
)


def review_packet(project: Path) -> dict:
    score_path = project / "score.json"
    raw = score_path.read_bytes()
    score = json.loads(raw)
    legacy = (score.get("motion_review") or {}).get("schema") == "motion_director_evidence/v1"
    return {
        "project": str(project), "score": str(score_path),
        "score_sha256": hashlib.sha256(raw).hexdigest(),
        "status": "unverified_declarations", "legacy_auto_enriched": legacy,
        "representative_shot_declaration": score.get("signature_shot") or score.get("representative_shot"),
        "shots": [{
            "id": shot.get("id"), "start": shot.get("start"), "end": shot.get("end"),
            "events": shot.get("events", {}),
            "declared": {key: shot[key] for key in DECLARATIONS if key in shot},
            "continuous_motion_review": "pending",
            "next_action": "查看当前真实动作及邻镜，核对表意、接触、节奏与结果；有缺陷改导演/实现，不自动补判断。",
        } for shot in score.get("shots", []) if isinstance(shot, dict)],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, default=Path("work/review/motion-review-packet.json"))
    args = parser.parse_args()
    root = args.workspace.resolve()
    cfg = yaml.safe_load((root / "workbench.yaml").read_text(encoding="utf-8")) or {}
    output = (root / args.output).resolve()
    projects = []
    for series, spec in (cfg.get("series") or {}).items():
        for episode, item in (spec.get("episodes") or {}).items():
            if item.get("project"):
                projects.append((series, episode, (root / item["project"]).resolve()))
    # The sole output must not alias a production file (including via symlinks).
    review_root = (root / "work/review").resolve()
    if not output.is_relative_to(review_root) or output.suffix != ".json":
        parser.error("--output 只能是 work/review/ 下的 JSON；不写制作输入或用户交付")
    if any(output.is_relative_to(project) for _, _, project in projects):
        parser.error("输出不能位于实际单集工程内")
    rows = []
    for series, episode, project in projects:
        try:
            row = review_packet(project)
        except (OSError, ValueError, TypeError, AttributeError) as exc:
            row = {"project": str(project), "status": "diagnostic", "error": str(exc)}
        rows.append({"series": series, "episode": episode, **row})
    payload = {
        "schema": "motion_review_packet/v2", "status": "declarations_exported",
        "production_inputs_modified": False, "inferred_phases": False,
        "source_code_or_frames_inspected": False, "blocks_stage_progress": False,
        "episodes": len(rows), "detail": rows,
        "note": "只汇集现有声明；字段齐全、旧审计清零不证明画面已修复。",
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"episodes": len(rows), "production_inputs_modified": False, "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
