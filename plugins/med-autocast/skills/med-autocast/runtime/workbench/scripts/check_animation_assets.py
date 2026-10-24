#!/usr/bin/env python3
"""Validate declared shot assets and review references before animation rendering."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


def check_assets(manifest: Path) -> dict:
    data = json.loads(manifest.read_text())
    if data.get("schema") != "medical_animation_assets/v1":
        raise ValueError("Unsupported animation asset manifest")
    base = manifest.resolve().parent

    def file(ref):
        if not isinstance(ref, str) or not ref.strip():
            raise ValueError("Missing asset or evidence file reference")
        path = (base / ref).resolve()
        if not path.is_file():
            raise ValueError(f"Missing asset or evidence: {ref}")
        return path

    assets, pending = {}, []
    evidence_integrity = []
    if not isinstance(data.get("assets"), list):
        raise ValueError("Missing or invalid assets array")
    for asset in data["assets"]:
        aid = asset.get("asset_id")
        if not isinstance(aid, str) or not aid or aid in assets:
            raise ValueError("Missing or duplicate asset ID")
        assets[aid] = asset
        source = file(asset.get("path"))
        calibration = (asset.get('human_scale') or {}).get('calibration') or {}
        if calibration.get('status') == 'calibrated':
            if hashlib.sha256(source.read_bytes()).hexdigest() != calibration.get('source_sha256'):
                raise ValueError(f'{aid}: 人物尺度标定与实际载荷不一致')
        source_type = asset.get("source_type")
        if source_type not in ("reviewed_library", "imagegen", "licensed_web", "authored_graphic"):
            raise ValueError(f"{aid}: unsupported asset source")
        if not asset.get("visual_meaning") or not asset.get("must_not_imply"):
            raise ValueError(f"{aid}: missing visual meaning or medical limits")
        if not isinstance(asset.get("medical"), bool):
            raise ValueError(f"{aid}: missing explicit medical scope")
        if asset["medical"]:
            file(asset.get("medical_reference"))
        if source_type == "imagegen":
            file(asset.get("prompt_ref"))
            file(asset.get("generation_receipt"))
        elif source_type == "licensed_web":
            if not asset.get("source_url") or not asset.get("license"):
                raise ValueError(f"{aid}: missing source URL or license")
            file(asset.get("license_evidence"))
    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("Missing shot asset coverage")
    seen = set()
    used_ids = set()
    for shot in shots:
        sid = shot.get("shot_id")
        if not isinstance(sid, str) or not sid or sid in seen:
            raise ValueError("Missing or duplicate shot ID")
        seen.add(sid)
        if "asset_ids" not in shot:
            raise ValueError(f"{sid}: missing asset_ids declaration")
        used = shot["asset_ids"]
        if not isinstance(used, list) or any(
            not isinstance(aid, str) or not aid.strip() for aid in used
        ):
            raise ValueError(f"{sid}: asset_ids must be an array of non-empty strings")
        unknown = sorted(set(used) - set(assets))
        if unknown:
            raise ValueError(f"{sid}: unknown shot assets: {', '.join(unknown)}")
        # An explicit [] declares zero file dependencies. Procedural drawing
        # remains a scene-review responsibility, never an invented file asset.
        used_ids.update(used)
    animation_references = data.get("animation_references", [])
    if animation_references is None:
        animation_references = []
    if not isinstance(animation_references, list):
        raise ValueError("animation_references must be an array")
    reference_ids = set()
    for reference in animation_references:
        if not isinstance(reference, dict):
            raise ValueError("animation_references entries must be objects")
        external_id = reference.get("external_asset_id")
        if not isinstance(external_id, str) or not external_id.strip() or external_id in reference_ids:
            raise ValueError("Missing or duplicate animation reference ID")
        reference_ids.add(external_id)
        if reference.get("mode") not in {"baseline_reference", "adapted", "new_creation"}:
            raise ValueError(f"{external_id}: invalid animation reference mode")
        if reference.get("creative_ceiling") != "open":
            raise ValueError(f"{external_id}: animation reference must keep creative ceiling open")
        entry = file(reference.get("entry"))
        record = file(reference.get("library_record"))
        expected_record_sha = reference.get("library_record_sha256")
        if expected_record_sha and hashlib.sha256(record.read_bytes()).hexdigest() != expected_record_sha:
            raise ValueError(f"{external_id}: animation reference record changed")
        linked_shots = reference.get("shots", [])
        if not isinstance(linked_shots, list) or any(
                not isinstance(shot_id, str) or shot_id not in seen for shot_id in linked_shots):
            raise ValueError(f"{external_id}: animation reference shots must name declared shots")
    # A manifest is also an inventory. Review debt belongs to the assets that
    # the current shot coverage actually uses; unused candidates remain visible
    # as inventory metadata and do not block or pollute this render's report.
    for aid, asset in assets.items():
        if aid not in used_ids:
            continue
        if asset.get("status") == "rejected":
            raise ValueError(f"{aid}: rejected asset cannot enter rendering")
        if asset.get("status") != "approved_direct_use":
            pending.append(f"{aid}:direct_use_pending")
        for kind in (["visual_review", "medical_review"] if asset["medical"] else ["visual_review"]):
            record = asset.get(kind, {})
            if record.get("status") == "rejected":
                raise ValueError(f"{aid}: {kind} rejected")
            if record.get("status") != "passed":
                pending.append(f"{aid}:{kind}_pending")
                continue
            evidence_path = file(record.get("evidence_ref"))
            evidence = json.loads(evidence_path.read_text())
            if (evidence.get("asset_id") != aid or file(evidence.get("asset_ref")) != (base / asset["path"]).resolve()
                    or evidence.get(kind) != "passed" or not evidence.get("reviewer")
                    or not evidence.get("notes")):
                raise ValueError(f"{aid}: review evidence does not match asset and review type")
            # Older review receipts commonly listed contact sheets inside an
            # ``evidence`` array.  Checking only the outer JSON made a deleted
            # contact sheet look like a valid pass.  Missing nested evidence
            # downgrades the record to an unverified source review; it never
            # becomes a blocking production error by itself.
            nested = evidence.get("evidence", [])
            if isinstance(nested, str):
                nested = [nested]
            if isinstance(nested, list):
                missing_nested = []
                for ref in nested:
                    if not isinstance(ref, str) or not ref.strip():
                        missing_nested.append(str(ref))
                        continue
                    candidate = (base / ref).resolve()
                    if not candidate.is_file():
                        missing_nested.append(ref)
                if missing_nested:
                    evidence_integrity.append({
                        "asset_id": aid, "review": kind,
                        "evidence_ref": str(evidence_path),
                        "status": "missing_nested_evidence",
                        "missing": missing_nested,
                    })
                    pending.append(f"{aid}:{kind}_evidence_integrity_pending")
            elif nested:
                evidence_integrity.append({
                    "asset_id": aid, "review": kind,
                    "evidence_ref": str(evidence_path),
                    "status": "malformed_nested_evidence",
                })
                pending.append(f"{aid}:{kind}_evidence_integrity_pending")
    return {"schema": "medical_animation_asset_check/v1", "status": "blocked" if pending else "passed",
            "manifest": str(manifest.resolve()), "assets": len(assets), "shots": len(shots),
            "used_asset_ids": sorted(used_ids), "unused_asset_ids": sorted(set(assets) - used_ids),
            "animation_references": len(animation_references),
            "evidence_integrity": evidence_integrity,
            "administrative_status": "continue_with_review_queue" if pending else "ready_for_scene_review",
            "pending": pending, "domain_quality_approved": False,
            "note": "Checks declared coverage and review references only; inspect actual artwork and rendered frames."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", required=True, type=Path)
    args = parser.parse_args()
    try:
        result = check_assets(args.manifest)
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        result = {"status": "blocked", "error": str(exc)}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "passed" else 2


if __name__ == "__main__":
    raise SystemExit(main())
