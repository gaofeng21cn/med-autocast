#!/usr/bin/env python3
"""Selected IndexTTS environment only; input is a private local job file."""

import argparse, json, sys
from pathlib import Path


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--job", type=Path, required=True)
    args = p.parse_args()
    job = json.loads(args.job.read_text())
    sys.path.insert(0, job["runtime_root"])
    import torch, numpy as np
    from indextts.infer_v2_5 import IndexTTS2

    model = IndexTTS2(
        cfg_path=str(Path(job["model_root"]) / "config.yaml"),
        model_dir=job["model_root"],
        device=job["device"],
        use_bf16=job["device"].startswith("cuda"),
        use_cuda_kernel=False,
        use_qwen_emo=True,
    )
    for b in job["beats"]:
        torch.manual_seed(job["seed"])
        np.random.seed(job["seed"])
        model.infer(
            spk_audio_prompt=job["reference"],
            text=b["text"],
            output_path=b["output"],
            lang=job["language"],
            use_emo_text=True,
            emo_text=job["direction"],
            emo_alpha=job["emotion_alpha"],
            use_random=False,
            interval_silence=220,
            duration_factor=job["duration_factor"],
            verbose=False,
        )
        print(json.dumps({"beat": b["id"], "status": "synthesized"}), flush=True)


if __name__ == "__main__":
    main()
