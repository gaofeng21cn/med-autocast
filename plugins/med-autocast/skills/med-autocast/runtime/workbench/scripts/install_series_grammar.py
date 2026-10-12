#!/usr/bin/env python3
"""Install the series camera grammar into every published episode.

Shared shot factories each declare their own camera differently. Rather than
rewriting every factory, this replaces the small camera expression with one that
delegates to the series grammar, and drops the grammar module next to it. The
shot bodies, story and props are untouched, so a failed install is easy to
revert and does not silently change what an episode says.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import yaml

GRAMMAR_SOURCE = "series_grammar.ts"

# Each factory exposes camera() in one of these shapes. Only the camera clause is
# replaced; everything else in the file stays byte-identical.
CAMERA_START = re.compile(r"camera\s*:\s*(?=\(\s*(?:\{t\}|c)?\s*\)\s*=>)")


def expression_end(text: str, start: int) -> int:
    """Return the end of the camera property, including a trailing comma."""
    i = start
    depth = 0
    seen = False
    while i < len(text):
        ch = text[i]
        if ch in "({[":
            depth += 1
            seen = True
        elif ch in ")}]":
            depth -= 1
            if depth == 0:
                i += 1
                probe = i
                while probe < len(text) and text[probe].isspace():
                    probe += 1
                if text.startswith("=>", probe):
                    i = probe + 2
                    continue
                if i < len(text) and text[i] in ",;\n":
                    while i < len(text) and text[i] in ",;\n":
                        i += 1
                return i
        elif depth == 0 and ch == "," and seen:
            return i + 1
        i += 1
    raise ValueError("unterminated camera expression")


def patch_file(path: Path, grammar_source: Path) -> str:
    text = path.read_text()
    if "from './series_grammar'" in text:
        return "already_installed"
    match = CAMERA_START.search(text)
    if not match:
        return "no_match"
    start = match.start()
    end = expression_end(text, match.end())
    original = text[start:end]
    series_id = next((p.name for p in path.parents if p.name.endswith("_paper_theatre")), "")
    topic = series_id.removesuffix("_paper_theatre") or "diabetes"
    anchor = ""
    if "ease(" not in original and "c.t" not in original:
        values = dict(re.findall(r"\b(x|y|zoom)\s*:\s*(-?[0-9.]+)", original))
        if {"x", "y", "zoom"} <= values.keys():
            anchor = ",anchor:{%s}" % ",".join(f"{k}:{values[k]}" for k in ("x", "y", "zoom"))
    replacement = ("camera:({t})=>cameraFor({t,topic:'%s',seed:id%s})," % (topic, anchor))
    patched = text[:start] + replacement + text[end:]
    lines = patched.splitlines(keepends=True)
    last_import = max((i for i, line in enumerate(lines[:24]) if line.startswith("import ")), default=-1)
    lines.insert(last_import + 1, "import {cameraFor} from './series_grammar';\n")
    patched = "".join(lines)
    workspace = next((p for p in path.parents if (p / "workbench.yaml").is_file()), None)
    backup_root = (workspace / "work/series-grammar-backups" if workspace else path.parents[3] / "work/series-grammar-backups")
    backup = backup_root / path.relative_to(workspace) if workspace else backup_root / path.name
    backup = backup.with_suffix(backup.suffix + ".pre-grammar")
    backup.parent.mkdir(parents=True, exist_ok=True)
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(patched)
    shutil.copy2(grammar_source, path.parent / GRAMMAR_SOURCE)
    return "patched"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--grammar", type=Path, required=True,
                        help="series_grammar.ts to install alongside each factory")
    parser.add_argument("--series", default="")
    parser.add_argument("--files", default="", help="comma-separated src basenames to patch")
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    allowed_files = {name.strip() for name in args.files.split(",") if name.strip()}
    config = yaml.safe_load((workspace / "workbench.yaml").read_text()) or {}
    summary = {}
    for series_id, series in (config.get("series") or {}).items():
        if args.series and args.series != series_id:
            continue
        for episode_id, episode in (series.get("episodes") or {}).items():
            src = workspace / (episode.get("project") or "") / "src"
            if not src.is_dir():
                continue
            for path in sorted(src.glob("*.ts")):
                if path.name in ("main.ts", GRAMMAR_SOURCE):
                    continue
                if allowed_files and path.name not in allowed_files:
                    continue
                text = path.read_text()
                if "camera:" not in text:
                    continue
                key = f"{series_id}/{episode_id}/{path.name}"
                if args.apply:
                    summary[key] = patch_file(path, args.grammar.resolve())
                else:
                    summary[key] = "already_installed" if "cameraFor(" in text else "candidate"

    counts = {}
    for value in summary.values():
        counts[value] = counts.get(value, 0) + 1
    print(json.dumps({"schema": "series_grammar_install/v1", "applied": args.apply,
                      "counts": counts, "files": len(summary)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
