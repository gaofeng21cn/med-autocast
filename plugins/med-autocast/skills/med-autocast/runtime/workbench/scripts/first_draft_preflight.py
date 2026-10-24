#!/usr/bin/env python3
"""Create a read-only first-draft quality brief for one paper-theatre project.

This tool front-loads the recurring failure modes from the 2026-10 repair pass:
assembled main characters, missing pose-specific scale calibration, complex
objects rendered too small, and animation references copied without a traceable
use record. It is a locator and handoff report, never a visual or medical
approval gate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from pathlib import Path
from typing import Any

from audit_character_and_scale_contract import inspect_source, manifest_assets, project_sources
from check_animation_assets import check_assets


SCHEMA = "medical_first_draft_preflight/v1"
HUMAN = re.compile(
    r"(?:patient|doctor|clinician|person|woman|man|child|elder|pregnan|family|carer|"
    r"人物|患者|医生|儿童|老人|孕妇|家属)",
    re.IGNORECASE,
)
COMPLEX = re.compile(
    r"(?:anatomy|organ|pituitary|thyroid|kidney|uterus|ovary|breast|heart|lung|"
    r"vessel|artery|joint|brain|adrenal|垂体|甲状腺|肾|子宫|卵巢|乳腺|心脏|肺|"
    r"血管|关节|脑|肾上腺)",
    re.IGNORECASE,
)


def _used_asset_ids(manifest: dict[str, Any]) -> set[str]:
    used: set[str] = set()
    for shot in manifest.get("shots", []):
        if isinstance(shot, dict):
            used.update(item for item in shot.get("asset_ids", []) if isinstance(item, str))
    return used


def _manifest_brief(manifest_path: Path) -> dict[str, Any]:
    if not manifest_path.is_file():
        return {
            "status": "missing",
            "path": str(manifest_path),
            "assets": 0,
            "used_assets": 0,
            "human_assets": 0,
            "human_scale_calibrated": 0,
            "human_scale_pending": [],
            "complex_assets": 0,
            "animation_references": 0,
            "check": {"status": "missing_manifest"},
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check = check_assets(manifest_path)
    assets = manifest.get("assets", [])
    by_id = {item.get("asset_id"): item for item in assets if isinstance(item, dict)}
    used_ids = _used_asset_ids(manifest)
    used = [by_id[aid] for aid in sorted(used_ids) if aid in by_id]
    human = [item for item in used if HUMAN.search(
        f"{item.get('asset_id', '')} {item.get('visual_meaning', '')}")]
    complex_items = [item for item in used if COMPLEX.search(
        f"{item.get('asset_id', '')} {item.get('visual_meaning', '')}")]
    pending = []
    calibrated = 0
    for item in human:
        scale = item.get("human_scale") or {}
        calibration = scale.get("calibration") or {}
        if calibration.get("status") == "calibrated" and calibration.get("source_sha256"):
            source = (manifest_path.parent / item.get("path", "")).resolve()
            if source.is_file() and hashlib.sha256(source.read_bytes()).hexdigest() == calibration.get("source_sha256"):
                calibrated += 1
                continue
        pending.append(item.get("asset_id"))
    return {
        "status": "present",
        "path": str(manifest_path),
        "assets": len(assets),
        "used_assets": len(used),
        "human_assets": len(human),
        "human_scale_calibrated": calibrated,
        "human_scale_pending": pending,
        "complex_assets": len(complex_items),
        "animation_references": len(manifest.get("animation_references") or []),
        "check": check,
    }


def preflight(project: Path) -> dict[str, Any]:
    project = project.resolve()
    manifest_path = project / "asset_manifest.json"
    manifest = {}
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assets = manifest_assets(project)
    sources = project_sources(project)
    if not sources:
        sources = sorted((project / "src").glob("*.ts")) + sorted((project / "src").glob("*.js"))
    source_reports = []
    for source in sources:
        source_reports.append({
            "source": str(source),
            "locators": inspect_source(source.read_text(encoding="utf-8"), assets),
        })
    character_locators = [
        {**item, "kind": kind}
        for report in source_reports
        for kind, values in report["locators"].items()
        for item in values
    ]
    brief = _manifest_brief(manifest_path)
    debts: list[str] = []
    if brief["status"] == "missing":
        debts.append("asset_manifest_missing")
    if brief.get("human_scale_pending"):
        debts.append("human_scale_calibration_pending")
    if any(item.get("kind") == "programmatic_character_helpers" for item in character_locators):
        debts.append("programmatic_character_locator")
    if any(item.get("kind") == "small_explicit_assets" for item in character_locators):
        debts.append("size_complexity_locator")
    if brief.get("human_assets"):
        debts.append("shared_scene_scale_visual_review_pending")
    if brief.get("complex_assets"):
        debts.append("complex_object_readability_review_pending")
    return {
        "schema": SCHEMA,
        "project": str(project),
        "status": "candidate" if brief["status"] == "present" else "blocked",
        "manifest": brief,
        "sources": source_reports,
        "character_scale_locator_count": len(character_locators),
        "quality_debt": sorted(set(debts)),
        "required_next_checks": [
            "实际查看原尺寸与移动端宽度，核对同场人物身体段、姿态、地面/椅面和接触组",
            "复杂主体按解释任务取得足够阅读面积；必要时改近景、拆分或换简化版本",
            "确认医生镜头实际加载作者私有 Dr.咩，回读源码路径与当前图像",
            "完成代表镜头、整集 animatic、正常速度动态、最终 MP4 听辨和医学复核",
        ],
        "note": "只读定位与交接报告；不批准素材、动画、听感、医学或发布资格。",
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        result = preflight(args.project)
    except (OSError, ValueError, TypeError, KeyError) as exc:
        result = {"schema": SCHEMA, "status": "blocked", "error": str(exc)}
    rendered = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0 if result.get("status") == "candidate" else 2


if __name__ == "__main__":
    raise SystemExit(main())
