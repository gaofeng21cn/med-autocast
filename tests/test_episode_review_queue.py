import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


SCRIPT = Path(__file__).resolve().parents[1] / "runtime/workbench/scripts/build_episode_review_queue.py"
SPEC = importlib.util.spec_from_file_location("build_episode_review_queue", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


class EpisodeReviewQueueTests(unittest.TestCase):
    def test_current_media_relative_path_is_resolved_from_episode_project(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            project = workspace / "productions/series/episode/v1"
            (project / "out").mkdir(parents=True)
            (project / "audio").mkdir()
            (project / "src").mkdir()
            (project / "score.json").write_text('{"shots": []}', encoding="utf-8")
            (project / "scene_directions.json").write_text("{}", encoding="utf-8")
            (project / "audio/narration_beats.json").write_text('{"beats": []}', encoding="utf-8")
            (project / "audio/narration-normalized.wav").write_bytes(b"placeholder")
            (project / "audio.wav").write_bytes(b"placeholder")
            current_media = project / "out/review.mp4"
            current_media.write_bytes(b"placeholder")
            (project / "out/current.json").write_text(
                json.dumps({"path": "out/review.mp4"}), encoding="utf-8"
            )
            (workspace / "workbench.yaml").write_text("", encoding="utf-8")

            row = MODULE.inspect_episode(workspace, "series", "episode", {"project": str(project.relative_to(workspace))})

        self.assertEqual(row["status"], "candidate_ready_needs_episode_review")
        self.assertEqual(row["evidence"]["current_media"], str(current_media))
        self.assertEqual(row["semantic_review"], "pending")
        self.assertFalse(row["release_eligible"])

    def test_missing_project_becomes_task_without_approval_or_exception(self):
        with tempfile.TemporaryDirectory() as temporary:
            row = MODULE.inspect_episode(Path(temporary), "series", "episode", {"project": "missing"})
        self.assertEqual(row["status"], "needs_input_repair")
        self.assertIn("project", row["missing_inputs"])
        self.assertFalse(row["release_eligible"])
        self.assertIn("逐镜反向读图", " ".join(row["next_tasks"]))


if __name__ == "__main__":
    unittest.main()
