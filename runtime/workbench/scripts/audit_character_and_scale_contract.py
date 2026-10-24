#!/usr/bin/env python3
"""Locate character assembly and composition-scale review debt.

This is a navigation tool, not a quality gate. A programmatic helper can be a
valid small accessory; a literal image width can be acceptable in a distant
establishing shot. The report exists so each episode can be reopened with the
actual frame and its narrative responsibility.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

import yaml


SCHEMA = "paper_theatre_character_scale_audit/v1"
PERSON_NOUN = re.compile(
    r"(?:person|patient|woman|man|doctor|clinician|puppet|seated|human|"
    r"child|elder|family|carer|body|portrait|diner|walker|figure|"
    r"readingbook|reader)",
    re.IGNORECASE,
)
GEOMETRY = (
    "oval(",
    "tornEllipse(",
    "poly(",
    "paper(",
    "cutout(",
    "limb(",
    "arm(",
    "piece(",
    "shape(",
)
COMPLEX_OBJECT = re.compile(
    r"(?:anatomy|organ|pituitary|thyroid|kidney|uterus|ovary|breast|heart|"
    r"liver|lung|vessel|artery|joint|brain|adrenal|cortisol|胰岛|垂体|甲状腺|"
    r"肾|子宫|卵巢|乳腺|心脏|肝|肺|血管|关节|肾上腺)",
    re.IGNORECASE,
)
PERSON_OBJECT = re.compile(
    r"(?:person|patient|woman|man|doctor|clinician|child|elder|pregnant|"
    r"人物|患者|医生|儿童|老人|孕妇)",
    re.IGNORECASE,
)
PERSON_STRUCTURE = re.compile(
    r"\b(?:head|hair|face|eye|eyes|neck|torso|body|shoulder|arm|elbow|"
    r"hand|waist|hip|thigh|leg|knee|foot|feet|shoe|shirt|pants|dress)\b",
    re.IGNORECASE,
)


def function_spans(text: str) -> list[tuple[str, int, int, str]]:
    spans: list[tuple[str, int, int, str]] = []
    for match in re.finditer(
        r"(?m)^(?:export\s+)?function\s+([A-Za-z_$][\w$]*)\s*\(", text
    ):
        name = match.group(1)
        opening = text.find("{", match.end() - 1)
        if opening < 0:
            continue
        depth = 0
        closing = len(text)
        for index in range(opening, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    closing = index + 1
                    break
        spans.append((name, match.start(), closing, text[match.start() : closing]))
    return spans


def project_sources(project: Path) -> list[Path]:
    src = project / "src"
    if not src.is_dir():
        return []
    preferred = [src / "episodeshots.ts", src / "story_shots.ts"]
    return [path for path in preferred if path.is_file()]


def locate_project(workspace: Path, raw: str) -> Path:
    path = Path(raw).expanduser()
    return path if path.is_absolute() else workspace / path


def manifest_assets(project: Path) -> dict[str, dict[str, Any]]:
    path = project / "asset_manifest.json"
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {
        item["asset_id"]: item
        for item in value.get("assets", [])
        if isinstance(item, dict) and item.get("asset_id")
    }


def inspect_source(text: str, assets: dict[str, dict[str, Any]]) -> dict[str, Any]:
    programmatic: list[dict[str, Any]] = []
    for name, start, _end, body in function_spans(text):
        geometry_terms = [term for term in GEOMETRY if term in body]
        structure_count = len(
            {match.group(0).lower() for match in PERSON_STRUCTURE.finditer(body)}
        )
        # Function names drift: a body builder may be called `walk`, `diner`
        # or `walkingFigure`. Treat a multi-part human silhouette as a
        # locator even when its name is not a person noun.
        human_structure = len(geometry_terms) >= 3 and structure_count >= 3
        if not PERSON_NOUN.search(name) and not human_structure:
            continue
        if re.search(r"(?:icon|badge|symbol)$", name, re.IGNORECASE):
            continue
        # A complete raster figure plus a local indicator is the intended
        # production path, not a programmatic body assembly.
        if re.search(r"\.image\s*\(|\bimg\s*\(", body):
            continue
        terms = geometry_terms
        if len(terms) < 2:
            continue
        call_count = max(
            0, len(re.findall(r"(?<![\w$])" + re.escape(name) + r"\s*\(", text)) - 1
        )
        programmatic.append(
            {
                "helper": name,
                "line": text.count("\n", 0, start) + 1,
                "call_sites": call_count,
                "construction_terms": terms,
                "human_structure_terms": structure_count,
                "reason": "角色由多个局部图形构造，需按完整人物素材准入复核",
            }
        )

    small_assets: list[dict[str, Any]] = []
    width_pattern = re.compile(
        r"""(?:s\.image|img\s*\(\s*s\s*,)\s*
        (?:
          ['"](?P<id1>[^'"]+)['"]\s*,\s*\{
          [^}]*?\bw\s*:\s*(?P<w1>\d+(?:\.\d+)?)
          |
          ['"](?P<id2>[^'"]+)['"]\s*,\s*
          [^,]+,\s*[^,]+,\s*(?P<w2>\d+(?:\.\d+)?)
        )""",
        re.VERBOSE | re.DOTALL,
    )
    for match in width_pattern.finditer(text):
        asset_id = match.group("id1") or match.group("id2")
        width = float(match.group("w1") or match.group("w2"))
        if not asset_id:
            continue
        visual = str((assets.get(asset_id) or {}).get("visual_meaning", ""))
        semantic = asset_id + " " + visual
        if PERSON_OBJECT.search(semantic) and width < 260:
            reason = "完整人物的显式宽度低于主/次人物全身边界复核线"
        elif COMPLEX_OBJECT.search(semantic) and width < 240:
            reason = "复杂医学结构以显式窄宽出现，需核对可读性而不是只加标签"
        else:
            continue
        small_assets.append(
            {
                "asset_id": asset_id,
                "line": text.count("\n", 0, match.start()) + 1,
                "explicit_width": width,
                "reason": reason,
            }
        )

    return {
        "programmatic_character_helpers": programmatic,
        "small_explicit_assets": small_assets,
    }


def audit(workspace: Path) -> dict[str, Any]:
    config_path = workspace / "workbench.yaml"
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    rows: list[dict[str, Any]] = []
    for series_id, series in (config.get("series") or {}).items():
        for episode_id, episode in (series.get("episodes") or {}).items():
            project = locate_project(workspace, episode["project"])
            sources = project_sources(project)
            findings: list[dict[str, Any]] = []
            for source in sources:
                current = inspect_source(source.read_text(encoding="utf-8"), manifest_assets(project))
                for kind, values in current.items():
                    for value in values:
                        findings.append(
                            {
                                **value,
                                "kind": kind,
                                "source": str(source.relative_to(workspace)),
                            }
                        )
            rows.append(
                {
                    "series_id": series_id,
                    "episode_id": episode_id,
                    "project": str(project.relative_to(workspace)),
                    "sources": [str(path.relative_to(workspace)) for path in sources],
                    "review_locators": findings,
                }
            )
    affected = [row for row in rows if row["review_locators"]]
    return {
        "schema": SCHEMA,
        "workspace": str(workspace),
        "episodes_scanned": len(rows),
        "episodes_with_locators": len(affected),
        "programmatic_character_helpers": sum(
            item["kind"] == "programmatic_character_helpers"
            for row in affected
            for item in row["review_locators"]
        ),
        "small_explicit_assets": sum(
            item["kind"] == "small_explicit_assets"
            for row in affected
            for item in row["review_locators"]
        ),
        "rows": rows,
        "note": (
            "定位材料不是质量结论。程序绘制的小型附件可能成立；显式宽度也可能处在远景。"
            "必须回到当前成片判断人物身份、动作、复杂度和叙事重量。"
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path)
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    result = audit(args.workspace.resolve())
    rendered = json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered + "\n", encoding="utf-8")
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
