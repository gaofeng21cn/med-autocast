#!/usr/bin/env python3
"""Per-episode animation diagnosis from real source signals.

Every number here is read out of the episode's own TypeScript or score file, so
the report says what the code actually does rather than what a contact sheet
looks like at a glance. The output is one diagnosis per episode, ordered by how
much the animation body needs rewriting.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

ACTIONS = [
    "liftCorner", "tearSheet", "foldPanel", "turnPage", "pullStrip",
    "unrollTape", "wrapAround", "cutOpen", "penStroke", "snapClip",
    "dropSheet", "unfoldMap", "handmadePiece",
]
PROPS = ["paperFolder", "pocket", "hinge", "clipFastener"]
PATTERNS = [
    "arc", "unfoldRevealCompareStow", "walkArriveHandoff", "layerReveal",
    "contactShadow",
]


def source_of(project: Path) -> tuple[str, list[str]]:
    """Return concatenated shot source and the files it came from."""
    src = project / "src"
    if not src.is_dir():
        return "", []
    texts, files = [], []
    for path in sorted(src.rglob("*.ts")):
        if "/kit/" in str(path) or path.name == "main.ts":
            continue
        texts.append(path.read_text(encoding="utf-8"))
        files.append(path.name)
    return "\n".join(texts), files


def diagnose(project: Path) -> dict:
    text, files = source_of(project)
    score_path = project / "score.json"
    score = json.loads(score_path.read_text()) if score_path.is_file() else {}
    shots = score.get("shots") or []
    n = max(1, len(shots))

    action_hits = {a: len(re.findall(r"\b%s\s*\(" % a, text)) for a in ACTIONS}
    pattern_hits = {p: len(re.findall(r"\b%s\s*\(" % p, text)) for p in PATTERNS}
    prop_hits = {p: len(re.findall(r"\b%s\s*\(" % p, text)) for p in PROPS}
    # A choreography pattern is as much an action as a raw paper action: it is
    # the arc that makes contact, reaction and settle visible. Counting only
    # actions.ts would under-report every episode written against patterns.ts.
    action_calls = sum(action_hits.values()) + sum(pattern_hits.values())
    prop_calls = sum(prop_hits.values())

    # Camera: does the frame actually travel, or sit at one anchor?
    cams = re.findall(r"camera\s*:\s*\([^)]*\)\s*=>\s*\(\{([^}]*)\}\)", text)
    cam_fields = []
    for body in cams:
        body_l = body.lower()
        if any(k in body_l for k in ("ease(", "phase(", "pushin", "pullout", "mix(", "tiltdrift", "camerafor")):
            cam_fields.append("dynamic")
        else:
            cam_fields.append("static")
    dynamic_cams = cam_fields.count("dynamic")

    # Text drawn inside the picture, excluding subtitles/brand handled by kit.
    labels = len(re.findall(r"\bs\.text\(", text)) + len(re.findall(r"\bstage\.text\(", text))
    # Environment plates: repeated env(id) calls mean a fixed stage.
    envs = re.findall(r"\benv\(\s*[^,]+,\s*'([^']+)'\s*\)", text)
    envs += re.findall(r"\benvironment\(\s*[^,]+,\s*'([^']+)'\s*\)", text)
    env_set = len(set(envs))
    # Event-driven staging reads the score clock; guessed timing does not.
    event_driven = bool(re.search(r"beat\.events|\bev\(", text))
    depth_on = bool(re.search(r"\bdepth\s*:", text)) or "staging" in text

    # Per-shot action density is the single most useful rewrite signal.
    density = action_calls / n
    problems = []
    if density < 0.35:
        problems.append("动作密度低：几乎只有进入与停留")
    if prop_calls / n < 0.2:
        problems.append("缺少纸件容器与固定件")
    if cams and dynamic_cams / max(1, len(cams)) < 0.34:
        problems.append("多数镜头机位固定")
    if labels / n > 2.4:
        problems.append("画内文字偏多，表达依赖标签")
    if env_set <= 2 and n >= 4:
        problems.append("舞台单一，空间没有变化")
    if not event_driven:
        problems.append("动作时点未由 score 事件驱动")

    score_val = (
        min(40, density * 44)
        + min(18, prop_calls / n * 26)
        + min(16, (dynamic_cams / max(1, len(cams))) * 16 if cams else 8)
        + min(12, env_set * 3)
        + (8 if event_driven else 0)
        + (10 if depth_on else 0)
    )
    return {
        "project": str(project),
        "files": files,
        "shots": len(shots),
        "action_calls": action_calls,
        "prop_calls": prop_calls,
        "action_density": round(density, 2),
        "actions_used": [a for a, c in action_hits.items() if c],
        "patterns_used": [p for p, c in pattern_hits.items() if c],
        "cameras": len(cams),
        "cameras_dynamic": dynamic_cams,
        "labels": labels,
        "environments": sorted(set(envs)),
        "event_driven": event_driven,
        "baseline_score": round(score_val, 1),
        "problems": problems,
        "verdict": "rewrite" if score_val < 55 else "upgrade" if score_val < 75 else "hold",
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, default=Path.cwd())
    ap.add_argument("--series", default="")
    ap.add_argument("--output", type=Path)
    args = ap.parse_args()

    config = yaml.safe_load((args.workspace / "workbench.yaml").read_text()) or {}
    report = {}
    for sid, series in (config.get("series") or {}).items():
        if args.series and sid != args.series:
            continue
        for eid, ep in (series.get("episodes") or {}).items():
            project = (args.workspace / ep["project"]).resolve()
            report[f"{sid}/{eid}"] = diagnose(project)

    order = sorted(report.items(), key=lambda kv: kv[1]["baseline_score"])
    summary = {
        "rewrite": sum(1 for _, v in order if v["verdict"] == "rewrite"),
        "upgrade": sum(1 for _, v in order if v["verdict"] == "upgrade"),
        "hold": sum(1 for _, v in order if v["verdict"] == "hold"),
    }
    out = {"schema": "episode_animation_diagnosis/v1", "summary": summary, "episodes": dict(order)}
    dest = args.output or (args.workspace / "work/episode-animation-diagnosis.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"summary": summary, "output": str(dest)}, ensure_ascii=False))
    for key, v in order:
        print(f"{v['baseline_score']:>5} {v['verdict']:<8} {key}")


if __name__ == "__main__":
    main()
