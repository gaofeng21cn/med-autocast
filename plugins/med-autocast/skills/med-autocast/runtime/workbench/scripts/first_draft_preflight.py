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
from _opl_file_hash import sha256_file
import json
import re
from pathlib import Path
from typing import Any

from audit_character_and_scale_contract import inspect_source, manifest_assets, project_sources
from check_animation_assets import check_assets
from scene_scale_contract import (
    READY_STATUSES,
    diagram_class,
    TEST_FIT_READY_STATUSES,
    is_diagram,
    is_human,
)


SCHEMA = "medical_first_draft_preflight/v1"
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


def _human_asset(item: dict[str, Any]) -> bool:
    return is_human(item)


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
            "scale_contract": {"status": "missing", "enforcement_required": False},
            "check": {"status": "missing_manifest"},
        }
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    check = check_assets(manifest_path)
    assets = manifest.get("assets", [])
    by_id = {item.get("asset_id"): item for item in assets if isinstance(item, dict)}
    used_ids = _used_asset_ids(manifest)
    used = [by_id[aid] for aid in sorted(used_ids) if aid in by_id]
    contract = manifest.get("scale_contract") or {}
    declared_human_ids = contract.get("human_asset_ids")
    if not isinstance(declared_human_ids, list):
        declared_human_ids = []
    declared_human_ids = [item for item in declared_human_ids if isinstance(item, str)]
    # Semantic identity is declared by the director; labels and names are not proof.
    human = [item for item in used if _human_asset(item) or item.get("asset_id") in declared_human_ids]
    diagrams = [item for item in used if is_diagram(item)]
    complex_items = [item for item in used if COMPLEX.search(
        f"{item.get('asset_id', '')} {item.get('visual_meaning', '')}")]
    pending = []
    calibrated = 0
    for item in human:
        scale = item.get("human_scale") or {}
        calibration = scale.get("calibration") or {}
        if calibration.get("status") == "calibrated" and calibration.get("source_sha256"):
            source = (manifest_path.parent / item.get("path", "")).resolve()
            if source.is_file() and sha256_file(source) == calibration.get("source_sha256"):
                calibrated += 1
                continue
        pending.append(item.get("asset_id"))
    ppcm = contract.get("pixels_per_cm")
    human_ids = [item.get("asset_id") for item in human]
    human_id_mismatch = sorted(set(human_ids) ^ set(declared_human_ids))
    human_diagram_conflict = sorted(
        item.get("asset_id") for item in diagrams if item.get("asset_id") in declared_human_ids
    )
    test_fit = contract.get("same_scene_test_fit") or {}
    test_fit_status = test_fit.get("status") if isinstance(test_fit, dict) else None
    test_fit_ready = not human or test_fit_status in TEST_FIT_READY_STATUSES
    contract_ready = bool(
        human
        and isinstance(ppcm, (int, float))
        and not isinstance(ppcm, bool)
        and ppcm > 0
        and contract.get("status") in READY_STATUSES
        and not pending
        and not human_id_mismatch
        and not human_diagram_conflict
        and test_fit_ready
    ) if human else not human_id_mismatch
    scale_summary = {
        "status": contract.get("status", "not_applicable" if not human else "missing"),
        "enforcement_required": contract.get("enforcement") == "required",
        "pixels_per_cm": ppcm,
        "human_asset_ids": human_ids,
        "declared_human_asset_ids": declared_human_ids,
        "human_asset_id_mismatch": human_id_mismatch,
        "human_diagram_conflict": human_diagram_conflict,
        "human_scale_pending": pending,
        "diagram_layer_exempt": [item.get("asset_id") for item in diagrams],
        "diagram_classes": {item.get("asset_id"): diagram_class(item) for item in diagrams},
        "same_scene_test_fit": test_fit,
        "same_scene_test_fit_ready": test_fit_ready,
        "ready": contract_ready,
        "basis": contract.get("basis"),
    }
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
        "scale_contract": scale_summary,
        "check": check,
    }


def _naturalness_brief(project: Path) -> dict[str, Any]:
    """Read deterministic evidence bindings without approving naturalness.

    A JSON file is a handoff record, not a quality gate.  In particular, a
    root ``status: passed`` plus present keys is never promoted to a machine
    approval.  The actual decision remains a per-shot visual review at the
    original, mobile and normal-speed views.
    """
    path = project / "qa" / "naturalness-review.json"
    required = [
        "text_readability", "complete_body_continuity", "action_causality",
        "contact_and_settle", "text_free_readback", "mobile_readability",
    ]
    if not path.is_file():
        return {
            "status": "not_provided",
            "path": str(path),
            "declared_status": None,
            "missing": required,
            "review_required": True,
            "binding": {"evidence_refs": [], "missing_evidence": [], "shot_records": 0},
            "note": "JSON不是自然性门；导演和视觉QA须回到逐镜实际帧、手机宽度和正常速度复核。",
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return {
            "status": "unreadable",
            "path": str(path),
            "declared_status": None,
            "error": str(exc),
            "missing": required,
            "review_required": True,
            "binding": {"evidence_refs": [], "missing_evidence": [], "shot_records": 0},
            "note": "记录不可读；不得把机器错误或缺失记录写成自然性通过。",
        }

    def _refs(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return [item for item in value if isinstance(item, str) and item]
        return []

    # Support both the older flat review and the newer per-shot review, but
    # only inspect whether evidence is bound to files that exist.  The values
    # of text/body/action fields are semantic judgements for a human reviewer.
    evidence_refs = _refs(payload.get("evidence"))
    shot_records = payload.get("shots") if isinstance(payload.get("shots"), dict) else {}
    if isinstance(shot_records, dict):
        for record in shot_records.values():
            if isinstance(record, dict):
                evidence_refs.extend(_refs(record.get("evidence")))
    evidence_refs = list(dict.fromkeys(evidence_refs))
    missing_evidence = []
    for ref in evidence_refs:
        candidate = (project / ref).resolve()
        try:
            candidate.relative_to(project)
        except ValueError:
            missing_evidence.append(ref)
            continue
        if not candidate.is_file():
            missing_evidence.append(ref)
    missing = [key for key in required if key in payload and payload.get(key) in (None, "", "pending")]
    return {
        "status": "review_required",
        "path": str(path),
        "declared_status": payload.get("status"),
        "missing": missing,
        "reviewed_version": payload.get("reviewed_version"),
        "scope": payload.get("scope") or payload.get("review_method"),
        "review_required": True,
        "binding": {
            "evidence_refs": evidence_refs,
            "missing_evidence": missing_evidence,
            "shot_records": len(shot_records) if isinstance(shot_records, dict) else 0,
        },
        "note": "仅回读版本、范围和证据路径；根 status/字段存在不构成自然性通过，必须逐镜视觉Review。",
    }


def preflight(project: Path, manifest_ref: Path | None = None) -> dict[str, Any]:
    project = project.resolve()
    manifest_path = (project / manifest_ref).resolve() if manifest_ref else project / "asset_manifest.json"
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
    naturalness = _naturalness_brief(project)
    debts: list[str] = []
    if brief["status"] == "missing":
        debts.append("asset_manifest_missing")
    if brief.get("human_scale_pending"):
        debts.append("human_scale_calibration_pending")
    scale = brief.get("scale_contract") or {}
    if brief.get("human_assets") and not scale.get("ready"):
        debts.append("scale_contract_pending")
    if scale.get("human_asset_id_mismatch"):
        debts.append("scale_contract_human_asset_ids_mismatch")
    if scale.get("human_diagram_conflict"):
        debts.append("scale_contract_human_diagram_conflict")
    if brief.get("human_assets") and not scale.get("same_scene_test_fit_ready"):
        debts.append("same_scene_test_fit_pending")
    if any(item.get("kind") == "programmatic_character_helpers" for item in character_locators):
        debts.append("programmatic_character_locator")
    if any(item.get("kind") == "small_explicit_assets" for item in character_locators):
        debts.append("size_complexity_locator")
    if brief.get("human_assets"):
        debts.append("shared_scene_scale_visual_review_pending")
    if brief.get("complex_assets"):
        debts.append("complex_object_readability_review_pending")
    # Naturalness is intentionally not a JSON-form gate.  Keep deterministic
    # evidence binding visible, while leaving the semantic decision to visual
    # QA.  Missing or stale bindings are reported in the brief itself.
    return {
        "schema": SCHEMA,
        "project": str(project),
        "status": (
            "blocked"
            if brief["status"] == "missing"
            or ((brief.get("scale_contract") or {}).get("enforcement_required")
                and not (brief.get("scale_contract") or {}).get("ready"))
            else "candidate"
        ),
        "manifest": brief,
        "naturalness": naturalness,
        "sources": source_reports,
        "character_scale_locator_count": len(character_locators),
        "quality_debt": sorted(set(debts)),
        "required_next_checks": [
            "先回读scale_contract的共同场景pixels_per_cm与每个真实人物标定；医学示意层可单独按解释职责定比例",
            "实际查看原尺寸与移动端宽度，核对同场人物身体段、姿态、地面/椅面和接触组",
            "复杂主体按解释任务取得足够阅读面积；必要时改近景、拆分或换简化版本",
            "确认医生镜头实际加载作者私有 Dr.咩，回读源码路径与当前图像",
            "检查文字归属与遮挡、人物完整连续性、动作因果、接触落点、去文字反向读图和移动端自然性，并写入qa/naturalness-review.json",
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
