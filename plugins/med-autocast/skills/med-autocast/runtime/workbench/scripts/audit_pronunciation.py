#!/usr/bin/env python3
"""Create a non-blocking Chinese pronunciation review index for a series."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

RISK_PATTERNS = {
    "还": "按语境区分 HAI2（仍然/另外）与 HUAN2（归还）",
    "重影": "CHONG2 YING3（重复成影）",
    "重建": "CHONG2 JIAN4（重新建造）",
    "长期": "CHANG2 QI1",
    "生长": "SHENG1 ZHANG3",
    "调节": "TIAO2 JIE2",
    "调整": "TIAO2 ZHENG3",
    "调药": "TIAO2 YAO4",
    "抽血": "CHOU1 XUE4",
    "血钠": "XUE4 NA4",
    "多年间": "DUO1 NIAN2 JIAN1",
    "应立即": "YING1 LI4 JI2",
}


def load(path: Path):
    return json.loads(path.read_text())


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path, required=True)
    ap.add_argument("--episodes", type=Path, required=True, help="JSON list of {id,project}")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    episodes = load(args.episodes)
    rows = []
    for episode in episodes:
        project = Path(episode["project"])
        narration_path = project / "preproduction/narration.json"
        if not narration_path.is_file():
            continue
        narration = load(narration_path)
        receipt = project / "audio/narration_beats.json"
        receipt_data = load(receipt) if receipt.is_file() else {}
        by_id = {b["id"]: b for b in receipt_data.get("beats", [])}
        for beat in narration.get("beats", []):
            for phrase, expected in RISK_PATTERNS.items():
                start = 0
                while True:
                    index = beat["text"].find(phrase, start)
                    if index < 0:
                        break
                    audio = by_id.get(beat["id"], {})
                    rows.append(
                        {
                            "episode": episode["id"],
                            "beat": beat["id"],
                            "phrase": phrase,
                            "context": beat["text"],
                            "expected": expected,
                            "tts_control_present": bool(beat.get("tts_text")),
                            "audio": audio.get("audio"),
                            "audio_pronunciation_review": (
                                "pending"
                                if not audio
                                else audio.get("pronunciation_review", "pending")
                            ),
                            "status": "review_target",
                            "note": "AI/ASR 只定位；实际音频仍需正常速度听辨，ASR同字转写不能证明多音字读音",
                        }
                    )
                    start = index + len(phrase)
    out = {
        "schema": "medical_pronunciation_audit/v1",
        "status": "review_index_only",
        "episodes": len(episodes),
        "targets": rows,
        "confirmed_errors": [],
        "method": "语境规则 + 可选 ASR 定位；不把规则、ASR、响度或 TTS 输入成功当作发音通过",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": out["status"], "targets": len(rows), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
