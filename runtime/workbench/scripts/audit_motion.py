#!/usr/bin/env python3
"""Audit a paper-theatre Score for motion-direction and directing debts.

This is a locating report, not a semantic approval gate.  It reads the current
Score, identifies repeated shot recipes, missing action-arc evidence, long
event gaps and absent representative-shot metadata, then writes a stable JSON
report.  All findings are non-blocking so directors can continue with a
partial or exploratory score.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SCHEMA = "medical_motion_audit/v1"
PHASES = {
    "prepare": re.compile(r"prepare|ready|enter|arrive|open|cover|start|begin|取出|进入|打开|准备|到达", re.I),
    "action": re.compile(r"action|move|slide|spread|reveal|contact|file|stow|leave|align|clip|stimulus|gather|more|less|揭示|移动|侧移|展开|接触|插入|收纳|离开|对齐|固定|检查|进入", re.I),
    "reaction": re.compile(r"reaction|react|response|review|compare|change|result|exam|review|uncovered|revealed|反应|比较|变化|结果|复核|呈现", re.I),
    "settle": re.compile(r"settle|done|hold|rest|finish|read|stable|落定|停留|保持|完成|静止|读", re.I),
}
DIRECTION_TOKENS = re.compile(
    r"left|right|up|down|横移|侧移|上移|下移|推近|推进|拉远|旋转|翻|展开|折叠|进入|退出|交接|接棒|揭示|放大|缩小",
    re.I,
)
REQUIRED_RECIPE_FIELDS = ("audience_read", "visual_anchor", "primary_motion", "motion_arc")


def canonical(value: Any) -> str:
    if isinstance(value, dict):
        value = {str(k): value[k] for k in sorted(value)}
    return re.sub(r"\s+", " ", json.dumps(value, ensure_ascii=False, sort_keys=True)).strip()


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def load_score(project: Path, explicit: Path | None) -> tuple[dict, Path]:
    score_path = explicit or project / "score.json"
    if not score_path.is_absolute():
        score_path = project / score_path
    payload = json.loads(score_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("score.json 必须是对象")
    return payload, score_path


def recipe_text(recipe: Any) -> str:
    if isinstance(recipe, dict):
        return " ".join(str(recipe.get(key, "")) for key in REQUIRED_RECIPE_FIELDS)
    return str(recipe or "")


def event_points(shot: dict) -> list[tuple[str, float, str]]:
    points: list[tuple[str, float, str]] = []
    for name, raw in (shot.get("events") or {}).items():
        if isinstance(raw, dict):
            value = raw.get("time", raw.get("at"))
            phase = str(raw.get("phase", ""))
        else:
            value = raw
            phase = ""
        try:
            local = float(value)
        except (TypeError, ValueError):
            continue
        if local < 0:
            continue
        points.append((str(name), local, phase))
    return sorted(points, key=lambda item: item[1])


def infer_phases(points: list[tuple[str, float, str]], recipe: Any) -> dict[str, list[str]]:
    text = recipe_text(recipe)
    phases: dict[str, list[str]] = {phase: [] for phase in PHASES}
    for name, _time, explicit in points:
        value = f"{name} {explicit}"
        matched = [phase for phase, pattern in PHASES.items() if pattern.search(value)]
        if not matched:
            # A named action still gives evidence that the shot is not empty;
            # its exact semantic phase remains a director decision.
            continue
        for phase in matched:
            phases[phase].append(name)
    for phase, pattern in PHASES.items():
        if pattern.search(text):
            phases[phase].append("recipe_text")
    return phases


def debt(code: str, detail: str, *, shot: str | None = None, owner: str = "story-directing", **extra: Any) -> dict:
    item = {
        "code": code,
        "owner_stage": owner,
        "blocks_stage_progress": False,
        "detail": detail,
    }
    if shot:
        item["shot"] = shot
    item.update(extra)
    return item


def audit(project: Path, score_path: Path | None = None) -> dict:
    score, resolved_score = load_score(project, score_path)
    shots = [shot for shot in score.get("shots", []) if isinstance(shot, dict)]
    duration = float(score.get("duration", 0) or 0)
    debts: list[dict] = []
    signatures: defaultdict[str, list[str]] = defaultdict(list)
    event_signatures: defaultdict[str, list[str]] = defaultdict(list)
    directions: Counter[str] = Counter()
    per_shot: list[dict] = []

    previous_end = 0.0
    for index, shot in enumerate(shots):
        shot_id = str(shot.get("id", f"shot-{index + 1}"))
        try:
            start = float(shot.get("start", 0))
            end = float(shot.get("end", start))
        except (TypeError, ValueError):
            start, end = 0.0, 0.0
        span = max(0.0, end - start)
        points = event_points(shot)
        recipe = shot.get("shot_recipe", shot.get("recipe"))
        recipe_key = canonical(recipe) if recipe else ""
        if recipe_key:
            signatures[recipe_key].append(shot_id)
        event_key = canonical([name for name, _time, _phase in points])
        if event_key:
            event_signatures[event_key].append(shot_id)
        text = recipe_text(recipe)
        for token in DIRECTION_TOKENS.findall(text):
            directions[token.lower()] += 1
        phases = infer_phases(points, recipe)
        missing_phases = [phase for phase in ("prepare", "action", "reaction", "settle") if not phases[phase]]
        if isinstance(recipe, dict):
            for field in REQUIRED_RECIPE_FIELDS:
                if not str(recipe.get(field, "")).strip():
                    debts.append(debt("shot_recipe_missing_field", f"缺少导演交接字段 {field}", shot=shot_id))
        elif not text:
            debts.append(debt("shot_recipe_missing", "镜头没有自然语言导演交接，无法判断观看任务与动作责任", shot=shot_id))
        if missing_phases:
            debts.append(debt(
                "motion_phase_evidence_incomplete",
                "动作弧缺少 " + ", ".join(missing_phases) + " 的事件或导演说明",
                shot=shot_id,
                missing_phases=missing_phases,
            ))
        if not points:
            debts.append(debt("shot_has_no_named_events", "镜头没有命名事件；可能是有意静止，也可能无法定位动作落点", shot=shot_id, owner="visual-review"))
        event_times = [time for _name, time, _phase in points if 0 <= time <= span]
        gaps = []
        if event_times:
            anchors = [0.0, *event_times, span]
            gaps = [round(b - a, 3) for a, b in zip(anchors, anchors[1:]) if b >= a]
        max_gap = max(gaps, default=span)
        if span >= 6 and max_gap >= max(2.5, span * 0.45):
            debts.append(debt(
                "long_motion_dead_zone",
                f"最长事件间隔 {max_gap:.2f}s；需确认这是有意呼吸/阅读停留，还是没有发展与结果",
                shot=shot_id,
                owner="visual-review",
                max_gap=max_gap,
            ))
        if index and start < previous_end - 0.02:
            debts.append(debt("shot_overlap", f"镜头与前一镜重叠 {previous_end - start:.3f}s", shot=shot_id, owner="media-production"))
        if start > previous_end + 0.02:
            debts.append(debt("shot_gap", f"镜头之间存在 {start - previous_end:.3f}s 未归属区间", shot=shot_id, owner="story-directing"))
        previous_end = max(previous_end, end)
        per_shot.append({
            "id": shot_id,
            "start": start,
            "end": end,
            "duration": round(span, 3),
            "event_count": len(points),
            "event_names": [name for name, _time, _phase in points],
            "max_event_gap": round(max_gap, 3),
            "phase_coverage": {phase: bool(values) for phase, values in phases.items()},
            "missing_phases": missing_phases,
        })

    for key, ids in signatures.items():
        if len(ids) > 1:
            debts.append(debt(
                "repeated_shot_recipe",
                f"多个镜头共享相同导演交接（{len(ids)} 个）",
                owner="story-directing",
                shots=ids,
                signature_sha256=hashlib.sha256(key.encode("utf-8")).hexdigest(),
            ))
    for key, ids in event_signatures.items():
        if len(ids) > 1 and len(shots) >= 4:
            debts.append(debt("repeated_event_signature", f"多个镜头的事件命名与顺序相同（{len(ids)} 个）", owner="story-directing", shots=ids))

    representative = score.get("signature_shot") or score.get("representative_shot")
    if not representative:
        debts.append(debt(
            "representative_shot_unregistered",
            "Score 没有登记 signature_shot/representative_shot；本集缺少可先验收的代表镜头入口",
            owner="story-directing",
        ))
    if len(shots) >= 3 and len(directions) <= 1:
        debts.append(debt(
            "motion_direction_low_diversity",
            "全片导演文字只出现一种或更少的空间动作方向；请确认不是整片同向进入/慢推",
            owner="story-directing",
            direction_counts=dict(directions),
        ))
    def has_carrier(shot: dict) -> bool:
        if isinstance(shot.get("carrier"), str) and shot.get("carrier", "").strip():
            return True
        recipe = shot.get("shot_recipe")
        return isinstance(recipe, dict) and isinstance(recipe.get("carrier"), str) and bool(recipe.get("carrier", "").strip())

    if shots and not all(has_carrier(shot) for shot in shots):
        debts.append(debt("carrier_continuity_unreported", "至少一个镜头没有登记跨镜承接物，需在邻镜审片确认桌面状态是否连续", owner="story-directing"))
    if shots and len(shots) > 1 and not any("transition" in shot for shot in shots[1:]):
        debts.append(debt("transition_intent_unreported", "镜头之间未登记转场/承接意图；允许硬切，但需要导演在邻镜中说明关系", owner="visual-review"))
    if duration and previous_end > duration + 0.02:
        debts.append(debt("score_exceeds_duration", "镜头尾部超出 Score duration", owner="media-production"))

    repeated_count = sum(max(0, len(ids) - 1) for ids in signatures.values())
    return {
        "schema": SCHEMA,
        "status": "completed",
        "project": str(project),
        "score": str(resolved_score),
        "score_sha256": sha256(resolved_score),
        "duration": duration,
        "shot_count": len(shots),
        "event_count": sum(row["event_count"] for row in per_shot),
        "unique_recipe_count": len(signatures),
        "recipe_repetition_ratio": round(repeated_count / len(shots), 4) if shots else 0,
        "direction_counts": dict(directions),
        "representative_shot": representative,
        "shots": per_shot,
        "quality_debt": debts,
        "summary": {
            "quality_debt_count": len(debts),
            "blocking_debt_count": 0,
            "next_owner_stages": sorted({item["owner_stage"] for item in debts}),
            "progress_first": True,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--score", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        report = audit(args.project.resolve(), args.score)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        report = {
            "schema": SCHEMA,
            "status": "diagnostic",
            "project": str(args.project.resolve()),
            "quality_debt": [debt("motion_audit_unavailable", str(exc), owner="story-directing")],
            "summary": {"quality_debt_count": 1, "blocking_debt_count": 0, "progress_first": True},
        }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
