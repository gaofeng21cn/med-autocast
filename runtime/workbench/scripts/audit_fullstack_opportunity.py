#!/usr/bin/env python3
"""Four-layer full-stack quality & opportunity audit for paper-theatre episodes.

Evaluates a single project (`--project`) or all active projects in a workspace
(`--workspace . --summary`) across coordinated improvement layers:
  1. Script / Narration pacing (extra-long single shots, dense cue blocks, tail silences)
  2. Storyboard / Cut-point cadence (uniform shot lengths, missing arc metadata, heading inside camera)
  3. Assets / Staging materiality (sparse manifests, uncalibrated scale contracts, geometry-heavy shots)
  4. Animation craft & actor naturalness (physics primitives, grounded staging, actor kit usage,
     hollow-desk bust occlusion, rapid pose switches, hard-cut pose swaps)
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml


PHYSICS_RE = re.compile(
    r"\b(landPose|springMove|springEase|springTrack|settledBreath|shotBreath|aliveBreath|demotePose|phaseShiftStep|landGroup|contactShadow|SPRING)\b"
)
RAW_ALIVE_RE = re.compile(r"\baliveBreath\b")
GROUNDING_RE = re.compile(r"\b(contactShadow|landGroup|landPiece)\b")
SPRITE_CALL_RE = re.compile(r"\b(sprite|stage\.image|person)\s*\(")
SHAPE_CALL_RE = re.compile(r"\b(cut|circle|stroke|rect|fillRect|arc)\s*\(")
ACTOR_KIT_RE = re.compile(
    r"\b(drawActorPose|drawActorAtlas|drawActorWalk|drawActorEdgeHand|actorCadence|actorTransition)\b"
)
CHARACTER_ID_RE = re.compile(
    r"(?:presenter|clinician|doctor|patient|elder|woman|man|child|teen|mother|father|parent|carer|girl|boy|nurse|family)",
    re.IGNORECASE,
)
ACTOR_CODE_RE = re.compile(
    r"(?:\bdrawActor(?:Pose|Atlas|Walk|EdgeHand)\b|\bperson\s*\([^)]*,\s*['\"][a-zA-Z0-9_-]+['\"])"
)
HARD_CUT_ACTOR_RE = re.compile(
    r"(?:\bp\s*[><=]=?\s*0?\.\d+|c\.t\s*[><=]=?\s*[\w.]+)\s*\?\s*['\"](?:doctor_|presenter_|clinician_|woman_|man_|elder_|child_|teen_|patient_|mother_|father_|parent_|carer_|boy_|girl_|nurse_|family_)"
)
LEGACY_STIFF_ACTOR_SUFFIXES = ("_pointing_v1", "_reach_v1", "_walk_v1")
BEAT_ARRAY_START_RE = re.compile(r"(?:\bbeats\s*:\s*|:\s*ActorBeat\[\]\s*=\s*)\[")
BEAT_ENTRY_RE = re.compile(r"\{([^{}]*)\}", re.S)
BEAT_AT_RE = re.compile(r"\bat\s*:\s*([0-9]+(?:\.[0-9]+)?)")
BEAT_POSE_RE = re.compile(r"\bpose\s*:\s*(['\"])([^'\"]+)\1")


def count_rapid_actor_switches(src_text: str, min_gap_sec: float = 1.4) -> int:
    """Count consecutive actor pose switches separated by less than `min_gap_sec`."""
    rapid = 0
    for m in BEAT_ARRAY_START_RE.finditer(src_text):
        idx = m.end() - 1
        depth = 0
        end_idx = None
        for pos in range(idx, len(src_text)):
            ch = src_text[pos]
            if ch == "[":
                depth += 1
            elif ch == "]":
                depth -= 1
                if depth == 0:
                    end_idx = pos + 1
                    break
        if end_idx is None:
            continue
        block = src_text[idx:end_idx]
        parsed: list[tuple[float, str]] = []
        for entry in BEAT_ENTRY_RE.finditer(block):
            body = entry.group(1)
            at_m = BEAT_AT_RE.search(body)
            pose_m = BEAT_POSE_RE.search(body)
            if at_m and pose_m:
                parsed.append((float(at_m.group(1)), pose_m.group(2)))
        parsed.sort(key=lambda item: item[0])
        for (prev_t, prev_p), (cur_t, cur_p) in zip(parsed, parsed[1:]):
            if cur_p != prev_p and (cur_t - prev_t) < min_gap_sec:
                rapid += 1
    return rapid


def count_bust_behind_hollow_desk(src_text: str) -> int:
    """Detect shots that combine a waist-cut drawActorAtlas bust with an open-leg desk() helper."""
    shot_matches = list(re.finditer(r"\bid\s*:\s*(['\"])S\d+\1", src_text))
    if not shot_matches:
        blocks = [src_text]
    else:
        blocks = []
        for idx, m in enumerate(shot_matches):
            start = m.start()
            end = shot_matches[idx + 1].start() if idx + 1 < len(shot_matches) else len(src_text)
            blocks.append(src_text[start:end])
    hits = 0
    for block in blocks:
        has_atlas = bool(re.search(r"\bdrawActorAtlas\s*\(", block))
        has_hollow_desk = bool(re.search(r"(?<![A-Za-z0-9_])desk\s*\(", block))
        if has_atlas and has_hollow_desk:
            hits += 1
    return hits


def count_heading_inside_camera(src_text: str) -> int:
    """Detect heading() calls inside a stage.camera(...) callback that zoom can clip above y=0."""
    hits = 0
    for m in re.finditer(r"\.camera\s*\(", src_text):
        pos = m.end() - 1
        depth = 0
        quote: str | None = None
        escaped = False
        end_idx = None
        for idx in range(pos, len(src_text)):
            ch = src_text[idx]
            if quote is not None:
                if escaped:
                    escaped = False
                elif ch == "\\":
                    escaped = True
                elif ch == quote:
                    quote = None
                continue
            if ch in ("'", '"', "`"):
                quote = ch
            elif ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    end_idx = idx + 1
                    break
        if end_idx is None:
            continue
        block = src_text[pos:end_idx]
        hits += len(re.findall(r"\bheading\s*\(", block))
    return hits


def load_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def cues_for_shot(cues: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [
        q
        for q in cues
        if float(q.get("end", 0) or 0) > start + 0.08 and float(q.get("start", 0) or 0) < end - 0.08
    ]


def suggest_cue_splits(shot: dict[str, Any], shot_cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Find interior cue boundaries that yield balanced sub-shots >= 3.5s each."""
    start = float(shot.get("start", 0) or 0)
    end = float(shot.get("end", 0) or 0)
    if end - start < 10.5 or len(shot_cues) < 2:
        return []
    candidates: list[dict[str, Any]] = []
    for idx in range(len(shot_cues) - 1):
        left_end = float(shot_cues[idx].get("end", 0) or 0)
        right_start = float(shot_cues[idx + 1].get("start", 0) or 0)
        cut_at = round((left_end + right_start) / 2.0, 3) if right_start >= left_end else round(left_end, 3)
        if cut_at - start >= 3.5 and end - cut_at >= 3.5:
            candidates.append(
                {
                    "cut_at": cut_at,
                    "left_span": round(cut_at - start, 2),
                    "right_span": round(end - cut_at, 2),
                    "before_text": str(shot_cues[idx].get("text", ""))[:40],
                    "after_text": str(shot_cues[idx + 1].get("text", ""))[:40],
                }
            )
    return candidates


def _legacy_stiff_tag(asset: dict[str, Any]) -> str | None:
    haystack = f"{asset.get('source_asset_id', '')} {asset.get('path', '')} {asset.get('library_ref', '')}"
    for suffix in LEGACY_STIFF_ACTOR_SUFFIXES:
        m = re.search(rf"([a-zA-Z0-9_]+{re.escape(suffix)})", haystack)
        if m:
            return m.group(1)
    return None


def analyze_project(project_dir: Path, series: str = "", episode: str = "") -> dict[str, Any]:
    score = load_json(project_dir / "score.json") or {}
    assets_doc = load_json(project_dir / "asset_manifest.json") or {}
    motion_audit = load_json(project_dir / "out/motion-audit.json") or {}

    shots = score.get("shots") or []
    cues = score.get("cues") or []
    sounds = score.get("sounds") or []
    sound_events = {str(s.get("event")) for s in sounds if isinstance(s, dict) and s.get("event")}
    spans = [round(max(0.0, float(s.get("end", 0) or 0) - float(s.get("start", 0) or 0)), 2) for s in shots]

    extra_long_shots: list[dict[str, Any]] = []
    dense_cue_shots: list[dict[str, Any]] = []
    long_tail_silences: list[dict[str, Any]] = []
    split_candidates_all: list[dict[str, Any]] = []

    for s in shots:
        sid = str(s.get("id", "?"))
        st = float(s.get("start", 0) or 0)
        en = float(s.get("end", 0) or 0)
        span = round(en - st, 2)
        sc = cues_for_shot(cues, st, en)
        if span >= 13.0:
            extra_long_shots.append({"shot": sid, "span": span, "cue_count": len(sc)})
        if len(sc) >= 4:
            dense_cue_shots.append({"shot": sid, "span": span, "cue_count": len(sc)})
        if sc:
            last_cue_end = max(float(q.get("end", 0) or 0) for q in sc)
            if en - last_cue_end >= 2.8:
                long_tail_silences.append({"shot": sid, "tail_gap": round(en - last_cue_end, 2)})
        splits = suggest_cue_splits(s, sc)
        if splits and span >= 11.0:
            split_candidates_all.append({"shot": sid, "span": span, "candidates": splits[:2]})

    uniform_cadence = len(spans) >= 4 and (max(spans) - min(spans) <= 2.2)
    signatures = [tuple((s.get("events") or {}).keys()) for s in shots if isinstance(s.get("events"), dict)]
    repeated_sig = len(signatures) >= 3 and len(set(signatures)) <= max(1, len(signatures) // 2)
    missing_arc = sum(1 for s in shots if not (s.get("motion_arc") or s.get("visual_anchor")))
    close_sound_events: list[dict[str, Any]] = []
    for s in shots:
        en = float(s.get("end", 0) or 0)
        for ev_name, ev_at in (s.get("events") or {}).items():
            if isinstance(ev_at, (int, float)) and en - float(ev_at) < 1.0 and ev_name in sound_events:
                close_sound_events.append({"shot": s.get("id"), "event": ev_name, "tail": round(en - float(ev_at), 2)})

    assets = assets_doc.get("assets") or []
    scale_contract = assets_doc.get("scale_contract") or {}
    sparse_assets = len(assets) <= 5
    missing_scale = scale_contract.get("enforcement") != "required"

    src_dir = project_dir / "src"
    phys_calls = 0
    raw_alive_hits = 0
    grounding_hits = 0
    sprite_calls = 0
    shape_calls = 0
    if src_dir.is_dir():
        for ts in src_dir.rglob("*.ts"):
            if "kit" in ts.parts:
                continue
            txt = ts.read_text(encoding="utf-8", errors="ignore")
            phys_calls += len(PHYSICS_RE.findall(txt))
            raw_alive_hits += len(RAW_ALIVE_RE.findall(txt))
            grounding_hits += len(GROUNDING_RE.findall(txt))
            sprite_calls += len(SPRITE_CALL_RE.findall(txt))
            shape_calls += len(SHAPE_CALL_RE.findall(txt))

    character_assets = [
        a
        for a in assets
        if isinstance(a, dict)
        and (
            str(a.get("visual_layer", "")) == "character"
            or bool(
                CHARACTER_ID_RE.search(
                    " ".join(
                        [
                            str(a.get("asset_id", "")),
                            str(a.get("path", "")),
                            str(a.get("author_id", "")),
                        ]
                    )
                )
            )
        )
    ]
    character_asset_ids = [str(a.get("asset_id", "")) for a in character_assets if a.get("asset_id")]
    actor_in_manifest = bool(character_assets)
    has_acting_atlas = any(
        isinstance(a, dict)
        and any(k in (str(a.get("asset_id", "")) + " " + str(a.get("path", ""))).lower() for k in ("acting_consult", "acting-sheet", "acting_v2", "acting_atlas", "walk_cycle_v2"))
        for a in assets
    )
    legacy_stiff_used = sorted(
        {
            tag
            for a in character_assets
            for tag in (_legacy_stiff_tag(a),)
            if tag
        }
    )

    actor_kit_calls = 0
    actor_in_code = False
    hard_cut_switches = 0
    rapid_actor_switches = 0
    bust_behind_hollow_desk = 0
    heading_inside_camera = 0
    if src_dir.is_dir():
        ts_sources = [
            (ts, ts.read_text(encoding="utf-8", errors="ignore"))
            for ts in sorted(src_dir.rglob("*.ts"))
            if "kit" not in ts.parts
        ]
        person_called_outside_puppets = any(
            re.search(r"\bperson\s*\(", txt)
            for ts, txt in ts_sources
            if ts.name != "puppets.ts"
        )
        for ts, txt in ts_sources:
            actor_kit_calls += len(ACTOR_KIT_RE.findall(txt))
            if ACTOR_CODE_RE.search(txt):
                actor_in_code = True
            if ts.name != "puppets.ts" or person_called_outside_puppets:
                hard_cut_switches += len(HARD_CUT_ACTOR_RE.findall(txt))
            rapid_actor_switches += count_rapid_actor_switches(txt)
            if ts.name != "puppets.ts":
                bust_behind_hollow_desk += count_bust_behind_hollow_desk(txt)
                heading_inside_camera += count_heading_inside_camera(txt)

    has_actor = actor_in_manifest or actor_in_code
    uses_actor_kit = actor_kit_calls > 0
    stiff_actor_risk = bool(
        has_actor
        and (
            not uses_actor_kit
            or hard_cut_switches > 0
            or rapid_actor_switches > 0
            or bust_behind_hollow_desk > 0
        )
    )

    low_physics = phys_calls < 15
    geometry_heavy = sprite_calls <= 6 and shape_calls >= 30

    recommended_layers: list[str] = []
    if extra_long_shots or dense_cue_shots:
        recommended_layers.append("script")
    if uniform_cadence or repeated_sig or split_candidates_all or missing_arc == len(shots) or heading_inside_camera > 0:
        recommended_layers.append("storyboard")
    if sparse_assets or geometry_heavy:
        recommended_layers.append("assets")
    if low_physics or raw_alive_hits > 0 or grounding_hits == 0:
        recommended_layers.append("animation")
    if stiff_actor_risk:
        recommended_layers.append("actor_performance")

    opp_score = (
        len(extra_long_shots) * 12
        + len(dense_cue_shots) * 8
        + (15 if uniform_cadence else 0)
        + (10 if repeated_sig else 0)
        + (15 if sparse_assets else 0)
        + (12 if geometry_heavy else 0)
        + (18 if low_physics else 0)
        + raw_alive_hits * 4
        + (6 if grounding_hits == 0 else 0)
        + (10 if (has_actor and not uses_actor_kit) else 0)
        + (6 if (has_actor and (hard_cut_switches > 0 or rapid_actor_switches > 0 or bust_behind_hollow_desk > 0 or (legacy_stiff_used and not has_acting_atlas))) else 0)
    )

    return {
        "series": series,
        "episode": episode,
        "project": str(project_dir),
        "shot_count": len(shots),
        "shot_spans": spans,
        "duration": round(float(score.get("duration", 0) or 0), 2),
        "opportunity_score": opp_score,
        "recommended_layers": recommended_layers,
        "script_opportunities": {
            "extra_long_shots": extra_long_shots,
            "dense_cue_shots": dense_cue_shots,
            "long_tail_silences": long_tail_silences,
        },
        "storyboard_opportunities": {
            "uniform_cadence": uniform_cadence,
            "span_spread": round(max(spans) - min(spans), 2) if spans else 0.0,
            "repeated_event_signature": repeated_sig,
            "shots_missing_arc_or_anchor": missing_arc,
            "close_sound_events": close_sound_events,
            "zero_drift_cue_split_candidates": split_candidates_all,
            "heading_inside_camera": heading_inside_camera,
        },
        "asset_opportunities": {
            "asset_count": len(assets),
            "sparse_assets": sparse_assets,
            "scale_contract_enforced": not missing_scale,
            "sprite_calls": sprite_calls,
            "shape_calls": shape_calls,
            "geometry_heavy": geometry_heavy,
        },
        "animation_opportunities": {
            "physics_calls": phys_calls,
            "low_physics": low_physics,
            "raw_alive_breath_hits": raw_alive_hits,
            "grounding_calls": grounding_hits,
            "motion_audit_codes": list((motion_audit.get("locator_codes") or {}).keys())
            if isinstance(motion_audit, dict)
            else [],
        },
        "actor_opportunities": {
            "has_actor": has_actor,
            "character_asset_ids": character_asset_ids,
            "uses_actor_kit": uses_actor_kit,
            "actor_kit_calls": actor_kit_calls,
            "has_acting_atlas": has_acting_atlas,
            "uses_legacy_stiff_poses": legacy_stiff_used,
            "hard_cut_pose_switches": hard_cut_switches,
            "rapid_actor_switches": rapid_actor_switches,
            "bust_behind_hollow_desk": bust_behind_hollow_desk,
            "stiff_actor_risk": stiff_actor_risk,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, help="Inspect a single project directory")
    parser.add_argument("--workspace", type=Path, default=Path("."), help="Workspace root for --summary")
    parser.add_argument("--summary", action="store_true", help="Scan active projects from workbench.yaml")
    parser.add_argument("--top", type=int, default=20, help="Top N candidates to print in --summary mode")
    parser.add_argument("--include-vivid", action="store_true", help="Include already vivid episodes in --summary")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON output")
    args = parser.parse_args()

    if args.project:
        report = analyze_project(args.project)
        print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0

    if not args.summary:
        parser.error("Provide --project <path> or --summary")

    wb = yaml.safe_load((args.workspace / "workbench.yaml").read_text(encoding="utf-8")) or {}
    rows: list[dict[str, Any]] = []
    for sid, sdata in (wb.get("series") or {}).items():
        for eid, edata in (sdata.get("episodes") or {}).items():
            proj_rel = edata.get("active_project") or edata.get("project") or ""
            if not proj_rel:
                continue
            if not args.include_vivid and "newstandard_vivid_" in proj_rel:
                continue
            proj = args.workspace / proj_rel
            if proj.is_dir():
                rows.append(analyze_project(proj, series=sid, episode=eid))

    rows.sort(key=lambda r: (-r["opportunity_score"], r["series"], r["episode"]))
    summary = {
        "scanned": len(rows),
        "with_script_opportunities": sum(1 for r in rows if "script" in r["recommended_layers"]),
        "with_storyboard_opportunities": sum(1 for r in rows if "storyboard" in r["recommended_layers"]),
        "with_asset_opportunities": sum(1 for r in rows if "assets" in r["recommended_layers"]),
        "with_animation_opportunities": sum(1 for r in rows if "animation" in r["recommended_layers"]),
        "with_actor_opportunities": sum(1 for r in rows if "actor_performance" in r["recommended_layers"]),
        "top": rows[: args.top],
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2 if args.pretty else None))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
