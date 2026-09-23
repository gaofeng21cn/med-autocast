#!/usr/bin/env python3
"""Build a static storyboard animatic that can never become a final candidate."""

import argparse
import json
import subprocess
from pathlib import Path

import yaml


CELL_OFFSETS = {"TL": (0, 0), "TR": (1, 0), "BL": (0, 1), "BR": (1, 1)}


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def dimensions(path: Path) -> tuple[int, int]:
    result = subprocess.run(
        ["magick", "identify", "-format", "%w %h", str(path)],
        check=True,
        capture_output=True,
        text=True,
    )
    width, height = result.stdout.split()
    return int(width), int(height)


def make_reference(source: Path, selector: str, shared_root: Path, target: Path) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    if selector.startswith("shared:"):
        selected = shared_root / selector.split(":", 1)[1]
        run(
            [
                "magick", str(selected), "-resize", "608x352^", "-gravity", "center",
                "-extent", "608x352", str(target),
            ]
        )
        return {"kind": "reviewed_shared", "source": str(selected)}

    if selector not in CELL_OFFSETS:
        raise ValueError(f"Unknown visual selector: {selector}")
    width, height = dimensions(source)
    cell_width, cell_height = width // 2, height // 2
    column, row = CELL_OFFSETS[selector]
    inset = max(4, min(width, height) // 250)
    crop_width, crop_height = cell_width - inset * 2, cell_height - inset * 2
    x, y = column * cell_width + inset, row * cell_height + inset
    run(
        [
            "magick", str(source), "-crop", f"{crop_width}x{crop_height}+{x}+{y}",
            "+repage", "-resize", "608x352^", "-gravity", "center", "-extent", "608x352",
            str(target),
        ]
    )
    return {"kind": "reviewed_storyboard_cell", "source": str(source), "cell": selector}


def make_stable_video(reference: Path, target: Path, duration: float) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-loop", "1",
            "-framerate", "24", "-i", str(reference), "-t", f"{duration:.3f}",
            "-c:v", "libx264", "-preset", "slow", "-crf", "18", "-pix_fmt", "yuv420p",
            "-an", str(target),
        ]
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, required=True)
    parser.add_argument("--production-root", type=Path, required=True)
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    parser.add_argument("--duration", type=float, default=14.0)
    args = parser.parse_args()

    spec = yaml.safe_load(args.map.read_text(encoding="utf-8"))
    shared_root = args.project_root / spec["shared_root"]
    results = []
    for episode_id, episode in spec["episodes"].items():
        production = args.production_root / episode_id
        storyboard = args.project_root / episode["storyboard"]
        records = []
        for beat_id, selector in episode["beats"].items():
            reference = production / "animatic/references" / f"{beat_id.lower()}.png"
            record = make_reference(storyboard, selector, shared_root, reference)
            candidate = production / "animatic/candidates" / f"{episode_id}_{beat_id.lower()}_animatic.mp4"
            make_stable_video(reference, candidate, args.duration)
            records.append({"beat_id": beat_id, "reference": str(reference), "candidate": str(candidate), **record})
        manifest = {
            "schema": "medical_video_animatic/v1",
            "episode_id": episode_id,
            "status": "animatic_only_animation_generation_required",
            "delivery_class": "animatic",
            "release_eligible": False,
            "strategy": "reviewed_keyframe_stable_hold",
            "motion": "none",
            "reason": "Static storyboard preview; not an animated release candidate",
            "beats": records,
        }
        manifest_path = production / "animatic/manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({"episode": episode_id, "beats": len(records)})
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
