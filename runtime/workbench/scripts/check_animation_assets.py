#!/usr/bin/env python3
"""Validate declared shot assets and review references before animation rendering."""
from __future__ import annotations

import argparse
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
    if not isinstance(data.get("assets"), list) or not data["assets"]:
        raise ValueError("No declared animation assets")
    for asset in data["assets"]:
        aid = asset.get("asset_id")
        if not isinstance(aid, str) or not aid or aid in assets:
            raise ValueError("Missing or duplicate asset ID")
        assets[aid] = asset
        source = file(asset.get("path"))
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
            evidence = json.loads(file(record.get("evidence_ref")).read_text())
            if (evidence.get("asset_id") != aid or file(evidence.get("asset_ref")) != source
                    or evidence.get(kind) != "passed" or not evidence.get("reviewer")
                    or not evidence.get("notes")):
                raise ValueError(f"{aid}: review evidence does not match asset and review type")
    shots = data.get("shots")
    if not isinstance(shots, list) or not shots:
        raise ValueError("Missing shot asset coverage")
    seen = set()
    for shot in shots:
        sid = shot.get("shot_id")
        if not isinstance(sid, str) or not sid or sid in seen:
            raise ValueError("Missing or duplicate shot ID")
        seen.add(sid)
        used = shot.get("asset_ids")
        if not isinstance(used, list) or not used or any(aid not in assets for aid in used):
            raise ValueError(f"{sid}: missing or unknown shot assets")
    return {"schema": "medical_animation_asset_check/v1", "status": "blocked" if pending else "passed",
            "manifest": str(manifest.resolve()), "assets": len(assets), "shots": len(shots),
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
