#!/usr/bin/env python3
"""Animate reviewed hand-drawn diagrams with semantic in-place pulse rings."""

import argparse
import subprocess
from pathlib import Path


def parse_pulse(value: str) -> tuple[float, ...]:
    parts = tuple(float(item) for item in value.split(","))
    if len(parts) != 8:
        raise argparse.ArgumentTypeError(
            "pulse must be x,y,radius,red,green,blue,period,phase"
        )
    x, y, radius, red, green, blue, period, _phase = parts
    if radius <= 0 or period <= 0 or not all(0 <= channel <= 255 for channel in (red, green, blue)):
        raise argparse.ArgumentTypeError("pulse radius, period, or RGB channel is invalid")
    return parts


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--duration", type=float, required=True)
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--pulse", type=parse_pulse, action="append", required=True)
    args = parser.parse_args()

    if not args.source.is_file() or args.duration <= 0 or args.fps <= 0:
        raise SystemExit("Source, duration, and fps must be valid")
    args.output.parent.mkdir(parents=True, exist_ok=True)

    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-loop", "1", "-framerate", str(args.fps), "-i", str(args.source),
    ]
    for x, y, radius, red, green, blue, period, phase in args.pulse:
        theta = f"2*PI*(T-{phase:.6f})/{period:.6f}"
        animated_radius = f"({radius:.6f}+{radius * 0.35:.6f}*(0.5+0.5*sin({theta})))"
        distance = f"((X-{x:.6f})^2+(Y-{y:.6f})^2)"
        ring = f"between({distance},({animated_radius}-2.2)^2,({animated_radius}+2.2)^2)"
        alpha = f"if({ring},72*(0.70+0.30*sin({theta})),0)"
        source = (
            f"color=c=black@0.0:s=608x352:r={args.fps}:d={args.duration:.6f},"
            f"format=rgba,geq=r={red:.0f}:g={green:.0f}:b={blue:.0f}:a='{alpha}'"
        )
        command.extend(["-f", "lavfi", "-i", source])

    filters = []
    previous = "0:v"
    for index in range(1, len(args.pulse) + 1):
        output = f"v{index}"
        filters.append(f"[{previous}][{index}:v]overlay=shortest=1[{output}]")
        previous = output
    command.extend(
        [
            "-filter_complex", ";".join(filters), "-map", f"[{previous}]", "-an",
            "-t", f"{args.duration:.6f}", "-c:v", "libx264", "-preset", "slow",
            "-crf", "18", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
            str(args.output),
        ]
    )
    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
