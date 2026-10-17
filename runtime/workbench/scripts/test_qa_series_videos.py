#!/usr/bin/env python3
"""Narrow regression tests for the paper-project adapter in qa_series_videos."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qa_series_videos import (
    EPISODE_RE,
    episode_inputs,
    paper_alignment_metrics,
    paper_animation_gate,
    paper_cues,
    paper_format,
    select_paper_project,
)


class PaperProjectAdapterTests(unittest.TestCase):
    def test_episode_regex_includes_emergency_e00(self):
        match = EPISODE_RE.match("e00_low_glucose")
        self.assertIsNotNone(match)
        self.assertEqual(match.groups(), ("00", "low_glucose"))

    def test_explicit_current_project_pointer_wins_and_stale_pointer_fails(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary) / "03_example"
            current = episode / "v2"
            historical = episode / "v1"
            current.mkdir(parents=True)
            historical.mkdir()
            (current / "project.json").write_text("{}")
            (historical / "project.json").write_text("{}")
            self.assertEqual(select_paper_project(episode, {episode.name: current}), current)
            with self.assertRaises(ValueError):
                select_paper_project(episode, {episode.name: episode / "v3"})

    def test_score_cues_are_caption_diagnostics_not_asr(self):
        score = {"cues": [{"start": 0, "end": 1, "text": "垂体"}]}
        cues = paper_cues(score)
        self.assertEqual(cues[0]["lines"], ["垂体"])
        report = paper_alignment_metrics({
            "manifest": {"beats": [{"text": "垂体"}]},
            "cues": cues,
        })
        self.assertFalse(report["audio_recognition_performed"])
        self.assertIn("approved_caption_match_ratio", report)
        self.assertNotIn("approved_asr_match_ratio", report)

    def test_canvas_attributes_are_order_independent(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "index.html").write_text('<canvas id="stage" height="540" width="960"></canvas>')
            self.assertEqual(paper_format(project, {"fps": 30}), {"width": 960, "height": 540, "fps": 30})

    def test_paper_gate_never_marks_release_eligible(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            (project / "project.json").write_text(json.dumps({"schema": "paper_project/v1"}))
            report = paper_animation_gate({
                "project": project,
                "config": {},
                "score": {"shots": [{"id": "s01"}], "cues": [{"start": 0, "end": 1, "text": "a"}]},
                "current": {"release_eligible": True},
                "video": None,
            })
            self.assertFalse(report["release_eligible"])
            self.assertTrue(report["current_release_eligible"])
            self.assertIn("paper_render_missing_current_video", report["violations"])

    def test_paper_gate_diagnoses_replaced_current_bytes(self):
        with tempfile.TemporaryDirectory() as temporary:
            project = Path(temporary)
            video = project / "current.mp4"
            video.write_bytes(b"replacement candidate")
            report = paper_animation_gate({
                "project": project,
                "config": {},
                "score": {"shots": [{"id": "s01"}], "cues": [{"start": 0, "end": 1, "text": "a"}]},
                "current": {"sha256": "0" * 64},
                "video": video,
            })
            self.assertEqual(report["render_bindings"]["sha256"]["status"], "mismatch")
            self.assertIn("paper_render_binding_mismatch:sha256", report["violations"])

    def test_legacy_yaml_input_contract_remains_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            episode = Path(temporary)
            (episode / "audio/local_voice").mkdir(parents=True)
            plan = {"audio": {"source": "audio/local_voice/narration-normalized.wav"}, "subtitles": {"source": "captions.srt"}}
            inputs = episode_inputs(episode, plan)
            self.assertEqual(inputs["kind"], "production_plan")
            self.assertEqual(inputs["srt"], episode / "captions.srt")


if __name__ == "__main__":
    unittest.main()
