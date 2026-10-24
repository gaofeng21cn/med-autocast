#!/usr/bin/env python3
"""Locate current character assets whose production anchors are absent or stale."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def read(path: Path, default):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, type(default)) else default
    except (OSError, ValueError):
        return default


def audit(workspace: Path) -> dict:
    config = yaml.safe_load((workspace / "workbench.yaml").read_text(encoding="utf-8")) or {}
    rows = []
    used = {}
    for series_id, series in (config.get("series") or {}).items():
        for episode_id, episode in (series.get("episodes") or {}).items():
            project = workspace / episode["project"]
            project_config = read(project / "project.json", {})
            manifest = read(project / project_config.get("assets", "asset_manifest.json"), {})
            for asset in manifest.get("assets", []):
                asset_id = asset.get("asset_id")
                if not asset_id or not asset.get("path"):
                    continue
                visual = " ".join(
                    str(asset.get(key, ""))
                    for key in ("visual_meaning", "original_source_type", "source_type")
                )
                name = (asset_id + " " + visual).casefold()
                complete_figure = any(token in name for token in (
                    "character", "person", "patient", "clinician", "pregnant",
                    "人物", "患者", "医生", "孕妇",
                )) and not any(token in asset_id.casefold() for token in (
                    "journal", "reader", "walker", "head", "hand", "arm",
                ))
                if not complete_figure:
                    continue
                registration = asset.get("registration") or {}
                anchors = registration.get("anchors") or {}
                pose = asset_id.casefold()
                required = ["head", "feet"]
                if any(token in pose for token in ("seated", "sit")):
                    required = ["head", "seat"]
                elif "lying" in pose:
                    required = ["head", "body"]
                missing = [name for name in required if name not in anchors]
                used.setdefault(asset_id, set()).add((series_id, episode_id))
                if missing:
                    rows.append(
                        {
                            "series_id": series_id,
                            "episode_id": episode_id,
                            "project": episode["project"],
                            "asset_id": asset_id,
                            "library_ref": asset.get("library_ref"),
                            "content_bounds": asset.get("content_bounds"),
                            "missing_anchors": missing,
                            "path": asset.get("path"),
                        }
                    )
    return {
        "schema": "paper_theatre_character_anchor_audit/v1",
        "workspace": str(workspace),
        "character_asset_ids_in_manifests": len(used),
        "episodes_with_character_candidates": len(
            {episode for episodes in used.values() for episode in episodes}
        ),
        "missing_anchor_findings": len(rows),
        "rows": rows,
        "blocks_production": False,
        "note": "按名称定位当前manifest中人物候选的锚点欠项；未追踪源码实际绘制，不是已使用素材或画面故障数量，坐标仍需对照原件和镜头。",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = audit(args.workspace.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
