#!/usr/bin/env python3
"""Rebuild every registered episode through the complete local media chain.

The driver is resumable and Progress First: one episode can fail without
stopping the remaining episodes.  It never declares semantic, listening or
medical approval; it only records the real command receipts and current-byte
bindings produced by the normal project commands.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def run_stage(workspace: Path, project: Path, stage: str, extra: list[str] | None = None) -> dict:
    command = [sys.executable, str(workspace / "scripts/paper_project.py"),
               "--workspace", str(workspace), "--project", str(project), stage]
    if extra:
        command.extend(extra)
    started = datetime.now(timezone.utc).isoformat()
    completed = subprocess.run(command, cwd=workspace, text=True, capture_output=True)
    lines = [line.strip() for line in completed.stdout.splitlines() if line.strip()]
    receipt = None
    for line in reversed(lines):
        if line.startswith("{"):
            try:
                receipt = json.loads(line)
                break
            except json.JSONDecodeError:
                pass
    result = {
        "stage": stage, "started_at": started, "returncode": completed.returncode,
        "status": "completed" if completed.returncode == 0 else "failed",
        "receipt": receipt,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "command": command,
    }
    return result


def rebuild(workspace: Path, series: str, episode: str, project: Path, review_root: Path,
            *, narration_only: bool = False, media_only: bool = False) -> dict:
    stages: list[dict] = []
    preview_dir = review_root / series / episode / "preview"
    try:
        project_config = json.loads((project / "project.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        project_config = {}
    voice_ref = project_config.get("voice", "audio/narration-normalized.wav")
    voice_path = Path(voice_ref)
    if not voice_path.is_absolute():
        voice_path = project / voice_path
    # A previous cleanup removed the source narration WAVs while leaving the
    # beat manifest and final mix. Recreate the current registered voice first
    # so retime/build/mix/render all bind to a real source take chain.
    narration_stage = [
        ("narrate", ["--force"]),
    ] if not voice_path.is_file() else []
    if narration_only:
        sequence = narration_stage
    else:
        sequence = ([] if media_only else narration_stage) + [
        ("retime", []),
        ("build", []),
        ("preview", ["--neighbors", "--output", str(preview_dir)]),
        ("mix", []),
        ("render", []),
        ("package", []),
        ]
    for stage, extra in sequence:
        result = run_stage(workspace, project, stage, extra)
        stages.append(result)
        if result["status"] != "completed":
            break
    pointer = project / "out/current.json"
    current = {}
    if pointer.is_file():
        try:
            current = json.loads(pointer.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            current = {}
    current_path = Path(current["path"]) if current.get("path") else None
    if current_path is not None and not current_path.is_absolute():
        current_path = project / current_path
    publish = workspace / "publish" / series / episode / "video.mp4"
    package_receipt = next((row.get("receipt") for row in reversed(stages)
                            if row.get("stage") == "package" and row.get("status") == "completed"), None) or {}
    package_dir = Path(package_receipt["directory"]) if package_receipt.get("directory") else None
    if package_dir and (package_dir / "video.mp4").is_file():
        publish = package_dir / "video.mp4"
    return {
        "series": series, "episode": episode, "project": str(project),
        "stages": stages,
        "completed_stages": [row["stage"] for row in stages if row["status"] == "completed"],
        "narration_regenerated": any(row["stage"] == "narrate" and row["status"] == "completed" for row in stages),
        "failed_stage": next((row["stage"] for row in stages if row["status"] == "failed"), None),
        "current": {"pointer": str(pointer), "path": str(current_path) if current_path else None,
                    "sha256": sha(current_path) if current_path else None},
        "publish": {"path": str(publish), "exists": publish.is_file(), "sha256": sha(publish),
                    "package_directory": str(package_dir) if package_dir else None},
        "release_eligible": False,
        "semantic_review": "pending",
        "full_listening": "pending",
        "medical_review": "pending",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--series", action="append", default=[])
    parser.add_argument("--episode", action="append", default=[])
    parser.add_argument("--workers", type=int, default=2)
    parser.add_argument("--narration-only", action="store_true",
                        help="只补齐缺失的当前旁白源轨，不改动画或交付")
    parser.add_argument("--media-only", action="store_true",
                        help="假定当前旁白已存在，只执行 retime 到 package")
    parser.add_argument("--review-root", type=Path,
                        default=Path("work/audit-20261014/rebuild-20261015"))
    args = parser.parse_args()
    if args.narration_only and args.media_only:
        parser.error("--narration-only 与 --media-only 不能同时使用")
    workspace = args.workspace.resolve()
    review_root = args.review_root if args.review_root.is_absolute() else workspace / args.review_root
    config = yaml.safe_load((workspace / "workbench.yaml").read_text(encoding="utf-8")) or {}
    jobs = []
    for series, spec in sorted((config.get("series") or {}).items()):
        if args.series and series not in args.series:
            continue
        for episode, row in sorted((spec.get("episodes") or {}).items()):
            if args.episode and episode not in args.episode:
                continue
            if row.get("project"):
                jobs.append((series, episode, (workspace / row["project"]).resolve()))
    review_root.mkdir(parents=True, exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(rebuild, workspace, series, episode, project, review_root,
                                narration_only=args.narration_only, media_only=args.media_only): (series, episode)
                   for series, episode, project in jobs}
        results = []
        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            destination = review_root / result["series"] / f'{result["episode"]}.json'
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            results.append(result)
            print(json.dumps({"series": result["series"], "episode": result["episode"],
                              "completed_stages": result["completed_stages"],
                              "failed_stage": result["failed_stage"]}, ensure_ascii=False), flush=True)
    results.sort(key=lambda row: (row["series"], row["episode"]))
    summary = {
        "schema": "episode_rebuild/v1", "generated_at": datetime.now(timezone.utc).isoformat(),
        "episodes": len(results),
        "fully_rebuilt": sum(row["failed_stage"] is None and len(row["completed_stages"]) == 6 for row in results),
        "failed": sum(row["failed_stage"] is not None for row in results),
        "release_eligible": False, "semantic_review": "pending", "full_listening": "pending",
        "medical_review": "pending", "detail": results,
    }
    (review_root / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in ("episodes", "fully_rebuilt", "failed", "release_eligible")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
