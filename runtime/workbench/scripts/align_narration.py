#!/usr/bin/env python3
"""Whisper timing evidence for an explicit episode; approved words remain unchanged."""

import argparse, hashlib, json
from pathlib import Path


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
    cues = []
    for beat in receipt["beats"]:
        r = model.transcribe(
            beat["audio"],
            language="zh",
            condition_on_previous_text=False,
            word_timestamps=True,
            fp16=a.device.startswith("cuda"),
        )
        segments = r.get("segments", [])
        for s in segments:
            s["start"] += beat["start"]
            s["end"] += beat["start"]
            for w in s.get("words", []):
                w["start"] += beat["start"]
                w["end"] += beat["start"]
        result.append(
            {
                "id": beat["id"],
                "approved_text": beat["text"],
                "asr_text": r.get("text", ""),
                "segments": segments,
            }
        )
        cues.append(
            {
                # A recognizer can omit the opening phrase or final words.
                # Its partial window must not squeeze the complete editorial text.
                "start": beat["start"],
                "end": beat["end"],
                "text": beat["text"],
            }
        )
    a.output.mkdir(parents=True, exist_ok=True)
    data = {
        "voice_sha256": hashlib.sha256(Path(receipt["audio"]).read_bytes()).hexdigest(),
        "model": a.model,
        "beats": result,
        "full_listening": "pending",
        "text_authority": "narration.json",
        "timing_scope": "ASR窗口用于定位，整段提案保留真实声段区间；分句由导演结合原音校准",
    }
    (a.output / "alignment.json").write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    )
    (a.output / "cues.proposed.json").write_text(
        json.dumps(
            {"voice_sha256": data["voice_sha256"], "cues": cues},
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
