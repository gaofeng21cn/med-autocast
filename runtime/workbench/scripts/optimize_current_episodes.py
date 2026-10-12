#!/usr/bin/env python3
"""Render and publish the current workbench revisions with resumable receipts.

This is deliberately a thin batch driver around the normal project commands. It
does not decide visual quality and it never blocks the series because one review
item is pending; it only records what actually rendered and published.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import json
import subprocess
import sys
from pathlib import Path

import yaml


def run(command: list[str], cwd: Path) -> dict:
    result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
    if result.returncode:
        return {"status": "failed", "command": command, "stdout": result.stdout[-4000:], "stderr": result.stderr[-4000:]}
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    receipt = json.loads(lines[-1]) if lines else {"status": "completed"}
    return {"status": "completed", "receipt": receipt}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--series", action="append", default=[])
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--render-only", action="store_true")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    config = yaml.safe_load((workspace / "workbench.yaml").read_text()) or {}
    jobs = []
    for series_id, series in (config.get("series") or {}).items():
        if args.series and series_id not in args.series:
            continue
        for episode_id, episode in (series.get("episodes") or {}).items():
            project = episode.get("project")
            if project:
                jobs.append((series_id, episode_id, workspace / project))

    def render(job):
        series_id, episode_id, project = job
        built = run([sys.executable, str(workspace / "scripts/paper_project.py"),
                     "--workspace", str(workspace), "--project", str(project), "build"], workspace)
        if built["status"] != "completed":
            return {"series_id": series_id, "episode_id": episode_id, "project": str(project), "render": built}
        result = run([sys.executable, str(workspace / "scripts/paper_project.py"),
                      "--workspace", str(workspace), "--project", str(project), "render"], workspace)
        return {"series_id": series_id, "episode_id": episode_id, "project": str(project), "render": result}

    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        rendered = list(pool.map(render, jobs))

    failures = [row for row in rendered if row["render"]["status"] != "completed"]
    published = []
    if not args.render_only:
        for row in rendered:
            if row["render"]["status"] != "completed":
                continue
            project = Path(row["project"])
            result = run([sys.executable, str(workspace / "scripts/paper_project.py"),
                          "--workspace", str(workspace), "--project", str(project), "package"], workspace)
            published.append({**row, "package": result})
    else:
        published = rendered

    report = {
        "schema": "optimize_current_episodes/v1",
        "episodes": len(jobs),
        "rendered": len(rendered) - len(failures),
        "render_failures": failures,
        "published": sum(1 for row in published if row.get("package", {}).get("status") == "completed"),
        "package_failures": [row for row in published if row.get("package", {}).get("status") != "completed"],
        "detail": published,
    }
    out = workspace / "work/optimize-current-episodes.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k != "detail"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
