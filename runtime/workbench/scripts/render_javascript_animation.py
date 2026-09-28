#!/usr/bin/env python3
"""Run a declared JavaScript animation project locally and verify its output."""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from check_animation_assets import check_assets


def run(command: list[str], cwd: Path) -> None:
    subprocess.run(command, cwd=cwd, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--render-entry", default="work/render_frames.mjs")
    parser.add_argument("--mux-entry", default="work/mux.mjs")
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--asset-manifest", type=Path, default=Path("asset_manifest.json"))
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--review-candidate", action="store_true",
                        help="Render pending assets for review; rejected or invalid assets still block")
    args = parser.parse_args()
    if shutil.which("node") is None or shutil.which("ffprobe") is None:
        raise SystemExit("node and ffprobe are required for JavaScript animation rendering")
    project = args.project_root.resolve()
    try:
        admission = check_assets(project / args.asset_manifest)
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        raise SystemExit(f"Asset admission blocked: {exc}") from exc
    if admission["status"] != "passed" and not args.review_candidate:
        raise SystemExit(json.dumps(admission, ensure_ascii=False))
    admission["render_mode"] = "review_candidate" if args.review_candidate else "approved_assets"
    admission["release_eligible"] = False
    if args.check_only:
        print(json.dumps(admission, ensure_ascii=False))
        return
    render_entry = project / args.render_entry
    mux_entry = project / args.mux_entry
    if not project.is_dir() or not render_entry.is_file() or not mux_entry.is_file():
        raise SystemExit("project root, render entry, and mux entry must exist")
    run(["node", str(render_entry), f"--fps={args.fps}"], project)
    run(["node", str(mux_entry)], project)
    output = args.output.resolve() if args.output else project / "out" / "pituitary_collage_short.mp4"
    if not output.is_file():
        raise SystemExit(f"JavaScript renderer did not create output: {output}")
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    metadata = json.loads(probe.stdout)
    receipt = {"status": "rendered", "backend": "javascript_animation", "output": str(output),
               "metadata": metadata, "asset_admission": admission, "release_eligible": False}
    output.with_suffix(".receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
