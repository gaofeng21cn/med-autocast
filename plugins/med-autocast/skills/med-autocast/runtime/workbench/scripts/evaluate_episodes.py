#!/usr/bin/env python3
"""Locate source signals for episode review; never score animation quality.

Calls and imports cannot establish what a viewer sees. A function may be unused,
draw the wrong specimen, or perform no visible action. This report locates code
for an episode-specific review of the actual candidate and its narration.
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

    # Lexical counts include vocabulary and possibly unused code. They are
    # navigation hints, not an estimate of visible action or explanatory quality.
    density = action_calls / n
    problems = []
    if density < 0.35:
        problems.append("已登记动作函数调用较少；需看实际镜头，可能存在自定义动作")
    if prop_calls / n < 0.2:
        problems.append("容器/固定件函数调用较少；不代表镜头需要增加容器")
    if cams and dynamic_cams / max(1, len(cams)) < 0.34:
        problems.append("匹配到的相机代码多为固定机位；固定机位本身不是缺陷")
    if labels / n > 2.4:
        problems.append("文字调用较多；需核对实际可见内容及其解释职责")
    if env_set <= 2 and n >= 4:
        problems.append("匹配到的环境调用较少；自定义布景/有意保持同一空间未计入")
    if not event_driven:
        problems.append("未匹配到命名事件读取；需核对实际时钟与旁白落点")
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
        "baseline_score": None,
        "review_locators": problems,
        "verdict": "semantic_review_required",
        "explanation": "源码词频不能证明对象正确、画面表意或动作实际发生；必须审查当前成片",
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

    order = sorted(report.items())
    summary = {"episodes": len(order), "semantic_review_required": len(order),
               "quality_approved_by_this_tool": 0}
    out = {"schema": "episode_source_review_locators/v2", "summary": summary, "episodes": dict(order)}
    dest = args.output or (args.workspace / "work/episode-animation-diagnosis.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(json.dumps({"summary": summary, "output": str(dest)}, ensure_ascii=False))
    for key, v in order:
        print(f"{v['verdict']} {key}")


if __name__ == "__main__":
    main()
