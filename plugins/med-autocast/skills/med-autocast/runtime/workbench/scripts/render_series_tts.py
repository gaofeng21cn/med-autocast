#!/usr/bin/env python3
"""Render a series through the registered narration backend and review gates."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import wave
from pathlib import Path

from render_narration import ANNOTATION, synthesize
from workbench_config import load_author_profile, production_root_for, series_paths, workspace_path


EPISODE_RE = re.compile(r"^(\d{2})_(.+)$")
BEAT_RE = re.compile(r"^## (B\d{2})\s+(.+)$")


def read_beats(path: Path) -> list[dict]:
    beats = []
    current = None
    paragraphs = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = BEAT_RE.match(line)
        if match:
            if current:
                raw = "".join(paragraphs).strip()
                current["text"] = ANNOTATION.sub(lambda match: match.group(1), raw)
                if raw != current["text"]:
                    current["tts_text"] = raw
                beats.append(current)
            current = {"id": match.group(1), "title": match.group(2).strip()}
            paragraphs = []
            continue
        if line.startswith("## 朗读规则"):
            break
        if current and line.strip():
            paragraphs.append(line.strip())
    if current:
        raw = "".join(paragraphs).strip()
        current["text"] = ANNOTATION.sub(lambda match: match.group(1), raw)
        if raw != current["text"]:
            current["tts_text"] = raw
        beats.append(current)
    if not beats or any(not beat["text"] for beat in beats):
        raise ValueError(f"No complete narration beats in {path}")
    return beats


def duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path(os.environ.get("MED_AUTOCAST_WORKSPACE_ROOT", ".")))
    parser.add_argument("--content-root", type=Path)
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--voice", type=Path)
    parser.add_argument("--author-profile", type=Path)
    parser.add_argument("--series")
    parser.add_argument("--direction", "--emotion", dest="direction", help="覆盖作者档案中的全篇讲解指令")
    parser.add_argument("--language")
    parser.add_argument("--start-episode", type=int, default=1)
    parser.add_argument("--end-episode", type=int, help="限定本次选集，避免小样生成全季")
    parser.add_argument("--silence-ms", type=int, default=260)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    workspace = args.workspace.expanduser().resolve()
    if args.content_root:
        args.content_root = workspace_path(args.content_root, root=workspace)
    if args.production_root:
        args.production_root = workspace_path(args.production_root, root=workspace)
    if not 0 <= args.silence_ms <= 3000:
        parser.error("--silence-ms must be between 0 and 3000")

    args.production_root = production_root_for(args.series, args.production_root, root=workspace)
    if args.series:
        registered_content = series_paths(args.series, root=workspace)["content_root"] / "episodes"
        if args.content_root and args.content_root.resolve() != registered_content.resolve():
            raise ValueError("--content-root conflicts with --series")
        args.content_root = registered_content
    if not args.content_root:
        parser.error("Pass --series or --content-root")

    _, author = load_author_profile(profile_path=args.author_profile, series_id=args.series, root=workspace)
    voice_config = author.get("voice", {})
    if args.voice:
        voice_config = {**voice_config, "reference_audio": str(args.voice)}
    if args.direction:
        voice_config = {**voice_config, "direction": args.direction}

    episodes = []
    for directory in sorted(args.content_root.iterdir()):
        match = EPISODE_RE.match(directory.name)
        narration = directory / "01_narration.md"
        if match and int(match.group(1)) >= args.start_episode and (args.end_episode is None or int(match.group(1)) <= args.end_episode) and narration.is_file():
            episodes.append((directory.name, narration, read_beats(narration)))
    if not episodes:
        raise SystemExit("No episode narration files found")

    for episode_id, narration_path, beats in episodes:
        output_dir = args.production_root / episode_id / "audio/local_voice"
        output_dir.mkdir(parents=True, exist_ok=True)
        source_text = json.dumps({"beats": beats}, ensure_ascii=False, indent=2) + "\n"
        source = output_dir / "inputs" / (hashlib.sha256(source_text.encode()).hexdigest() + ".json")
        source.parent.mkdir(exist_ok=True)
        source.write_text(source_text, encoding="utf-8")
        result = synthesize(
            workspace, source, output_dir, args.series, None, args.force,
            args.direction, str(args.voice) if args.voice else None,
            args.language, args.author_profile, gap_seconds=args.silence_ms / 1000,
        )

        normalized = Path(result["audio"])
        final_audio = normalized
        receipt_path = output_dir / "narration_beats.json"
        receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
        receipt.update({
            "episode_id": episode_id,
            "source": str(narration_path),
            "synthesis_source": str(source),
            "voice": str(workspace_path(voice_config.get("reference_audio"), root=workspace)) if voice_config.get("reference_audio") else None,
            "voice_direction": voice_config.get("direction"),
            "language": args.language or voice_config.get("language") or "zh",
            "silence_ms": args.silence_ms,
            "audio": "audio/local_voice/narration-normalized.wav",
            "audio_source": "audio/local_voice/narration-normalized.wav",
            "duration": round(duration(final_audio), 6),
            "backend_status": "synthesis_verified_pending_listening",
        })
        for beat in receipt.get("beats", []):
            audio = Path(beat["audio"])
            try:
                beat["audio"] = str(audio.relative_to(args.production_root / episode_id))
            except ValueError:
                beat["audio"] = str(audio)
        receipt_path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        (output_dir / "narration.txt").write_text("\n\n".join(beat["text"] for beat in beats) + "\n", encoding="utf-8")
        print(json.dumps({"episode": episode_id, "duration": duration(final_audio), "backend": result["backend"], "generated": result["generated"], "reused": result["reused"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
