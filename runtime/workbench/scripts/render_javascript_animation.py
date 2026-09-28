#!/usr/bin/env python3
"""Run a declared JavaScript animation project locally and verify its output."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from check_animation_assets import check_assets


def run(command: list[str], cwd: Path) -> None:
    env = dict(os.environ)
    runtime_root = Path(__file__).resolve().parents[1]
    env['MED_AUTOCAST_PLAYWRIGHT_MODULE'] = (runtime_root / 'scripts/playwright_runtime.mjs').as_uri()
    try:
        subprocess.run(command, cwd=cwd, check=True, env=env)
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "JS 渲染失败，请查看上方错误。项目自身 import 'playwright' 需要项目 npm install；"
            "使用工作区共享依赖时，入口应动态 import(process.env.MED_AUTOCAST_PLAYWRIGHT_MODULE)。"
            "缺少 Chromium 时重跑工作区 setup_workbench.sh。"
        ) from exc


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--render-entry", default="work/render_frames.mjs")
    parser.add_argument("--mux-entry", default="work/mux.mjs")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--html-entry", default="index.html")
    parser.add_argument("--audio", type=Path, help="共享渲染入口使用的最终旁白（可为已混音音轨）")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--asset-manifest", type=Path, default=Path("asset_manifest.json"))
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--review-candidate", action="store_true",
                        help="Render pending assets for review; rejected or invalid assets still block")
    args = parser.parse_args()
    if any(shutil.which(tool) is None for tool in ("node", "ffmpeg", "ffprobe")):
        raise SystemExit("需要 Node.js 20+ 和 ffprobe；请先运行 bash scripts/setup_workbench.sh")
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
    output = args.output.resolve() if args.output else project / "out" / "video.mp4"
    if output.exists():
        raise SystemExit("输出已存在，请使用新的修订路径")
    if args.audio:
        config = {"project_root": str(project), "entry": args.html_entry,
                  "audio": str(args.audio.resolve()), "output": str(output),
                  "fps": args.fps, "width": args.width, "height": args.height}
        with tempfile.TemporaryDirectory(prefix="med-animation-") as temporary:
            config_path = Path(temporary) / "render.json"
            config_path.write_text(json.dumps(config))
            run(["node", str(Path(__file__).with_name("render_local_animation.mjs")), str(config_path)], project)
    else:
        if not project.is_dir() or not render_entry.is_file() or not mux_entry.is_file():
            raise SystemExit("通用渲染请提供 --audio 与 index.html；自定义项目需提供 render/mux 入口")
        run(["node", str(render_entry), f"--fps={args.fps}"], project)
        run(["node", str(mux_entry)], project)
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
