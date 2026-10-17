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

from scan_narration_boundaries import current_projects


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
    current_path = project / "out/current.json"
    if not current_path.is_file():
        return False
    try:
        from paper_project import assert_built
        assert_built(project)
        digest = sha(voice)
        score = sha(project / config.get("score", "score.json"))
        audio = sha(project / config.get("audio", "audio.wav"))
        timing_data = json.loads(timing.read_text())
        mix_data = json.loads(mix_receipt.read_text())
        current = json.loads(current_path.read_text())
        movie = Path(current.get("path", ""))
        if not movie.is_absolute():
            movie = project / movie
        return (timing_data.get("voice_sha256") == digest
                and mix_data.get("voice_sha256") == digest
                and mix_data.get("score_sha256") == score
                and mix_data.get("audio_sha256") == audio
                and current.get("status") == "rendered"
                and current.get("score_sha256") == score
                and current.get("audio_sha256") == audio
                and current.get("bundle_sha256") == sha(project / "dist/film.js")
                and movie.is_file() and current.get("sha256") == sha(movie))
    except (OSError, ValueError, KeyError):
        return False


def process(workspace: Path, project: Path, force: bool, deadline: float,
            reference_root: Path | None = None):
    config = json.loads((project / "project.json").read_text())
    if not force and already_current(project, config):
        return {"status": "already_current"}
    entry = [sys.executable, str(workspace / "scripts/paper_project.py"),
             "--workspace", str(workspace), "--project", str(project)]
    steps = []
    for step in ("retime", "build", "mix", "render"):
        if time.time() > deadline:
            return {"status": "deferred", "step": step, "completed_steps": steps}
        command = entry + [step]
        if step == "retime" and reference_root:
            reference = reference_root / config["series_id"] / config["episode_id"] / "audio/narration_beats.json"
            if not reference.is_file():
                return {"status": "failed", "step": step,
                        "output": f"Missing explicit pre-repair narration reference: {reference}"}
            # Keep the current director's score, but map its existing editorial
            # caption breaks from the actual old beat windows. A backup score
            # would overwrite current visual revisions and is not appropriate.
            command += ["--reference-narration", str(reference)]
        code, output = run_step(command, workspace)
        if code != 0:
            return {"status": "failed", "step": step,
                    "completed_steps": steps, "output": output[-3000:]}
        steps.append(step)
    if not already_current(project, config):
        return {"status": "failed", "step": "readback", "completed_steps": steps,
                "output": "Commands exited successfully, but current MP4/build/mix do not bind the current inputs."}
    current = json.loads((project / "out/current.json").read_text())
    return {"status": "rendered", "completed_steps": steps,
            "path": current["path"], "sha256": current["sha256"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--series", default="")
    parser.add_argument("--episode", default="")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--minutes", type=float, default=25.0)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--reference-root", type=Path,
                        help="Pre-repair audio backups, used to preserve existing caption breaks")
    parser.add_argument("--plan", action="store_true", help="List current targets and commands without writing projects")
    parser.add_argument("--log", type=Path, help="write the run summary here as well as stdout")
    args = parser.parse_args()

    workspace = args.workspace.resolve()
    deadline = time.time() + args.minutes * 60
    # Only operate on the workbench's registered current projects. Walking
    # every v* directory re-renders historical revisions and can make an 89
    # episode season look like hundreds of targets.
    targets = []
    for project in sorted(current_projects(workspace)):
        if args.series and args.series not in str(project):
            continue
        if args.episode and args.episode != json.loads((project / "project.json").read_text())["episode_id"]:
            continue
        beats = project / "audio/narration_beats.json"
        try:
            if "splice" not in json.loads(beats.read_text()):
                continue
        except (OSError, ValueError):
            continue
        targets.append(project)
    if args.limit:
        targets = targets[:args.limit]

    if args.plan:
        plan = {"schema": "splice_rerender_plan/v2", "targets": len(targets),
                "target_source": "workbench.yaml registered current projects",
                "reference_root": str(args.reference_root.resolve()) if args.reference_root else None,
                "detail": [{"project": str(p), "already_current": already_current(p, json.loads((p / "project.json").read_text()))}
                           for p in targets], "steps": ["retime", "build", "mix", "render", "actual_current_readback"]}
        if args.log:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            args.log.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n")
        print(json.dumps(plan, ensure_ascii=False), flush=True)
        return

    counts = {"rendered": 0, "already_current": 0, "deferred": 0, "failed": 0}
    failures = []
    detail = []
    for project in targets:
        if time.time() > deadline:
            counts["deferred"] += 1
            continue
        result = process(workspace, project, args.force, deadline,
                         args.reference_root.resolve() if args.reference_root else None)
        config = json.loads((project / "project.json").read_text())
        row = {"series": config["series_id"], "episode": config["episode_id"],
               "project": str(project), **result}
        detail.append(row)
        counts[result["status"]] = counts.get(result["status"], 0) + 1
        if result["status"] == "failed":
            failures.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
        if args.log:
            args.log.parent.mkdir(parents=True, exist_ok=True)
            args.log.write_text(json.dumps({"schema": "splice_rerender/v2", "targets": len(targets),
                **counts, "detail": detail, "failures": failures, "complete": len(detail) == len(targets)},
                ensure_ascii=False, indent=2) + "\n")
    summary = {"schema": "splice_rerender/v2", "targets": len(targets), **counts,
               "detail": detail, "failures": failures, "complete": len(detail) == len(targets)}
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        args.log.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
