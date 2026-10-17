#!/usr/bin/env python3
"""定位代码动画中需要核对安全区归属的低层文字调用。

这是导航和质量债工具，不是阻断器：Canvas 图形里的自由文字仍然合法，
但纸上标题、标签和注释应改用 ``textBox``/``Stage.label``，再由真实预览
检查字形、纸件边界和遮挡。
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml


RAW = re.compile(r"\b(?:s|stage)\.text\s*\(")
BOX = re.compile(r"\b(?:textBox|cardTitle|tagLabel)\s*\(")
LABEL = re.compile(r"\.(?:label)\s*\(")


def project_rows(workspace: Path, project_filter: str | None = None):
    config = yaml.safe_load((workspace / "workbench.yaml").read_text()) or {}
    rows = []
    for series, spec in config.get("series", {}).items():
        for episode, item in (spec.get("episodes") or {}).items():
            key = f"{series}/{episode}"
            if project_filter and key != project_filter:
                continue
            project = (workspace / item["project"]).resolve()
            sources = sorted(project.glob("src/**/*.ts"))
            raw = []
            explicit = 0
            for source in sources:
                text = source.read_text(errors="replace")
                for match in RAW.finditer(text):
                    line = text.count("\n", 0, match.start()) + 1
                    raw.append({"file": str(source), "line": line})
                explicit += len(BOX.findall(text)) + len(LABEL.findall(text))
            rows.append(
                {
                    "episode_key": key,
                    "project": str(project),
                    "source_files": len(sources),
                    "raw_stage_text_calls": len(raw),
                    "explicit_region_calls": explicit,
                    "raw_calls": raw,
                    "quality_debt": (
                        [
                            {
                                "kind": "raw_text_calls_need_classification",
                                "count": len(raw),
                                "blocks_stage_progress": False,
                                "action": "核对实际调用及region参数；纸上文字使用 Stage.label/textBox，保留自由手绘字",
                            }
                        ]
                        if raw
                        else []
                    ),
                }
            )
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--project")
    args = parser.parse_args()
    rows = project_rows(args.workspace.resolve(), args.project)
    summary = {
        "schema": "label_contract_audit/v1",
        "episodes_checked": len(rows),
        "raw_stage_text_calls": sum(r["raw_stage_text_calls"] for r in rows),
        "explicit_region_calls": sum(r["explicit_region_calls"] for r in rows),
        "progress_first": True,
        "note": "Literal source navigation may include unused helpers or comments. Raw calls may already have a region; inspect actual imports, call options and preview before classifying. Counts do not approve or reject artwork.",
        "episodes": rows,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    lines = [
        "# 文字区域契约审计",
        "",
        "原始 `Stage.text` 调用只是源码导航，可能已传入 region，也可能来自未使用的 helper 或注释；先核对真实调用。自由手绘字可以保留，纸上文字应绑定区域，再结合正式预览审看。",
        "",
        f"检查 {len(rows)} 集源码；低层文字调用候选 {summary['raw_stage_text_calls']}；显式区域入口 {summary['explicit_region_calls']}。",
        "",
        "| 集 | 低层文字调用 | 显式区域调用 |",
        "| --- | ---: | ---: |",
    ]
    for row in rows:
        lines.append(f"| {row['episode_key']} | {row['raw_stage_text_calls']} | {row['explicit_region_calls']} |")
    args.output.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(json.dumps({k: summary[k] for k in ("episodes_checked", "raw_stage_text_calls", "explicit_region_calls")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
