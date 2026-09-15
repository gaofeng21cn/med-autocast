#!/usr/bin/env python3
"""Build every episode that has audio, subtitles, a plan, and approved candidates."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

from delivery_contract import animation_gate
from workbench_config import load_author_profile, production_root_for, resolve_font


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--builder", type=Path, default=Path(__file__).with_name("build_episode_video.py"))
    parser.add_argument("--font", type=Path)
    parser.add_argument("--avatar", type=Path)
    parser.add_argument("--bgm", type=Path)
    parser.add_argument("--no-bgm", action="store_true")
    parser.add_argument("--no-avatar", action="store_true")
    parser.add_argument("--author-profile", type=Path)
    parser.add_argument("--series")
    parser.add_argument("--episode", action="append")
    args = parser.parse_args()

    author_path, author = load_author_profile(profile_path=args.author_profile, series_id=args.series)
    args.production_root = production_root_for(args.series, args.production_root)
    args.font = resolve_font(args.font)

    selected = set(args.episode or [])
    results = []
    for episode_dir in sorted(args.production_root.iterdir()):
        if selected and episode_dir.name not in selected:
            continue
        plan = episode_dir / "production_plan.yaml"
        if not plan.is_file():
            continue
        plan_data = yaml.safe_load(plan.read_text(encoding="utf-8"))
        audio = episode_dir / plan_data.get("audio", {}).get("source", "audio/local_voice/index-tts25-narration.wav")
        srt = episode_dir / plan_data.get("subtitles", {}).get("source", "audio/local_voice/narration.srt")
        candidates = episode_dir / "candidates"
        if not all(path.exists() for path in (plan, audio, srt, candidates)):
            continue
        plan_author = plan_data.get("delivery", {}).get("author_profile")
        if plan_author and plan_author != author.get("profile_id"):
            raise SystemExit(
                f"Author profile mismatch for {episode_dir.name}: plan={plan_author!r}, "
                f"selected={author.get('profile_id')!r}"
            )
        gate = animation_gate(episode_dir, plan_data)
        if gate["status"] != "passed":
            raise SystemExit(
                f"Animation delivery gate failed for {episode_dir.name}: "
                f"{json.dumps(gate['violations'], ensure_ascii=False)}"
            )
        output = episode_dir / "final/video.mp4"
        work_dir = episode_dir / "qa/build-final"
        command = [
            sys.executable, str(args.builder), "--candidates", str(candidates),
            "--audio", str(audio), "--srt", str(srt), "--font", str(args.font),
            "--plan", str(plan), "--output", str(output),
            "--work-dir", str(work_dir),
            "--author-profile", str(author_path),
        ]
        if args.avatar:
            command += ["--avatar", str(args.avatar)]
        if args.bgm:
            command += ["--bgm", str(args.bgm)]
        if args.no_bgm:
            command += ["--no-bgm"]
        if args.no_avatar:
            command += ["--no-avatar"]
        subprocess.run(command, check=True)
        results.append({"episode": episode_dir.name, "output": str(output)})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
