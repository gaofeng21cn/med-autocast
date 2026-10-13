#!/usr/bin/env python3
"""Refuse deliveries whose episodes are copies of a series template.

An episode must own its direction and its shot implementation. Sharing the kit
is correct — the kit is animation primitives. Sharing the *director* means
every episode in a series stages the same way no matter what the episode is
about, which is the failure this check exists to prevent.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

import yaml

# Files that legitimately hold series-wide vocabulary rather than staging.
# Anything outside this set may not be byte-identical across episodes.
ALLOWED_SHARED = {
    # Vocabulary: how a paper organ, page, folder or room is drawn. How an
    # episode *stages* them is never in these files.
    "series_grammar.ts",
    "paper_objects.ts",
    "six_objects.ts",
    "episode-kit.ts",
    "meal_objects.ts",
    "main.ts",
}

NOISE = re.compile(r"//[^\n]*|/\*.*?\*/", re.S)


def digest(text: str) -> str:
    """Hash with comments removed so formatting is not mistaken for
    difference while real staging copies are still caught."""
    stripped = "\n".join(l.rstrip() for l in NOISE.sub("", text).splitlines() if l.strip())
    return hashlib.sha256(stripped.encode()).hexdigest()[:12]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, default=Path.cwd())
    ap.add_argument("--series", default="")
    ap.add_argument("--report-only", action="store_true")
    args = ap.parse_args()

    config = yaml.safe_load((args.workspace / "workbench.yaml").read_text()) or {}
    directions: dict = defaultdict(list)
    shots: dict = defaultdict(list)
    independent: list[str] = []

    for sid, series in (config.get("series") or {}).items():
        if args.series and sid != args.series:
            continue
        for eid, ep in (series.get("episodes") or {}).items():
            key = f"{sid}/{eid}"
            src = (args.workspace / ep["project"] / "src").resolve()
            if not src.is_dir():
                continue
            direction = src / "scene_directions.json"
            if direction.is_file():
                directions[(sid, digest(direction.read_text()))].append(key)
            own = False
            for f in sorted(src.rglob("*.ts")):
                if f.name in ALLOWED_SHARED or "kit" in f.parts:
                    continue
                shots[(sid, digest(f.read_text()))].append(key)
                own = True
            if own:
                independent.append(key)

    dup_dir = {k: v for k, v in directions.items() if len(v) > 1}
    dup_shot = {k: v for k, v in shots.items() if len(v) > 1}
    report = {
        "schema": "episode_independence/v1",
        "episodes_with_own_shots": len(independent),
        "duplicated_directions": [{"series": k[0], "episodes": v} for k, v in dup_dir.items()],
        "duplicated_shot_code": [{"series": k[0], "episodes": v} for k, v in dup_shot.items()],
        "independent": sorted(independent),
    }
    out = args.workspace / "work/episode-independence.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    blocked = not dup_dir and not dup_shot
    print(
        json.dumps(
            {
                "episodes_with_own_shots": len(independent),
                "duplicated_direction_groups": len(dup_dir),
                "duplicated_shot_groups": len(dup_shot),
                "verdict": "ok" if blocked else "blocked",
                "report": str(out),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    if not blocked and not args.report_only:
        for row in report["duplicated_directions"]:
            print(f"导演稿重复: {row['series']} {len(row['episodes'])} 集", file=sys.stderr)
        for row in report["duplicated_shot_code"]:
            print(f"镜头代码重复: {row['series']} {len(row['episodes'])} 集", file=sys.stderr)
    return 0 if blocked else 1


if __name__ == "__main__":
    raise SystemExit(main())
