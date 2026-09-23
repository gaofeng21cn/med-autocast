#!/usr/bin/env python3
"""Render H3 shots for a registered series, resuming only from explicit receipts."""

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path
from workbench_config import production_root_for
from media_backend import load_config


EPISODE_RE = re.compile(r"^(\d{2})_(.+)$")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--series", required=True)
    parser.add_argument("--backend")
    parser.add_argument("--queue-runner", type=Path, default=Path(__file__).with_name("queue_h3_shots.py"))
    parser.add_argument("--base-queue", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--receipt-root", type=Path, required=True)
    parser.add_argument("--start-episode", type=int, default=1)
    parser.add_argument("--base-url")
    args = parser.parse_args()
    args.production_root = production_root_for(args.series, args.production_root)
    config = load_config()
    backend_id = args.backend or config["policy"]["default_video"]
    backend = config["video"][backend_id]
    if not backend.get("kind", "").startswith("comfyui"):
        raise ValueError("render_series_h3 only accepts a ComfyUI backend")
    args.base_url = args.base_url or backend["endpoint"]

    summary = []
    for episode_dir in sorted(args.production_root.iterdir()):
        match = EPISODE_RE.match(episode_dir.name)
        prompts = episode_dir / "shot_prompts.json"
        if not match or int(match.group(1)) < args.start_episode or not prompts.is_file():
            continue
        spec = json.loads(prompts.read_text(encoding="utf-8"))
        receipt_path = args.receipt_root / args.series / f"{episode_dir.name}.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8")) if receipt_path.is_file() else {}
        completed = {shot["shot"] for shot in receipt.get("shots", [])
                     if shot.get("status") == "generated_review_required" and shot.get("outputs")
                     and all((args.output_root / output).is_file() for output in shot["outputs"])}
        missing = []
        for shot in spec["shots"]:
            if shot["id"] not in completed:
                missing.append(shot["id"])
        if not missing:
            summary.append({"episode": episode_dir.name, "status": "already_complete"})
            continue

        command = [
            sys.executable,
            str(args.queue_runner),
            "--base-queue",
            str(args.base_queue),
            "--prompts",
            str(prompts),
            "--base-url",
            args.base_url,
            "--output-prefix",
            f"video/{args.series}_{episode_dir.name}",
        ]
        for shot_id in missing:
            command.extend(["--shot", shot_id])
        command.extend(["--receipt", str(receipt_path)])
        print(json.dumps({"episode": episode_dir.name, "missing": missing}, ensure_ascii=False), flush=True)
        subprocess.run(command, check=True)
        summary.append({"episode": episode_dir.name, "status": "rendered", "shots": missing})

    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)


if __name__ == "__main__":
    main()
