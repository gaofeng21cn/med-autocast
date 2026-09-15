import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
import unittest
import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from queue_h3_shots import apply_sampling, build_generation_prompt, main


class GenerationPromptTests(unittest.TestCase):
    def setUp(self) -> None:
        self.prompt_spec = {
            "common": "COMMON_VISUAL_RULES",
            "brand_common": "DR_MIE_IDENTITY_RULES",
        }

    def test_non_brand_shot_excludes_brand_identity_prompt(self) -> None:
        prompt = build_generation_prompt(
            self.prompt_spec,
            {"prompt": "Animate the medical diagram.", "brand_required": False},
            "",
        )

        self.assertIn("COMMON_VISUAL_RULES", prompt)
        self.assertNotIn("DR_MIE_IDENTITY_RULES", prompt)
        self.assertIn("first frame defines the complete cast", prompt)

    def test_brand_shot_appends_brand_identity_prompt(self) -> None:
        prompt = build_generation_prompt(
            self.prompt_spec,
            {"prompt": "Dr.咩 raises one hand.", "brand_required": True},
            "",
        )

        self.assertIn("COMMON_VISUAL_RULES", prompt)
        self.assertIn("DR_MIE_IDENTITY_RULES", prompt)
        self.assertNotIn("first frame defines the complete cast", prompt)

    def test_official_prompt_is_not_wrapped_with_legacy_camera_lock(self) -> None:
        prompt = "integrated_multimodal_description: [Shot 1] The camera pushes in.\n\noverall_soundscape: Quiet room.\n\nnon_diegetic_music: N/A"
        self.assertEqual(build_generation_prompt(self.prompt_spec, {"official_prompt": prompt}, "locked-camera"), prompt)

    def test_regular_sampling_disables_turbo_and_resolves_canvas(self) -> None:
        graph = {key: {"inputs": {}} for key in ["140:131", "140:139", "140:137"]}
        apply_sampling(graph, {"width": 1344, "height": 768, "turbo": False, "steps": 20})
        self.assertEqual(graph["140:131"]["inputs"], {"width": 1344, "height": 768})
        self.assertFalse(graph["140:139"]["inputs"]["value"])
        self.assertEqual(graph["140:137"]["inputs"]["value"], 20)

    def test_resolution_selector_one_megapixel_overflow_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "pixel area"):
            apply_sampling({}, {"width": 1376, "height": 768, "turbo": False, "steps": 20})

    def test_receipt_is_saved_before_wait_and_resume_does_not_submit_again(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            prompts, receipt = root / "shots.json", root / "receipt.json"
            snapshot = root / "queue.json"
            snapshot.write_text(json.dumps({"queue_running": [[0, "fixture", {key: {"inputs": {}} for key in ["92", "140:129", "140:133", "140:131"]}]]}))
            prompts.write_text(json.dumps({"common": "watercolor", "shots": [{
                "id": "T1", "prompt": "A hand moves.", "duration": 5, "seed": 42,
            }]}))
            argv = ["queue_h3_shots", "--base-queue", str(snapshot), "--prompts", str(prompts),
                    "--output-prefix", "test", "--receipt", str(receipt)]
            with patch("sys.argv", argv), patch("queue_h3_shots.wait_for_idle"), \
                 patch("queue_h3_shots.request_json", return_value={"prompt_id": "task-1"}) as request, \
                 patch("queue_h3_shots.wait_for_prompt", side_effect=TimeoutError):
                with self.assertRaises(TimeoutError):
                    main()
                self.assertEqual(json.loads(receipt.read_text())["shots"][0]["prompt_id"], "task-1")
                request.assert_called_once()
            with patch("sys.argv", argv), patch("queue_h3_shots.request_json") as request, \
                 patch("queue_h3_shots.wait_for_prompt", return_value={"outputs": {}}):
                main()
                request.assert_not_called()

    def test_reviewed_insert_is_rejected_before_contacting_backend(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            queue = root / "queue.json"
            prompts = root / "prompts.json"
            queue.write_text(json.dumps({"queue_running": [[0, "unused", {}]]}))
            prompts.write_text(json.dumps({
                "schema": "h3_semantic_shots/v2",
                "shots": [{"id": "R10", "status": "reviewed_insert_replaces_h3"}],
            }))
            argv = ["queue_h3_shots", "--base-queue", str(queue), "--prompts", str(prompts),
                    "--output-prefix", "unused", "--shot", "R10"]
            with patch("sys.argv", argv), patch("queue_h3_shots.wait_for_idle") as idle:
                with self.assertRaisesRegex(SystemExit, "R10"):
                    main()
                idle.assert_not_called()


if __name__ == "__main__":
    unittest.main()
