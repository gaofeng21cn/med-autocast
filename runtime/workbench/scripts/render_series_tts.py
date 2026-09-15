#!/usr/bin/env python3
"""Render reviewed episode narration beat-by-beat with one IndexTTS model load."""

import argparse
import json
import re
import wave
from pathlib import Path
from workbench_config import load_author_profile, production_root_for, series_paths, workspace_path

try:
    from indextts.infer_v2_5 import IndexTTS2
except ImportError as exc:  # keep --help usable before runtime install
    IndexTTS2 = None
    _INDEXTTS_IMPORT_ERROR = exc


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
                current["text"] = "".join(paragraphs).strip()
                beats.append(current)
            current = {"id": match.group(1), "title": match.group(2).strip()}
            paragraphs = []
            continue
        if line.startswith("## 朗读规则"):
            break
        if current and line.strip():
            paragraphs.append(line.strip())
    if current:
        current["text"] = "".join(paragraphs).strip()
        beats.append(current)
    if not beats or any(not beat["text"] for beat in beats):
        raise ValueError(f"No complete narration beats in {path}")
    return beats


def duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        return wav.getnframes() / wav.getframerate()


def concat_wavs(paths: list[Path], target: Path, silence_ms: int) -> list[dict]:
    manifest = []
    cursor = 0.0
    with wave.open(str(paths[0]), "rb") as first:
        params = first.getparams()
    silence_frames = round(params.framerate * silence_ms / 1000)
    silence = b"\x00" * silence_frames * params.sampwidth * params.nchannels
    with wave.open(str(target), "wb") as output:
        output.setparams(params)
        for index, path in enumerate(paths):
            with wave.open(str(path), "rb") as source:
                if (source.getnchannels(), source.getsampwidth(), source.getframerate()) != (
                    params.nchannels,
                    params.sampwidth,
                    params.framerate,
                ):
                    raise ValueError(f"Incompatible WAV parameters: {path}")
                frames = source.readframes(source.getnframes())
                beat_duration = source.getnframes() / source.getframerate()
            start = cursor
            output.writeframes(frames)
            cursor += beat_duration
            manifest.append({"start": round(start, 6), "end": round(cursor, 6)})
            if index != len(paths) - 1:
                output.writeframes(silence)
                cursor += silence_ms / 1000
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--content-root", type=Path)
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--model-root", type=Path, required=True)
    parser.add_argument("--voice", type=Path)
    parser.add_argument("--author-profile", type=Path)
    parser.add_argument("--series")
    parser.add_argument("--emotion")
    parser.add_argument("--language")
    parser.add_argument("--start-episode", type=int, default=1)
    parser.add_argument("--silence-ms", type=int, default=220)
    parser.add_argument(
        "--device",
        default="auto",
        help="推理设备：auto/cuda:0/mps/cpu；默认按 CUDA→MPS→CPU 探测",
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    args.production_root = production_root_for(args.series, args.production_root)
    if args.series:
        registered_content = series_paths(args.series)["content_root"] / "episodes"
        if args.content_root and args.content_root.resolve() != registered_content.resolve():
            raise ValueError("--content-root conflicts with --series")
        args.content_root = registered_content
    if not args.content_root:
        parser.error("Pass --series or --content-root")

    voice = args.voice
    _, author = load_author_profile(profile_path=args.author_profile, series_id=args.series)
    reference_audio = author.get("voice", {}).get("reference_audio")
    if voice is None and reference_audio:
        voice = workspace_path(reference_audio)
    if voice is None or not voice.is_file():
        raise SystemExit("No reference voice found; configure voice.reference_audio or pass --voice")
    voice_config = (author or {}).get("voice", {})
    emotion = args.emotion or voice_config.get("direction") or "温柔、可信、耐心、自然，不播音腔"
    language = args.language or voice_config.get("language") or "zh"

    if IndexTTS2 is None:
        raise SystemExit(
            "IndexTTS 未安装，请先运行 backends/indextts/setup_mac.sh 或使用 4090 环境。"
            f" ({_INDEXTTS_IMPORT_ERROR})"
        )

    device = args.device
    if device == "auto":
        try:
            import torch

            if torch.cuda.is_available():
                device = "cuda:0"
            elif torch.backends.mps.is_available():
                device = "mps"
            else:
                device = "cpu"
        except Exception:
            device = "cpu"
    if device.startswith("cuda"):
        use_bf16 = True
    else:
        # MPS/CPU do not support the CUDA-only acceleration path used by the
        # workstation setup. Keep the local path explicit and conservative.
        use_bf16 = False

    episodes = []
    for directory in sorted(args.content_root.iterdir()):
        match = EPISODE_RE.match(directory.name)
        narration = directory / "01_narration.md"
        if match and int(match.group(1)) >= args.start_episode and narration.is_file():
            episodes.append((directory.name, narration, read_beats(narration)))
    if not episodes:
        raise SystemExit("No episode narration files found")

    model = IndexTTS2(
        cfg_path=str(args.model_root / "checkpoints/config.yaml"),
        model_dir=str(args.model_root / "checkpoints"),
        use_bf16=use_bf16,
        device=device,
        use_cuda_kernel=False,
        use_qwen_emo=True,
    )

    for episode_id, narration_path, beats in episodes:
        output_dir = args.production_root / episode_id / "audio/local_voice"
        beat_dir = output_dir / "beats"
        beat_dir.mkdir(parents=True, exist_ok=True)
        beat_paths = []
        for beat in beats:
            output = beat_dir / f"{beat['id'].lower()}.wav"
            if args.force or not output.is_file():
                model.infer(
                    spk_audio_prompt=str(voice),
                    text=beat["text"],
                    output_path=str(output),
                    lang=language,
                    use_emo_text=True,
                    emo_text=emotion,
                    emo_alpha=0.6,
                    interval_silence=220,
                    duration_factor=1.05,
                    verbose=False,
                )
            beat_paths.append(output)

        combined = output_dir / "index-tts25-narration.wav"
        timings = concat_wavs(beat_paths, combined, args.silence_ms)
        for beat, timing, beat_path in zip(beats, timings, beat_paths):
            beat.update(timing)
            beat["audio"] = str(beat_path.relative_to(args.production_root / episode_id))
            beat["duration"] = round(duration(beat_path), 6)
        (output_dir / "narration_beats.json").write_text(
            json.dumps(
                {
                    "episode_id": episode_id,
                    "source": str(narration_path),
                    "voice": str(voice),
                    "voice_direction": emotion,
                    "language": language,
                    "silence_ms": args.silence_ms,
                    "duration": round(duration(combined), 6),
                    "beats": beats,
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        (output_dir / "narration.txt").write_text(
            "\n\n".join(beat["text"] for beat in beats) + "\n", encoding="utf-8"
        )
        print(
            json.dumps(
                {"episode": episode_id, "duration": duration(combined), "device": device},
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
