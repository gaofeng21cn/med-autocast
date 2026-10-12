#!/usr/bin/env python3
"""Rebuild every episode whose narration splice was repaired.

The splice fix changes the voice track, so mix, build binding and the encoded
episode all have to be refreshed. Each step is resumable: an episode whose
receipts already match the current voice hash is skipped.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_step(command, cwd: Path):
    result = subprocess.run(command, cwd=cwd, capture_output=True, text=True)
    return result.returncode, (result.stdout or "") + (result.stderr or "")


def already_current(project: Path, config: dict) -> bool:
    voice = project / config.get("voice", "audio/narration-normalized.wav")
    timing = project / "audio/timing-receipt.json"
    mix_receipt = project / "audio/mix-receipt.json"
    if not (voice.is_file() and timing.is_file() and mix_receipt.is_file()):
        return False
    digest = sha(voice)
    return json.loads(timing.read_text()).get("voice_sha256") == digest \
        and json.loads(mix_receipt.read_text()).get("voice_sha256") == digest


def process(workspace: Path, project: Path, force: bool, deadline: float):
    config = json.loads((project / "project.json").read_text())
    if not force and already_current(project, config):
        return {"status": "already_current"}
    entry = [sys.executable, str(workspace / "scripts/paper_project.py"),
             "--workspace", str(workspace), "--project", str(project)]
    for step in ("retime", "build", "mix", "render"):
        if time.time() > deadline:
            return {"status": "deferred", "step": step}
        code, output = run_step(entry + [step], workspace)
        if code != 0:
            return {"status": "failed", "step": step, "output": output[-300:]}
    return {"status": "rendered"}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--series", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--minutes", type=float, default=25.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--log", type=Path, help="write the run summary here as well as stdout")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    deadline = time.time() + args.minutes * 60
    targets = []
    for beats in sorted((workspace / "productions").glob("*_paper_theatre/*/v*/audio/narration_beats.json")):
        if args.series and args.series not in str(beats):
            continue
        try:
            if "splice" not in json.loads(beats.read_text()):
                continue
        except (OSError, ValueError):
            continue
        targets.append(beats.parents[1])
    if args.limit:
        targets = targets[:args.limit]

    counts = {"rendered": 0, "already_current": 0, "deferred": 0, "failed": 0}
    failures = []
    for project in targets:
        if time.time() > deadline:
            counts["deferred"] += 1
            continue
        result = process(workspace, project, args.force, deadline)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if result["status"] == "failed":
            failures.append({"project": project.name, **{k: v for k, v in result.items() if k != "status"}})
            print(json.dumps(failures[-1], ensure_ascii=False), flush=True)
    summary = {"schema": "splice_rerender/v1", "targets": len(targets), **counts,
               "failures": failures}
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
