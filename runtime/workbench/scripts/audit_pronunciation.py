#!/usr/bin/env python3
"""Create a non-blocking Chinese pronunciation review index for a series."""

from __future__ import annotations

import argparse
import json
import re
import hashlib
import yaml
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


def annotation_spans(value):
    spans = []
    cursor = 0
    last = 0
    for match in re.finditer(r"<([^<>|]+)\|([^<>|]+)>", value):
        cursor += len(value[last:match.start()])
        spans.append({"start": cursor, "end": cursor + len(match[1]), "text": match[1], "pronunciation": match[2]})
        cursor += len(match[1]); last = match.end()
    return spans


TARGET_CHAR = {"重影": "重", "重建": "重", "长期": "长", "生长": "长",
               "调节": "调", "调整": "调", "调药": "调", "抽血": "血", "血钠": "血",
               "多年间": "间", "应立即": "应", "还": "还"}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--workspace", type=Path, required=True)
    selection = ap.add_mutually_exclusive_group(required=True)
    selection.add_argument("--series", help="从workbench.yaml读取精确当前项目；推荐入口")
    selection.add_argument("--episodes", type=Path, help="兼容明确选集JSON；不猜最大版本")
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    root = args.workspace.resolve()
    if args.series:
        config = yaml.safe_load((root / "workbench.yaml").read_text())
        episodes = [{"id": eid, "project": row["project"]} for eid, row in
                    config["series"][args.series]["episodes"].items()]
    else:
        episodes = load(root / args.episodes)
    diagnostics = []
    rows = []
    for episode in episodes:
        project = (root / episode["project"]).resolve()
        config_path = project / "project.json"
        config = load(config_path) if config_path.is_file() else {}
        narration_path = project / config.get("narration", "preproduction/narration.json")
        if not narration_path.is_file():
            diagnostics.append({"episode": episode["id"], "code": "narration_missing", "project": str(project)})
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
                            "tts_control_present": any(
                                a["start"] <= index + phrase.index(TARGET_CHAR[phrase]) < a["end"]
                                for a in annotation_spans(beat.get("tts_text", beat["text"]))),
                            "requested_annotations": [a for a in annotation_spans(beat.get("tts_text", beat["text"]))
                                if a["start"] <= index + phrase.index(TARGET_CHAR[phrase]) < a["end"]],
                            "project": str(project),
                            "narration_sha256": hashlib.sha256(narration_path.read_bytes()).hexdigest(),
                            "source_offset": index,
                            "model_text": audio.get("model_text"),
                            "audio": audio.get("audio"),
                            "audio_pronunciation_review": (
                                "pending"
                                if not audio
                                else (load(Path(audio["audio"]).with_suffix(".json")).get("pronunciation_review", "pending")
                                 if audio.get("audio") and Path(audio["audio"]).with_suffix(".json").is_file()
                                 else "pending")
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
        "diagnostics": diagnostics,
        "confirmed_errors": [r for r in rows if r["audio_pronunciation_review"] in ("failed", "rejected")
                             or isinstance(r["audio_pronunciation_review"], dict) and
                             r["audio_pronunciation_review"].get("status") in ("failed", "rejected")],
        "method": "语境规则 + 可选 ASR 定位；不把规则、ASR、响度或 TTS 输入成功当作发音通过",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": out["status"], "targets": len(rows), "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
