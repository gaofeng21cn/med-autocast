#!/usr/bin/env python3
"""Load VoxCPM2 once and synthesize a private local narration job."""

from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--job", type=Path, required=True)
    args = parser.parse_args()
    job = json.loads(args.job.read_text(encoding="utf-8"))

    runtime_profile = job.get("runtime_profile", {})
    # MPS reads these at initialization, so apply them before importing Torch.
    for key in ("low", "high"):
        ratio = runtime_profile.get(f"mps_{key}_watermark_ratio")
        if ratio is not None:
            os.environ[f"PYTORCH_MPS_{key.upper()}_WATERMARK_RATIO"] = str(float(ratio))
    if runtime_profile.get("normalize", False):
        raise ValueError("Cached VoxCPM generation requires normalize=false")
    started = time.perf_counter()

    import numpy as np
    import soundfile as sf
    import torch
    from voxcpm import VoxCPM

    device = job.get("device") or ("mps" if torch.backends.mps.is_available() else "cpu")
    model = VoxCPM.from_pretrained(
        job["model_root"],
        load_denoiser=bool(runtime_profile.get("load_denoiser", False)),
        optimize=bool(runtime_profile.get("optimize", False)),
        device=device,
    )
    reference = job["reference"]
    direction = job.get("direction", "Professional medical education narration, clear and composed.")
    seed = int(job.get("seed", 1601))
    settings = {
        "cfg_value": float(runtime_profile.get("cfg_value", 2.0)),
        "inference_timesteps": int(runtime_profile.get("inference_timesteps", 10)),
        "max_len": 4096,
        "retry_badcase": bool(runtime_profile.get("retry_badcase", False)),
    }

    def sync() -> None:
        if device.startswith("mps") and hasattr(torch, "mps") and torch.backends.mps.is_available():
            torch.mps.synchronize()

    prompt_cache = model.tts_model.build_prompt_cache(reference_wav_path=reference)
    sync()
    print(json.dumps({"status": "model_and_reference_ready", "reference_encodings": 1,
                      "seconds": round(time.perf_counter() - started, 3),
                      "device": device,
                      "mps_watermarks": {key: os.environ.get(f"PYTORCH_MPS_{key.upper()}_WATERMARK_RATIO")
                                         for key in ("low", "high")}}, ensure_ascii=False), flush=True)

    for beat in job["beats"]:
        started = time.perf_counter()
        torch.manual_seed(seed)
        np.random.seed(seed)
        sync()
        model_text = beat.get("model_text", beat.get("text", ""))
        prompt = f"({direction}){model_text}" if direction else model_text
        wav, _, _ = model.tts_model.generate_with_prompt_cache(
            target_text=prompt, prompt_cache=prompt_cache, **settings
        )
        audio = wav.squeeze(0).cpu().numpy()
        if not audio.size or not np.isfinite(audio).all() or np.max(np.abs(audio)) < 1e-6:
            raise ValueError(f"Invalid waveform for {beat['id']}")
        output = Path(beat["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        sample_rate = int(model.tts_model.sample_rate)
        sf.write(output, audio, sample_rate)
        del wav, audio
        sync()
        if device.startswith("mps") and hasattr(torch, "mps"):
            torch.mps.empty_cache()
        print(json.dumps({"beat": beat["id"], "status": "synthesized", "sample_rate": sample_rate,
                          "seconds": round(time.perf_counter() - started, 3)}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()
