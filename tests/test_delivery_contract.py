import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
#!/usr/bin/env python3

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from delivery_contract import animation_gate, release_eligible


class DeliveryContractTests(unittest.TestCase):
    def make_episode(
        self,
        root: Path,
        classes: list[str],
        backend: str = "seedance_api",
    ) -> tuple[Path, dict]:
        episode = root / "productions/02_example"
        candidates = episode / "candidates"
        candidates.mkdir(parents=True)
        timeline = []
        segments = []
        for index, visual_class in enumerate(classes, 1):
            segment_id = f"B{index:02d}"
            source = f"shot-{index}.mp4"
            (candidates / source).touch()
            timeline.append(
                {"segment_id": segment_id, "source": source, "start": (index - 1) * 10, "end": index * 10}
            )
            segment = {
                "segment_id": segment_id,
                "source": source,
                "visual_class": visual_class,
                "motion_review": "approved_watchable_motion",
                "audio_visual_alignment_review": "approved_audio_visual_alignment",
            }
            if visual_class not in {"deterministic_animation", "deterministic_hand_drawn_animation"}:
                segment["backend_id"] = backend
            if visual_class in {"deterministic_animation", "deterministic_hand_drawn_animation"}:
                segment["supporting_explainer_only"] = True
            segments.append(segment)
        plan = {
            "delivery": {
                "visual_requirement": "hand_drawn_explainer_animation",
                "visual_style": "hand_drawn_medical_explainer",
                "animation_mode": "hand_drawn_patient_explainer_animation",
                "author_profile": "example_author",
                "primary_video_backend": backend,
                "visual_manifest": "visual_delivery_manifest.json",
                "static_animatic_allowed_as_final": False,
            },
            "visual_timeline": timeline,
        }
        manifest = {
            "schema": "medical_video_visual_delivery/v4",
            "delivery_class": "final_animation",
            "visual_style": "hand_drawn_medical_explainer",
            "animation_mode": "hand_drawn_patient_explainer_animation",
            "author_profile": "example_author",
            "primary_video_backend": backend,
            "visual_style_review": "approved",
            "viewer_engagement_review": "approved",
            "noncontradiction_review": "approved",
            "audio_visual_alignment_review": "approved",
            "review_status": "approved",
            "release_eligible": True,
            "segments": segments,
        }
        (episode / "visual_delivery_manifest.json").write_text(json.dumps(manifest))
        return episode, plan

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_registered_generative_backend_passes(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary), ["generative_animation"]
            )
            self.assertEqual(animation_gate(episode, plan)["status"], "passed")

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_legacy_h3_manifest_remains_compatible(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary), ["minimax_h3_hand_drawn_animation"]
            )
            plan["delivery"].pop("author_profile")
            plan["delivery"].pop("primary_video_backend")
            plan["delivery"]["primary_generator"] = "MiniMax H3-Base"
            manifest_path = episode / "visual_delivery_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["schema"] = "medical_video_visual_delivery/v1"
            manifest.pop("author_profile")
            manifest.pop("primary_video_backend")
            manifest["primary_generator"] = "MiniMax H3-Base"
            manifest["segments"][0]["visual_class"] = "minimax_h3_hand_drawn_animation"
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(animation_gate(episode, plan)["status"], "passed")

    @patch("delivery_contract.sampled_frame_hashes", return_value=["same", "same"])
    def test_static_fallback_cannot_pass_as_animation(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary), ["generative_animation"]
            )
            (episode / "controlled_visual_manifest.json").write_text(
                json.dumps({"strategy": "reviewed_keyframe_stable_hold", "motion": "none"})
            )
            gate = animation_gate(episode, plan)
            self.assertEqual(gate["status"], "failed")
            self.assertIn("legacy_static_fallback_manifest_present", gate["violations"])
            self.assertIn("no_animated_visual_segments", gate["violations"])

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_deterministic_only_episode_cannot_replace_generative_video(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary), ["deterministic_hand_drawn_animation"]
            )
            gate = animation_gate(episode, plan)
            self.assertEqual(gate["status"], "failed")
            self.assertIn("no_generative_animation_segments", gate["violations"])
            self.assertIn("generative_animation_not_primary_by_duration", gate["violations"])

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_generative_video_must_cover_at_least_half_of_timeline(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary),
                [
                    "generative_animation",
                    "deterministic_hand_drawn_animation",
                    "deterministic_hand_drawn_animation",
                ],
            )
            gate = animation_gate(episode, plan)
            self.assertEqual(gate["status"], "failed")
            self.assertIn("generative_animation_not_primary_by_duration", gate["violations"])

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_deterministic_animation_must_be_declared_supporting(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary),
                ["generative_animation", "deterministic_hand_drawn_animation"],
            )
            manifest_path = episode / "visual_delivery_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["segments"][1].pop("supporting_explainer_only")
            manifest_path.write_text(json.dumps(manifest))
            gate = animation_gate(episode, plan)
            self.assertEqual(gate["status"], "failed")
            self.assertIn(
                "deterministic_animation_not_declared_supporting:B02", gate["violations"]
            )

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_manifest_backend_must_match_plan(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary), ["generative_animation"]
            )
            manifest_path = episode / "visual_delivery_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["primary_video_backend"] = "different_backend"
            manifest_path.write_text(json.dumps(manifest))
            gate = animation_gate(episode, plan)
            self.assertEqual(gate["status"], "failed")
            self.assertIn("visual_manifest_primary_backend_mismatch", gate["violations"])

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_v4_manifest_records_backend_per_generated_segment(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary), ["generative_animation"]
            )
            manifest_path = episode / "visual_delivery_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["segments"][0].pop("backend_id")
            manifest_path.write_text(json.dumps(manifest))
            gate = animation_gate(episode, plan)
            self.assertEqual(gate["status"], "failed")
            self.assertIn("generative_backend_not_recorded:B01", gate["violations"])

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_author_selected_visual_format_is_not_hardcoded(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary), ["generative_animation"]
            )
            plan["delivery"]["visual_requirement"] = "photographic_explainer_video"
            plan["delivery"]["visual_style"] = "warm_clinical_documentary"
            plan["delivery"]["animation_mode"] = "cinematic_patient_explainer"
            manifest_path = episode / "visual_delivery_manifest.json"
            manifest = json.loads(manifest_path.read_text())
            manifest["visual_style"] = "warm_clinical_documentary"
            manifest["animation_mode"] = "cinematic_patient_explainer"
            manifest_path.write_text(json.dumps(manifest))
            self.assertEqual(animation_gate(episode, plan)["status"], "passed")

    def test_release_requires_animation_delivery_status(self) -> None:
        old_report = {
            "status": "technical_qa_passed_visual_and_medical_review_required",
            "delivery_class": "final_animation",
            "animation_gate": {"status": "passed"},
        }
        self.assertFalse(release_eligible(old_report))
        old_report["status"] = "delivery_qa_passed_visual_and_medical_review_required"
        self.assertTrue(release_eligible(old_report))

    @patch("delivery_contract.sampled_frame_hashes", return_value=["a", "b"])
    def test_missing_manifest_reports_failure_without_crashing(self, _hashes) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            episode, plan = self.make_episode(
                Path(temporary), ["generative_animation"]
            )
            (episode / "visual_delivery_manifest.json").unlink()
            gate = animation_gate(episode, plan)
            self.assertEqual(gate["status"], "failed")
            self.assertIn("missing_visual_delivery_manifest", gate["violations"])


if __name__ == "__main__":
    unittest.main()
