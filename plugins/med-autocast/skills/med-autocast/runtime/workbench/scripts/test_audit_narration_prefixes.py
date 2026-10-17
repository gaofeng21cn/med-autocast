#!/usr/bin/env python3
import unittest

from audit_narration_prefixes import audit, classify


class PrefixAuditTests(unittest.TestCase):
    def test_markup_is_removed_without_losing_spoken_character(self):
        row = {
            "series": "demo", "episode": "01", "beat": "B01",
            "approved_text": "看字还清楚。",
            "tts_text": "看字<还|HAI2>清楚。",
            "padded_asr": {"text": "看字还清楚"},
        }
        result = classify(row)
        self.assertEqual(result["category"], "no_prefix_divergence")
        self.assertEqual(result["approved_prefix"], "看字还清楚")

    def test_suffix_match_is_only_a_possible_omission(self):
        row = {"approved_text": "第一句完整内容。", "padded_asr": {"text": "句完整内容"}}
        result = classify(row)
        self.assertEqual(result["category"], "possible_leading_omission")
        self.assertTrue(result["possible_leading_char_omission"])
        self.assertEqual(result["pronunciation_review"], "pending")

    def test_textual_difference_does_not_become_audio_failure(self):
        row = {"approved_text": "垂体占位。", "padded_asr": {"text": "垂体站位"}}
        result = classify(row)
        self.assertEqual(result["category"], "asr_textual_difference")
        self.assertEqual(result["full_listening"], "pending")

    def test_aggregate_keeps_all_rows_and_boundary(self):
        report = audit({"schema": "frozen_source_asr_index/v1", "rows": [
            {"series": "a", "episode": "1", "approved_text": "第一句", "padded_asr": {"text": "第一句"}},
            {"series": "a", "episode": "1", "approved_text": "第二句", "padded_asr": {"text": "句"}},
        ]})
        self.assertEqual(report["source_takes"], 2)
        self.assertEqual(report["episodes"], 1)
        self.assertIn("manual_listening_required", report["summary"])
        self.assertIn("ASR is a locator only", report["evidence_boundary"])


if __name__ == "__main__":
    unittest.main()
