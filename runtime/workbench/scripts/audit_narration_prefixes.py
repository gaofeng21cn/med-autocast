#!/usr/bin/env python3
"""Audit the first words of current narration takes.

This consumes an independent frozen-source ASR index.  It is deliberately a
locator: ASR can identify a suspicious prefix, but cannot prove that a word
was spoken correctly, that the tone is stable, or that the final MP4 contains
the same audio.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter
from pathlib import Path


ANNOTATION = re.compile(r"<([^<>|]+)\|([^<>|]+)>")
PUNCTUATION = re.compile(r"[^\u4e00-\u9fffA-Za-z0-9]+")


def spoken_text(value: str) -> str:
    """Remove pronunciation markup and formatting for prefix comparison."""
    value = ANNOTATION.sub(lambda match: match.group(1), str(value or ""))
    return PUNCTUATION.sub("", value)


def classify(row: dict, prefix_length: int = 8) -> dict:
    expected = spoken_text(row.get("approved_text", ""))
    asr = spoken_text((row.get("padded_asr") or {}).get("text", ""))
    expected_prefix = expected[:prefix_length]
    asr_prefix = asr[:prefix_length]
    locator = row.get("padded_locator") or {}
    omission = list(locator.get("possible_leading_char_omission") or [])
    if not omission and expected_prefix:
        # Keep this conservative: only a contiguous suffix of the expected
        # prefix counts, and it must be long enough to be meaningful.
        for offset in range(1, min(6, len(expected_prefix) - 2)):
            if asr.startswith(expected_prefix[offset:]) and len(expected_prefix[offset:]) >= 4:
                omission.append(offset)
    second_model = row.get("second_model_evidence") or []
    if omission:
        category = "possible_leading_omission"
    elif second_model or row.get("previous_pronunciation_locators"):
        category = "must_listen_pronunciation_locator"
    elif expected_prefix and not asr.startswith(expected_prefix[:4]):
        category = "asr_textual_difference"
    elif expected_prefix and asr_prefix != expected_prefix:
        category = "asr_later_prefix_difference"
    else:
        category = "no_prefix_divergence"
    return {
        "series": row.get("series"),
        "episode": row.get("episode"),
        "beat": row.get("beat"),
        "source": row.get("source"),
        "source_sha256": row.get("source_sha256"),
        "approved_prefix": expected_prefix,
        "asr_prefix": asr_prefix,
        "category": category,
        "possible_leading_char_omission": omission,
        "textual_first_four_equal": bool(asr.startswith(expected[:4])) if expected else False,
        "pronunciation_review": "pending",
        "full_listening": "pending",
        "note": "仅作正常速度听辨定位；ASR、波形和文本匹配都不能证明发音、语气或最终成片通过。",
    }


def audit(index: dict, prefix_length: int = 8) -> dict:
    rows = [classify(row, prefix_length) for row in index.get("rows", [])]
    counts = Counter(row["category"] for row in rows)
    return {
        "schema": "narration_prefix_review/v1",
        "source_index": index.get("schema"),
        "source_index_path": index.get("source_index_path"),
        "prefix_length": prefix_length,
        "episodes": len({(row.get("series"), row.get("episode")) for row in rows}),
        "source_takes": len(rows),
        "summary": {
            "no_prefix_divergence": counts["no_prefix_divergence"],
            "asr_textual_difference": counts["asr_textual_difference"],
            "asr_later_prefix_difference": counts["asr_later_prefix_difference"],
            "possible_leading_omission": counts["possible_leading_omission"],
            "must_listen_pronunciation_locator": counts["must_listen_pronunciation_locator"],
            "manual_listening_required": sum(
                counts[key] for key in (
                    "possible_leading_omission",
                    "must_listen_pronunciation_locator",
                    "asr_textual_difference",
                    "asr_later_prefix_difference",
                )
            ),
        },
        "evidence_boundary": "ASR is a locator only; no pronunciation, tone, complete listening, medical correctness, or final MP4 approval is inferred.",
        "rows": rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-asr", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--prefix-length", type=int, default=8)
    args = parser.parse_args()
    index = json.loads(args.source_asr.read_text(encoding="utf-8"))
    index["source_index_path"] = str(args.source_asr.resolve())
    report = audit(index, max(4, min(16, args.prefix_length)))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"episodes": report["episodes"], "source_takes": report["source_takes"], "summary": report["summary"], "output": str(args.output)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
