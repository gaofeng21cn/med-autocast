#!/usr/bin/env python3
"""Create a narration-plus-foley audit mix without changing the release mix receipt."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    project = args.project.resolve()
    score = json.loads((project / "score.json").read_text())
    audio = project / "audio"
    voice = audio / "narration-normalized.wav"
    foley = audio / "foley.wav"
    output = (args.output or audio / "narration-foley-only.wav").resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    duration = float(score["duration"])
    receipt_path = audio / "mix-receipt.json"
    receipt = json.loads(receipt_path.read_text())
    if (receipt.get("voice_sha256") != sha256(voice) or
            receipt.get("score_sha256") != sha256(project / "score.json")):
        raise ValueError("无音乐审听候选须使用当前旁白与事件，请先重新 mix")

    # Keep the same 48 kHz, stereo, loudness target as the release mix while
    # removing the music bus. The foley remains audible for listening review.
    premix = audio / "narration-foley-only-premix.wav"
    run([
        "ffmpeg", "-y", "-v", "error",
        "-i", str(voice), "-i", str(foley),
        "-filter_complex",
        "[0:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur="
        f"{duration},atrim=end={duration}[v];"
        "[1:a]aresample=48000,aformat=channel_layouts=stereo,apad=whole_dur="
        f"{duration},atrim=end={duration}[f];"
        "[v][f]amix=inputs=2:normalize=0:duration=first[out]",
        "-map", "[out]", "-t", str(duration), "-c:a", "pcm_s24le", str(premix),
    ])
    run([
        "ffmpeg", "-y", "-v", "error", "-i", str(premix),
        "-af", "loudnorm=I=-16:TP=-1.2:LRA=11:linear=false",
        "-ar", "48000", "-ac", "2", "-c:a", "pcm_s24le", str(output),
    ])
    receipt = {
        "schema": "paper_theatre_no_music_mix/v1",
        "status": "created",
        "project": str(project),
        "duration_seconds": duration,
        "voice": str(voice),
        "voice_sha256": sha256(voice),
        "foley": str(foley),
        "foley_sha256": sha256(foley),
        "music": None,
        "output": str(output),
        "output_sha256": sha256(output),
        "full_listening": "pending",
        "purpose": "保留旁白与拟音、移除 BGM 的独立听审版本",
    }
    receipt_path = output.with_suffix(".receipt.json")
    receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": "created", "output": str(output), "receipt": str(receipt_path)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
