#!/usr/bin/env python3
"""Transcribe final IndexTTS beat audio with Whisper word timestamps."""

import argparse
import json
import math
import re
from pathlib import Path
from workbench_config import production_root_for

import numpy as np
import soundfile as sf
import whisper
from scipy.signal import resample_poly


EPISODE_RE = re.compile(r"^(\d{2})_(.+)$")
WHISPER_SAMPLE_RATE = 16_000
ALIGNMENT_IGNORED_RE = re.compile(r"[\s，。；：、！？,.!?;:、“”‘’（）()《》<>\-�]+")


def alignment_text(text: str) -> str:
    return ALIGNMENT_IGNORED_RE.sub("", text).upper()


def load_wav(path: Path) -> np.ndarray:
    """Load PCM audio without relying on a system ffmpeg executable."""
    audio, sample_rate = sf.read(path, dtype="float32", always_2d=False)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate != WHISPER_SAMPLE_RATE:
        divisor = math.gcd(sample_rate, WHISPER_SAMPLE_RATE)
        audio = resample_poly(
            audio,
            WHISPER_SAMPLE_RATE // divisor,
            sample_rate // divisor,
        ).astype(np.float32)
    return np.ascontiguousarray(audio, dtype=np.float32)


def compact_segment(segment: dict) -> dict:
    return {
        "start": round(float(segment["start"]), 6),
        "end": round(float(segment["end"]), 6),
        "text": segment.get("text", "").strip(),
        "words": [
            {
                "start": round(float(word["start"]), 6),
                "end": round(float(word["end"]), 6),
                "word": word.get("word", ""),
                "probability": round(float(word.get("probability", 0.0)), 6),
            }
            for word in segment.get("words", [])
            if "start" in word and "end" in word
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--series")
    parser.add_argument("--model", required=True, help="Whisper model name or local .pt path")
    parser.add_argument("--device", default="cuda")
    parser.add_argument("--episode", action="append")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    args.production_root = production_root_for(args.series, args.production_root)

    model = whisper.load_model(args.model, device=args.device)
    selected = set(args.episode or [])
    results = []
    for episode_dir in sorted(args.production_root.iterdir()):
        if not EPISODE_RE.match(episode_dir.name) or (selected and episode_dir.name not in selected):
            continue
        manifest_path = episode_dir / "audio/local_voice/narration_beats.json"
        if not manifest_path.is_file():
            continue
        output_path = episode_dir / "audio/local_voice/whisper-alignment.json"
        if output_path.is_file() and not args.force:
            results.append({"episode": episode_dir.name, "status": "existing"})
            continue

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        beat_results = []
        for beat in manifest["beats"]:
            audio_path = episode_dir / beat["audio"]
            result = model.transcribe(
                load_wav(audio_path),
                language=manifest.get("language", "zh"),
                task="transcribe",
                initial_prompt=None,
                condition_on_previous_text=False,
                word_timestamps=True,
                fp16=args.device.startswith("cuda"),
                verbose=False,
            )
            segments = [compact_segment(segment) for segment in result.get("segments", [])]
            asr_text = "".join(segment["text"] for segment in segments)
            timed_text = "".join(
                word["word"] for segment in segments for word in segment.get("words", [])
            )
            word_coverage = len(alignment_text(timed_text)) / max(1, len(alignment_text(asr_text)))
            if word_coverage < 0.9:
                raise RuntimeError(
                    f"Incomplete Whisper word timestamps for {episode_dir.name} {beat['id']}: "
                    f"coverage={word_coverage:.3f}"
                )
            beat_results.append(
                {
                    "id": beat["id"],
                    "approved_text": beat["text"],
                    "asr_text": asr_text,
                    "word_timing_coverage": round(word_coverage, 6),
                    "segments": segments,
                }
            )

        payload = {
            "schema": "whisper_word_alignment/v1",
            "episode_id": episode_dir.name,
            "model": args.model,
            "device": args.device,
            "language": "zh",
            "word_timestamps": True,
            "text_authority": "approved_narration",
            "prompt_mode": "none",
            "beats": beat_results,
        }
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        results.append({"episode": episode_dir.name, "status": "transcribed", "beats": len(beat_results)})
        print(json.dumps(results[-1], ensure_ascii=False), flush=True)

    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
