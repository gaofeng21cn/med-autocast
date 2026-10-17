#!/usr/bin/env python3
"""Whisper timing evidence for an explicit episode; approved words remain unchanged."""

import argparse, hashlib, json
from pathlib import Path
from build_episode_timelines import build_cues


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--receipt", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--device", default="cpu")
    a = p.parse_args()
    import whisper

    receipt = json.loads(a.receipt.read_text())
    model = whisper.load_model(a.model, device=a.device)
    result = []
    for beat in receipt["beats"]:
        source = Path(beat["audio"])
        source_sha = hashlib.sha256(source.read_bytes()).hexdigest()
        r = model.transcribe(
            str(source),
            language="zh",
            condition_on_previous_text=False,
            word_timestamps=True,
            fp16=a.device.startswith("cuda"),
        )
        segments = r.get("segments", [])
        result.append(
            {
                "id": beat["id"],
                "approved_text": beat["text"],
                "asr_text": r.get("text", ""),
                "source_audio": str(source.resolve()),
                "source_sha256": source_sha,
                "timing_coordinates": "source_local_seconds",
                "segments": segments,
            }
        )
    a.output.mkdir(parents=True, exist_ok=True)
    data = {
        "schema": "whisper_word_alignment/v2",
        "voice_sha256": hashlib.sha256(Path(receipt["audio"]).read_bytes()).hexdigest(),
        "narration_receipt_sha256": hashlib.sha256(a.receipt.read_bytes()).hexdigest(),
        "model": a.model,
        "timing_coordinates": "source_local_seconds",
        "beats": result,
        "full_listening": "pending",
        "text_authority": "narration.json",
        "timing_scope": "ASR为源音频局部秒数；字幕只加一次段落起点，保留完整批准正文并拆句/双行，实际同期仍需审听",
    }
    cues = build_cues(receipt, data)
    (a.output / "alignment.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    (a.output / "cues.proposed.json").write_text(
        json.dumps(
            {
                "voice_sha256": data["voice_sha256"],
                "narration_receipt_sha256": data["narration_receipt_sha256"],
                "source_sha256": {beat["id"]: beat["source_sha256"] for beat in result},
                "timing_coordinates": "timeline_global_seconds",
                "timing_review": "draft",
                "text_authority": data["text_authority"],
                "full_listening": "pending",
                "cues": cues,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n"
    )
    print(
        json.dumps(
            {
                "status": "timing_proposed",
                "output": str(a.output),
                "approved_words_preserved": True,
            }
        )
    )


if __name__ == "__main__":
    main()
