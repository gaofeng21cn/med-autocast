#!/usr/bin/env python3
"""Regression checks for incomplete source sample audits falsely passing."""
import array
import json
import subprocess
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import audit_narration_samples as audit


class NarrationSampleAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.project = Path(self.temp.name)
        self.audio = self.project / "audio"
        self.audio.mkdir()
        self.samples = array.array("h", [0, 1, -1, 2, -2] * 480)
        self.write_wav(self.audio / "take.wav", self.samples)
        self.write_wav(self.audio / "narration.wav", self.samples)
        self.beat = {"id": "B01", "audio": "audio/take.wav", "start": 0,
                     "end": len(self.samples) / 24000}
        self.receipt([self.beat])

    @staticmethod
    def write_wav(path, samples):
        with wave.open(str(path), "wb") as handle:
            handle.setnchannels(1)
            handle.setsampwidth(2)
            handle.setframerate(24000)
            handle.writeframes(samples.tobytes())

    def receipt(self, beats):
        (self.audio / "narration_beats.json").write_text(json.dumps({
            "splice": {"schema": "narration_splice/v2"}, "beats": beats,
        }))

    def inspect(self):
        with patch.object(audit, "decode", return_value=self.samples):
            return audit.inspect(self.project)

    def test_complete_take_stays_a_structural_pass(self):
        result = self.inspect()
        self.assertEqual(result["status"], "passed")
        self.assertEqual(result["source_takes_checked"], 1)
        self.assertEqual(result["flags"], [])
        self.assertIn("does not prove pronunciation", result["note"])

    def test_missing_take_fails_the_episode_and_is_not_counted_as_checked(self):
        self.beat["audio"] = "audio/missing.wav"
        self.receipt([self.beat])
        result = self.inspect()
        self.assertEqual(result["status"], "needs_repair")
        self.assertIn("B01:missing_source_take", result["flags"])
        self.assertEqual(result["source_takes_checked"], 0)

    def test_empty_beats_cannot_pass(self):
        self.receipt([])
        result = self.inspect()
        self.assertEqual(result["status"], "needs_repair")
        self.assertIn("missing_or_empty_beats", result["flags"])

    def test_removed_head_samples_are_reported(self):
        self.write_wav(self.audio / "narration.wav", self.samples[120:])
        result = self.inspect()
        self.assertEqual(result["status"], "needs_repair")
        self.assertIn("B01:raw_track_does_not_contain_exact_source_take", result["flags"])

    def test_bad_beat_does_not_prevent_checking_later_take(self):
        self.receipt([None, {"id": "B00", "start": "NaN", "end": 1}, self.beat])
        result = self.inspect()
        self.assertEqual(result["status"], "needs_repair")
        self.assertEqual(result["source_takes_checked"], 1)
        self.assertIn("B00:invalid_beat_time_range", result["flags"])
        self.assertEqual(result["beats"][-1]["flags"], [])

    def test_decode_failure_becomes_a_readable_diagnostic(self):
        with patch.object(audit, "decode", side_effect=subprocess.CalledProcessError(1, "ffmpeg")):
            result = audit.inspect(self.project)
        self.assertEqual(result["status"], "needs_repair")
        self.assertIn("B01:source_take_decode_failed", result["flags"])

    def test_registered_project_with_missing_receipt_remains_in_the_batch(self):
        workspace = self.project / "workspace"
        workspace.mkdir()
        (workspace / "workbench.yaml").write_text(
            "series:\n  test:\n    episodes:\n      episode:\n        project: productions/missing\n"
        )
        projects = list(audit.projects(workspace))
        self.assertEqual(projects, [(workspace / "productions/missing").resolve()])
        self.assertEqual(audit.inspect(projects[0])["status"], "needs_repair")


if __name__ == "__main__":
    unittest.main()
