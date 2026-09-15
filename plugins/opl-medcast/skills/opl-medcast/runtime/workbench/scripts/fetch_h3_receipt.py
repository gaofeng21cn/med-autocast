#!/usr/bin/env python3
"""Fetch the exact ComfyUI outputs named by one H3 generation receipt."""

import argparse
import json
import subprocess
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--receipt", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--remote-output-dir", required=True)
    parser.add_argument("--destination", type=Path, required=True)
    args = parser.parse_args()

    receipt = json.loads(args.receipt.read_text(encoding="utf-8"))
    shots = receipt.get("shots", [])
    if not shots:
        raise SystemExit("Receipt contains no generated shots")

    outputs = []
    for shot in shots:
        if shot.get("status") != "generated_review_required":
            raise SystemExit(f"Shot {shot.get('shot')} is not ready to fetch")
        for filename in shot.get("outputs", []):
            if Path(filename).name != filename:
                raise SystemExit(f"Unsafe output filename in receipt: {filename!r}")
            outputs.append((shot["shot"], filename, shot["prompt_id"]))
    if not outputs:
        raise SystemExit("Receipt contains no output files")

    args.destination.mkdir(parents=True, exist_ok=True)
    fetched = []
    for shot_id, filename, prompt_id in outputs:
        target = args.destination / filename
        subprocess.run(
            [
                "scp",
                f"{args.host}:{args.remote_output_dir.rstrip('/')}/{filename}",
                str(target),
            ],
            check=True,
        )
        fetched.append(
            {
                "shot": shot_id,
                "prompt_id": prompt_id,
                "source_filename": filename,
                "local_path": str(target),
            }
        )
    print(json.dumps(fetched, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
