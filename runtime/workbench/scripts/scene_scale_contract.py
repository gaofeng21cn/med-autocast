"""Shared defaults and structural helpers for the human scene-scale contract.

The contract is intentionally small: it records the scene density and the
evidence that each real person was calibrated before a rough animation is
eligible.  Visual approval still belongs to the director and visual review.
"""
from __future__ import annotations

import copy
from typing import Any


SCHEMA = "medical_scene_scale_contract/v1"
HUMAN_LAYERS = {"character", "person", "human", "real_person"}
DIAGRAM_LAYERS = {"medical_diagram", "diagram", "diagram_exception"}
DIAGRAM_SCALE_MODES = {
    "diagrammatic_structure", "magnified_detail", "data_visualization",
    "symbolic_metaphor",
}
READY_STATUSES = {"calibrated_for_current_scene", "ready", "reviewed"}
TEST_FIT_READY_STATUSES = {"recorded", "reviewed", "passed"}


def default_scale_contract() -> dict[str, Any]:
    """Return a fresh required contract for every new independent project."""
    return {
        "schema": SCHEMA,
        "status": "not_applicable",
        "enforcement": "required",
        "pixels_per_cm": None,
        "human_asset_ids": [],
        "diagram_asset_ids": [],
        "same_scene_test_fit": {
            "status": "not_applicable",
            "evidence_refs": [],
            "required_views": ["original_size", "mobile_width", "motion_contact", "neighbor_shot"],
        },
        "diagram_policy_ref": "docs/49_示意图分类与跨层排景逻辑.md",
        "basis": "新单集默认携带；无真实人物时保持not_applicable，加入真实人物后必须补齐共同场景标尺、姿态标定和同场试装。",
    }


def layer(item: dict[str, Any]) -> str:
    return str(item.get("visual_layer") or item.get("scale_scene_role") or "").strip().lower()


def scale_mode(item: dict[str, Any]) -> str:
    return str(item.get("scale_mode") or "").strip().lower()


def is_diagram(item: dict[str, Any]) -> bool:
    return layer(item) in DIAGRAM_LAYERS or scale_mode(item) in DIAGRAM_SCALE_MODES


def diagram_class(item: dict[str, Any]) -> str | None:
    if not is_diagram(item):
        return None
    value = item.get("diagram_class") or scale_mode(item)
    return str(value).strip() if value else None


def is_human(item: dict[str, Any]) -> bool:
    """Read an explicit scene role; names and descriptions are not proof."""
    if is_diagram(item):
        return False
    return layer(item) in HUMAN_LAYERS


def manifest_has_humans(manifest: dict[str, Any]) -> bool:
    contract = manifest.get("scale_contract") or {}
    return bool(contract.get("human_asset_ids")) or any(
        is_human(item) for item in manifest.get("assets", []) if isinstance(item, dict)
    )


def fresh_contract_for_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    """Add a required contract without overwriting an existing project choice."""
    contract = manifest.get("scale_contract")
    if isinstance(contract, dict):
        return contract
    result = default_scale_contract()
    if manifest_has_humans(manifest):
        result["status"] = "pending"
        result["same_scene_test_fit"]["status"] = "pending"
    return result


def copy_contract(contract: dict[str, Any]) -> dict[str, Any]:
    return copy.deepcopy(contract)
