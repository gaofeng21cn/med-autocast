#!/usr/bin/env python3
"""Coordinate and editorial regressions without running a recognition model."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import sys

import align_narration
from build_episode_timelines import build_cues, visible_length
from paper_captions import caption_rows_text, caption_text


def evidence(text, start=1.2, end=6.0):
    return {"segments": [{"start": start, "end": end,
                         "words": [{"word": text, "start": start, "end": end}]}]}


class AlignmentTests(unittest.TestCase):
    def test_second_beat_stays_source_local_and_global_offset_is_added_once(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            voice, first, second = [root / name for name in ("voice.wav", "first.wav", "second.wav")]
            for index, path in enumerate((voice, first, second)):
                path.write_bytes(bytes([index + 1]) * 8)
            second_text = "这份检查首先记录结构变化和身体的反应。后一条说明需要结合完整的激素检查结果再判断。"
            receipt = {"audio": str(voice), "beats": [
                {"id": "B01", "text": "第一句。", "audio": str(first), "start": .32, "end": 8.32},
                {"id": "B02", "text": second_text, "audio": str(second), "start": 30.0, "end": 38.0}]}
            receipt_path = root / "receipt.json"
            receipt_path.write_text(json.dumps(receipt, ensure_ascii=False))
            model = SimpleNamespace(transcribe=lambda path, **kwargs:
                {"text": "识别器没有权威正文", **evidence(receipt["beats"][0 if path == str(first) else 1]["text"])})
            fake = SimpleNamespace(load_model=lambda *args, **kwargs: model)
            args = ["align_narration", "--receipt", str(receipt_path), "--output", str(root / "aligned"), "--model", "fake"]
            with patch.dict(sys.modules, {"whisper": fake}), patch.object(sys, "argv", args):
                align_narration.main()
            alignment = json.loads((root / "aligned/alignment.json").read_text())
            proposal = json.loads((root / "aligned/cues.proposed.json").read_text())
            self.assertEqual(alignment["timing_coordinates"], "source_local_seconds")
            self.assertEqual(alignment["beats"][1]["segments"][0]["start"], 1.2)
            self.assertEqual(alignment["voice_sha256"], hashlib.sha256(voice.read_bytes()).hexdigest())
            self.assertEqual(proposal["source_sha256"]["B02"], hashlib.sha256(second.read_bytes()).hexdigest())
            rows = [cue for cue in proposal["cues"] if cue["beat_id"] == "B02"]
            self.assertGreater(len(rows), 1)
            self.assertAlmostEqual(rows[0]["start"], 31.2)
            self.assertTrue(all(30.0 <= row["start"] < row["end"] <= 38.0 for row in rows))
            self.assertEqual(caption_rows_text(second_text, rows), caption_text(second_text))
            self.assertTrue(any("\n" in row["text"] for row in rows))
            self.assertTrue(all(visible_length(line) <= 20 for row in rows for line in row["text"].splitlines()))

    def test_explicit_global_conversion_matches_source_local_with_trim_once(self):
        manifest = {"beats": [{"id": "B02", "text": "后一条说明。", "start": 30.0, "end": 38.0, "trimmed_head_seconds": .4}]}
        local = {"timing_coordinates": "source_local_seconds", "beats": [{"id": "B02", **evidence("后一条说明", 1.2, 6.0)}]}
        global_alignment = deepcopy(local)
        global_alignment["timing_coordinates"] = "timeline_global_seconds"
        beat = global_alignment["beats"][0]
        beat["source_to_timeline_offset_seconds"] = 29.6
        for segment in beat["segments"]:
            for row in [segment, *segment["words"]]:
                row["start"] += 29.6
                row["end"] += 29.6
        before = deepcopy(global_alignment)
        self.assertEqual(build_cues(manifest, local), build_cues(manifest, global_alignment))
        self.assertEqual(global_alignment, before)
        self.assertAlmostEqual(build_cues(manifest, local)[0]["start"], 30.8)

    def test_undeclared_origin_is_diagnosed_without_guess_or_lost_text(self):
        text = "完整的批准正文需要保留。后一条说明也不能丢失。"
        manifest = {"beats": [{"id": "B02", "text": text, "start": 30.0, "end": 38.0}]}
        for coordinates in (None, "timeline_global_seconds"):
            with self.subTest(coordinates=coordinates):
                alignment = {"beats": [{"id": "B02", **evidence("后一条说明", 31.2, 36.0)}]}
                if coordinates:
                    alignment["timing_coordinates"] = coordinates
                cues = build_cues(manifest, alignment)
                self.assertEqual(caption_rows_text(text, cues), caption_text(text))
                self.assertTrue(all(row["timing_source"] == "character_ratio_fallback" and row["timing_note"] for row in cues))
                self.assertTrue(all(30.0 <= row["start"] < row["end"] <= 38.0 for row in cues))

    def test_partial_recognition_keeps_unrecognized_opening_and_tail(self):
        text = "完整开头。识别器只得到中间这一句。完整尾句也要保留。"
        manifest = {"beats": [{"id": "B02", "text": text, "start": 30.0, "end": 38.0}]}
        alignment = {"timing_coordinates": "source_local_seconds", "beats": [{"id": "B02", **evidence("识别器只得到中间这一句", 2.0, 6.0)}]}
        cues = build_cues(manifest, alignment)
        self.assertEqual(caption_rows_text(text, cues), caption_text(text))
        self.assertEqual(cues[0]["start"], 30.0)
        self.assertEqual(cues[-1]["end"], 38.0)

    def test_missing_word_times_keeps_split_editorial_proposal(self):
        text = "第一句。后一条说明。"
        manifest = {"beats": [{"id": "B02", "text": text, "start": 30.0, "end": 38.0}]}
        alignment = {"timing_coordinates": "source_local_seconds", "beats": [{"id": "B02", "segments": [{"start": 2.0, "end": 6.0, "words": []}]}]}
        cues = build_cues(manifest, alignment)
        self.assertEqual(len(cues), 2)
        self.assertEqual(caption_rows_text(text, cues), caption_text(text))
        self.assertTrue(all(row["timing_note"] for row in cues))

    def test_source_mismatch_never_consumes_wrong_acoustic_timing(self):
        manifest = {"beats": [{"id": "B02", "text": "后一条说明。", "start": 30.0, "end": 38.0, "source_sha256": "current"}]}
        alignment = {"timing_coordinates": "source_local_seconds", "beats": [{"id": "B02", "source_sha256": "old", **evidence("后一条说明")} ]}
        cue = build_cues(manifest, alignment)[0]
        self.assertEqual(cue["timing_source"], "character_ratio_fallback")
        self.assertEqual(cue["timing_note"], "alignment_source_sha256_mismatch")

    def test_caption_layout_preserves_numeric_and_english_word_boundaries(self):
        text = "结果为1.5，需要记录1-2次变化。U.S. adults需要保留原文词间空格。"
        cues = build_cues({"beats": [{"id": "B02", "text": text, "start": 30.0, "end": 38.0}]})
        self.assertEqual(caption_rows_text(text, cues), caption_text(text))
        self.assertTrue(all(len(row["text"].splitlines()) <= 2 for row in cues))
        self.assertTrue(all(visible_length(line) <= 20 for row in cues for line in row["text"].splitlines()))


if __name__ == "__main__":
    unittest.main()
