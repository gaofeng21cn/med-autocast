#!/usr/bin/env python3
"""Export non-blocking, evidence-scoped quality-review queues.

No production or publish file is modified. Audit locators start unresolved;
only explicit per-locator reviews bound to the current Score and source can
classify them. Catalog readability is never visual or medical approval.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import yaml

from audit_motion import audit
from check_animation_assets import check_assets


def sha256(path: Path, cache: dict | None = None) -> str | None:
    """Hash actual bytes, reusing a result only while file stat is unchanged."""
    try:
        stat = path.stat()
        if not path.is_file():
            return None
        key = (str(path.resolve()), stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)
        if cache is not None and key in cache:
            return cache[key]
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        value = digest.hexdigest()
        if cache is not None:
            cache[key] = value
        return value
    except OSError:
        return None


def json_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def source_binding(project: Path, cache: dict | None = None) -> dict:
    """Bind executable code, render-affecting media and build inputs."""
    source_dirs = [project / name for name in ("src", "assets", "public")]
    sources = [p for directory in source_dirs if directory.is_dir()
               for p in directory.rglob("*") if p.is_file()]
    extras = [project / name for name in ("index.html", "project.json", "asset_manifest.json",
              "package.json", "package-lock.json", "tsconfig.json", "scripts/build.mjs")
              if (project / name).is_file()]
    files = {str(p.relative_to(project)): sha256(p, cache) for p in sorted(set(sources + extras))}
    return {"score_sha256": sha256(project / "score.json", cache),
            "source_sha256": json_hash(files) if sources and all(files.values()) else None,
            "source_hash_recipe": "sha256(canonical-json(relative-path-to-sha256)); src/**, assets/**, public/** and entry/manifest/build inputs",
            "source_files": files}


def active_catalog_hashes(root: Path, config: dict, cache: dict | None = None,
                          diagnostics: list | None = None) -> set[str]:
    """Read back every payload of active catalog records and verify its SHA.

    Successful readback proves source availability only. No visual, medical,
    current-use, or scene judgment is inferred from the active catalog flag.
    """
    diagnostics = diagnostics if diagnostics is not None else []
    raw = (config.get("asset_library") or {}).get("catalog")
    if not raw:
        return set()
    catalog = Path(raw)
    if not catalog.is_absolute():
        catalog = root / catalog
    repo = catalog.parent.parent
    hashes: set[str] = set()
    try:
        lines = catalog.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        diagnostics.append({"code": "catalog_unreadable", "detail": str(exc)})
        return hashes
    for line_no, line in enumerate(lines, 1):
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            diagnostics.append({"code": "catalog_record_invalid", "line": line_no})
            continue
        if not isinstance(record, dict) or (record.get("curation") or {}).get("status") != "active":
            continue
        payload = record.get("payload")
        verified: list[str] = []
        if not isinstance(payload, list) or not payload:
            diagnostics.append({"code": "catalog_payload_missing", "asset_id": record.get("id")})
            continue
        for item in payload:
            if not isinstance(item, dict) or not isinstance(item.get("path"), str) or not item["path"]:
                break
            expected = item.get("sha256")
            actual = sha256(repo / item["path"], cache)
            if not actual or actual != expected:
                break
            verified.append(actual)
        if len(verified) != len(payload):
            diagnostics.append({"code": "catalog_payload_not_verified", "asset_id": record.get("id")})
            continue
        hashes.update(verified)
    return hashes


def classify_asset_review(project: Path, asset: dict, declared_ids: set[str],
                          catalog_hashes: set[str], cache: dict | None = None) -> dict:
    """Separate declared coverage, source readability and current-scene review."""
    if asset.get("asset_id") not in declared_ids:
        return {"tier": "unused_inventory"}
    source_hash = sha256(project / str(asset.get("path", "")), cache)
    visual = asset.get("visual_review") or {}
    evidence_ref = visual.get("evidence_ref")
    evidence_readable = bool(isinstance(evidence_ref, str) and evidence_ref
                             and sha256(project / evidence_ref, cache))
    catalog_readable = bool(source_hash and source_hash in catalog_hashes)
    return {
        "tier": "medical_and_scene_review_required" if asset.get("medical") else "scene_review_required",
        "coverage_source": "manifest_declaration_unverified",
        "source_sha256": source_hash,
        "source_payload_readable": bool(source_hash),
        "source_evidence_readable": evidence_readable or catalog_readable,
        "catalog_payload_sha_verified": catalog_readable,
        "source_visual_review_claim": visual.get("status"),
        "source_visual_claim_unverified": visual.get("status") == "passed",
        "source_review_note": "来源/证据可回读不等于原件视觉、当前镜头或医学批准；旧 passed 不继承。",
        "domain_quality_approved": False,
    }


def load_reviews(path: Path | None) -> tuple[list[dict], list[dict]]:
    if path is None:
        return [], []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        records = data.get("reviews") if isinstance(data, dict) else data
        if not isinstance(records, list):
            raise ValueError("motion review must contain a reviews array")
        diagnostics = []
        valid = []
        for index, record in enumerate(records):
            if isinstance(record, dict):
                valid.append(record)
            else:
                diagnostics.append({"code": "review_record_invalid", "index": index})
        return valid, diagnostics
    except (OSError, ValueError, TypeError) as exc:
        return [], [{"code": "motion_review_unreadable", "detail": str(exc)}]


def load_actual_asset_usage(path: Path | None) -> tuple[dict[tuple[str, str], dict], list[dict]]:
    """Read optional source-traced raster reachability without approving pixels."""
    if path is None:
        return {}, []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        rows = data.get("episodes") if isinstance(data, dict) else None
        if not isinstance(rows, list):
            raise ValueError("actual asset usage must contain episodes[]")
        result: dict[tuple[str, str], dict] = {}
        for row in rows:
            if not isinstance(row, dict) or not row.get("series") or not row.get("episode"):
                continue
            shots: dict[str, dict] = {}
            for shot in row.get("shots", []):
                if not isinstance(shot, dict) or not shot.get("shot_id"):
                    continue
                shots[str(shot["shot_id"])] = {
                    "used_asset_ids": sorted({str(x) for x in shot.get("used_asset_ids", []) if isinstance(x, str)}),
                    "procedural_refs": sorted({str(x) for x in shot.get("procedural_refs", []) if isinstance(x, str)}),
                    "source_evidence": shot.get("source_evidence", []),
                    "uncertain": shot.get("uncertain", []),
                }
            result[(str(row["series"]), str(row["episode"]))] = {
                "coverage_method": row.get("coverage_method", data.get("method")),
                "shots": shots,
            }
        return result, []
    except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
        return {}, [{"code": "actual_asset_usage_unreadable", "detail": str(exc), "path": str(path)}]


def classify_motion_locator(series: str, episode: str, locator: dict, binding: dict,
                            reviews: list[dict] | None = None, review_base: Path | None = None,
                            cache: dict | None = None) -> dict:
    """Consume explicit evidence-bound model decisions, never infer approval."""
    identity = json_hash(locator)
    result = dict(locator, locator_sha256=identity, triage_status="unresolved",
                  triage_reason="这是审片定位，未提供绑定当前候选的逐项判断。", review_diagnostics=[])
    candidates = []
    for record in reviews or []:
        if record.get("series") != series or record.get("episode") != episode:
            continue
        record_identity = record.get("locator_sha256")
        if record_identity is None and isinstance(record.get("locator"), dict):
            record_identity = json_hash(record["locator"])
        if record_identity != identity:
            continue
        if isinstance(record.get("locator"), dict) and json_hash(record["locator"]) != identity:
            result["review_diagnostics"].append({"code": "review_locator_identity_conflict"})
            continue
        if (not binding.get("score_sha256") or not binding.get("source_sha256")
                or record.get("score_sha256") != binding["score_sha256"]
                or record.get("source_sha256") != binding["source_sha256"]):
            result["review_diagnostics"].append({"code": "stale_or_unbound_review"})
            continue
        ref = record.get("evidence_ref")
        evidence_path = ((review_base or Path.cwd()) / ref).resolve() if isinstance(ref, str) and ref else None
        actual = sha256(evidence_path, cache) if evidence_path is not None else None
        if not actual or record.get("evidence_sha256") != actual:
            result["review_diagnostics"].append({"code": "review_evidence_unreadable_or_changed", "evidence_ref": ref})
            continue
        if (record.get("decision") not in {"not_a_defect", "confirmed_defect", "needs_scene_review"}
                or not record.get("reason") or not record.get("review_method")):
            result["review_diagnostics"].append({"code": "review_judgment_incomplete"})
            continue
        candidates.append(dict(record, evidence_path=str(evidence_path), evidence_sha256=actual))
    if len(candidates) > 1 and len({r["decision"] for r in candidates}) > 1:
        result["review_diagnostics"].append({"code": "conflicting_reviews"})
        return result
    elif candidates:
        record = candidates[-1]
        result.update(triage_status={"not_a_defect": "reviewed_not_defect",
                      "confirmed_defect": "confirmed_defect", "needs_scene_review": "unresolved"}[record["decision"]],
                      triage_reason=record["reason"], review=record,
                      review_scope="locator_only_not_continuous_motion_medical_or_release_approval")
    return result


def validate_output(output: Path, root: Path, config: dict, review_path: Path | None) -> None:
    output = output.resolve()
    protected = [root / "productions", root / "publish"]
    protected.extend((root / item["project"]).resolve()
                     for spec in (config.get("series") or {}).values()
                     for item in (spec.get("episodes") or {}).values() if item.get("project"))
    if ({"productions", "publish"} & set(output.parts)
            or any(output == p.resolve() or p.resolve() in output.parents for p in protected)):
        raise ValueError("report output cannot be inside production or publish directories")
    if output == (root / "workbench.yaml").resolve() or (review_path and output == review_path.resolve()):
        raise ValueError("report output cannot overwrite configuration or review inputs")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--motion-review", type=Path,
                        help="Optional reviews[] with series/episode, locator identity, Score/source SHA, decision, reason, method and evidence_ref")
    parser.add_argument("--actual-asset-usage", type=Path,
                        help="Optional source-traced actual-asset-usage.json; separates raster calls from mounted-only candidates")
    args = parser.parse_args()
    root = args.workspace.resolve()
    config = yaml.safe_load((root / "workbench.yaml").read_text(encoding="utf-8")) or {}
    output = args.output if args.output.is_absolute() else root / args.output
    review_path = args.motion_review
    if review_path and not review_path.is_absolute():
        review_path = root / review_path
    validate_output(output, root, config, review_path)
    reviews, diagnostics = load_reviews(review_path)
    actual_usage_path = args.actual_asset_usage
    if actual_usage_path and not actual_usage_path.is_absolute():
        actual_usage_path = root / actual_usage_path
    actual_usage, usage_diagnostics = load_actual_asset_usage(actual_usage_path)
    diagnostics.extend(usage_diagnostics)
    cache: dict = {}
    catalog_hashes = active_catalog_hashes(root, config, cache, diagnostics)
    rows = []
    motion_summary = {"unresolved": 0, "reviewed_not_defect": 0, "confirmed_defect": 0,
                      "confirmed_structural_debt": 0}
    asset_summary = {"declared_scene_review_required": 0,
                     "declared_medical_and_scene_review_required": 0}
    matched_reviews: set[str] = set()
    for series, spec in sorted((config.get("series") or {}).items()):
        for episode, item in sorted((spec.get("episodes") or {}).items()):
            project_ref = item.get("project") if isinstance(item, dict) else None
            project = ((root / project_ref).resolve() if isinstance(project_ref, str) and project_ref
                       else root / "__unresolved_episode_project__")
            manifest = project / "asset_manifest.json"
            row_diagnostics = []
            if project == root / "__unresolved_episode_project__":
                row_diagnostics.append({"code": "episode_project_unreported"})
            try:
                asset_check = check_assets(manifest)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                asset_check = {"status": "diagnostic", "pending": [], "error": str(exc)}
                row_diagnostics.append({"code": "asset_check_incomplete", "detail": str(exc)})
            try:
                manifest_data = json.loads(manifest.read_text(encoding="utf-8"))
            except (OSError, ValueError) as exc:
                manifest_data = {}
                row_diagnostics.append({"code": "manifest_unreadable", "detail": str(exc)})
            declared_ids = {aid for shot in manifest_data.get("shots", []) if isinstance(shot, dict)
                            for aid in shot.get("asset_ids", []) if isinstance(aid, str)}
            usage_row = actual_usage.get((series, episode))
            actual_ids = {aid for shot in (usage_row or {}).get("shots", {}).values()
                          for aid in shot.get("used_asset_ids", [])}
            try:
                motion = audit(project)
            except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
                motion = {}
                row_diagnostics.append({"code": "motion_audit_incomplete", "detail": str(exc)})
            binding = source_binding(project, cache)
            asset_tiers = {}
            for declared in manifest_data.get("assets", []):
                if not isinstance(declared, dict):
                    continue
                coverage_ids = actual_ids if usage_row is not None else declared_ids
                classification = classify_asset_review(project, declared, coverage_ids, catalog_hashes, cache)
                if classification["tier"] != "unused_inventory":
                    asset_tiers[str(declared.get("asset_id"))] = classification
                    summary_key = ("declared_medical_and_scene_review_required"
                                   if declared.get("medical") else "declared_scene_review_required")
                    asset_summary[summary_key] += 1
            classified_locators = []
            for locator in motion.get("review_locators", []):
                classified = classify_motion_locator(series, episode, locator, binding, reviews,
                                review_path.parent if review_path else None, cache)
                classified_locators.append(classified)
                motion_summary[classified["triage_status"]] += 1
                matched_reviews.add(json_hash({"series": series, "episode": episode,
                                              "locator_sha256": classified["locator_sha256"]}))
            structural = motion.get("quality_debt", [])
            motion_summary["confirmed_structural_debt"] += len(structural)
            rows.append({
                "series": series, "episode": episode, "project": str(project), "bindings": binding,
                "diagnostics": row_diagnostics,
                "asset_review": {
                    "declaration_check_status": asset_check.get("status"),
                    "coverage_source": "manifest_declaration_unverified",
                    "actual_render_use": "unverified_manifest_only",
                    "declared_used_asset_ids": sorted(declared_ids),
                    "declared_unused_asset_ids": sorted({a.get("asset_id") for a in manifest_data.get("assets", [])
                                                       if isinstance(a, dict) and isinstance(a.get("asset_id"), str)} - declared_ids),
                    "coverage_method": (usage_row or {}).get("coverage_method") if usage_row is not None else "manifest_declaration_unverified",
                    "actual_render_use": "source_traced_raster_reachability" if usage_row is not None else "unverified_manifest_only",
                    "actual_used_asset_ids": sorted(actual_ids) if usage_row is not None else [],
                    "mounted_only_asset_ids": sorted(declared_ids - actual_ids) if usage_row is not None else sorted(declared_ids),
                    "procedural_only": bool(usage_row is not None and not actual_ids),
                    "actual_shot_coverage": (usage_row or {}).get("shots", {}) if usage_row is not None else {},
                    "pending_declared_review_records": asset_check.get("pending", []), "asset_tiers": asset_tiers,
                    "administrative_status": "continue_with_review_queue",
                    "interpretation": "素材覆盖仅为 manifest 声明，尚未证明真实渲染使用；来源回读不代表视觉或医学批准。",
                },
                "motion_review": {"confirmed_structural_debt": structural,
                    "review_locators": classified_locators,
                    "interpretation": "未绑定当前候选的定位项保持 unresolved；已绑定判断也仅覆盖该项实际审查范围。"},
                "semantic_review": "pending", "continuous_motion_review": "pending",
                "full_listening": "pending", "medical_review": "pending", "release_eligible": False,
            })
    for index, record in enumerate(reviews):
        identity = record.get("locator_sha256")
        if identity is None and isinstance(record.get("locator"), dict):
            identity = json_hash(record["locator"])
        key = json_hash({"series": record.get("series"), "episode": record.get("episode"), "locator_sha256": identity})
        if key not in matched_reviews:
            diagnostics.append({"code": "review_target_unmatched_or_unbound", "index": index,
                                "series": record.get("series"), "episode": record.get("episode")})
    payload = {"schema": "paper_theatre_quality_debt_reclassification/v2",
        "production_inputs_modified": False, "episodes": len(rows), "rows": rows,
        "motion_triage_summary": motion_summary, "declared_asset_triage_summary": asset_summary,
        "asset_coverage_summary": ({
            "scope": "source_traced_raster_reachability",
            "general_asset_ids": sum(1 for row in rows for aid, tier in row["asset_review"]["asset_tiers"].items()
                                      if tier.get("tier") == "scene_review_required"),
            "medical_asset_ids": sum(1 for row in rows for aid, tier in row["asset_review"]["asset_tiers"].items()
                                      if tier.get("tier") == "medical_and_scene_review_required"),
            "procedural_only_episodes": sum(1 for row in rows if row["asset_review"].get("procedural_only")),
            "mounted_only_is_excluded": bool(actual_usage),
        } if actual_usage else {
            "scope": "manifest_declaration_unverified",
            "mounted_only_is_excluded": False,
        }),
        "actual_asset_usage_input": str(actual_usage_path) if actual_usage_path else None,
        "diagnostics": diagnostics, "domain_quality_approved": False,
        "note": "可继续消费的审查队列；缺失、过期或不完整证据产生诊断，不阻断制作，不自动批准。"}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"episodes": len(rows), "motion_triage_summary": motion_summary,
                      "declared_asset_triage_summary": asset_summary, "diagnostics": len(diagnostics),
                      "output": str(output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
