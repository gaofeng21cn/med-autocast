import hashlib
import io
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

import sys
sys.path.insert(0, str(Path(__file__).parent))
from audit_audio_delivery_binding import inspect_episode, main


def write_wav(path: Path, seconds: float = 0.2) -> None:
    frames = b"\0\0" * round(24000 * seconds)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(24000)
        handle.writeframes(frames)


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class DeliveryBindingTests(unittest.TestCase):
    def make_episode(self, root: Path):
        project = root / "productions/s/e/v1"
        audio = project / "audio"
        write_wav(audio / "take.wav")
        write_wav(audio / "narration.wav", 0.6)
        write_wav(audio / "narration-normalized.wav", 0.6)
        (project / "score.json").write_text("{}")
        (project / "audio.wav").write_bytes(b"audio")
        (project / "dist").mkdir(parents=True)
        (project / "dist/film.js").write_bytes(b"bundle")
        movie = project / "out/movie.mp4"
        movie.parent.mkdir(parents=True)
        movie.write_bytes(b"movie")
        voice = audio / "narration-normalized.wav"
        score = project / "score.json"
        mixed = project / "audio.wav"
        bundle = project / "dist/film.js"
        current = movie
        (project / "project.json").write_text(json.dumps({"score": "score.json", "voice": "audio/narration-normalized.wav", "audio": "audio.wav"}))
        (audio / "narration_beats.json").write_text(json.dumps({
            "splice": {"schema": "narration_splice/v2", "policy": "resample_correctly_preserve_all_source_samples",
                        "raw_sha256": digest(audio / "narration.wav"), "normalized_sha256": digest(voice)},
            "beats": [{"id": "B01", "audio": str(audio / "take.wav"), "source_sha256": digest(audio / "take.wav"), "start": 0.0, "end": 0.2}],
        }))
        (project / "audio/timing-receipt.json").write_text(json.dumps({"voice_sha256": digest(voice), "score_sha256": digest(score)}))
        (project / "audio/mix-receipt.json").write_text(json.dumps({"voice_sha256": digest(voice), "score_sha256": digest(score), "audio_sha256": digest(mixed)}))
        (project / "out/current.json").write_text(json.dumps({"status": "rendered", "path": str(current), "sha256": digest(current), "audio_sha256": digest(mixed), "score_sha256": digest(score), "bundle_sha256": digest(bundle)}))
        workbench = root / "workbench.yaml"
        workbench.write_text("directories: {}\nseries:\n  s:\n    publish_root: publish/s\n    delivery:\n      episode_dirs:\n        e: episode\n    episodes:\n      e:\n        project: productions/s/e/v1\n")
        publish = root / "publish/s/episode"
        publish.mkdir(parents=True)
        publish.joinpath("video.mp4").write_bytes(movie.read_bytes())
        return project

    @patch("audit_audio_delivery_binding.locations")
    def test_fresh_delivery_is_bound(self, locations,):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_episode(root)
            locations.return_value = {"user": root / "publish/s/episode"}
            row = inspect_episode(root, "s", "e", {"project": "productions/s/e/v1"})
            self.assertTrue(row["source"]["bound"])
            self.assertTrue(row["bindings"]["timing_bound"])
            self.assertTrue(row["bindings"]["mix_bound"])
            self.assertTrue(row["bindings"]["render_bound"])
            self.assertTrue(row["bindings"]["publish_bound"])
            self.assertFalse(row["stale_publish"])
            self.assertEqual(row["status"], "publish_fresh")

    @patch("audit_audio_delivery_binding.locations")
    def test_old_publish_is_attention_only(self, locations):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            self.make_episode(root)
            locations.return_value = {"user": root / "publish/s/episode"}
            (root / "publish/s/episode/video.mp4").write_bytes(b"old")
            row = inspect_episode(root, "s", "e", {"project": "productions/s/e/v1"})
            self.assertTrue(row["stale_publish"])
            self.assertIn("published_mp4_sha_mismatch", row["stale_publish_reasons"])
            self.assertEqual(row["status"], "attention_required")

    @patch("audit_audio_delivery_binding.locations")
    def test_invalid_beat_times_are_diagnostics(self, locations):
        cases = [
            ({"end": 0.2}, "missing_beat_start"),
            ({"start": 0.0}, "missing_beat_end"),
            ({"start": "not-a-number", "end": 0.2}, "invalid_beat_start"),
            ({"start": 0.0, "end": []}, "invalid_beat_end"),
            ({"start": "NaN", "end": 0.2}, "invalid_beat_start"),
            ({"start": 0.0, "end": "Infinity"}, "invalid_beat_end"),
            ({"start": True, "end": 0.2}, "invalid_beat_start"),
            ({"start": -1, "end": 0.2}, "invalid_beat_start"),
            ({"start": 0.2, "end": 0.1}, "nonpositive_beat_duration"),
        ]
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.make_episode(root)
            locations.return_value = {"user": root / "publish/s/episode"}
            narration_path = project / "audio/narration_beats.json"
            narration = json.loads(narration_path.read_text())
            original_beat = narration["beats"][0]
            for timing, expected_flag in cases:
                with self.subTest(timing=timing):
                    beat = {key: value for key, value in original_beat.items() if key not in ("start", "end")}
                    beat.update(timing)
                    narration["beats"] = [beat, original_beat]
                    narration_path.write_text(json.dumps(narration))
                    result = inspect_episode(root, "s", "e", {"project": "productions/s/e/v1"})
                    self.assertIn(expected_flag, result["source"]["beats"][0]["flags"])
                    self.assertIsNone(result["source"]["beats"][0]["declared_duration"])
                    self.assertEqual(result["source"]["beats"][1]["flags"], [])
                    self.assertFalse(result["source"]["bound"])
                    self.assertEqual(result["status"], "attention_required")

    @patch("audit_audio_delivery_binding.locations")
    def test_missing_or_malformed_beats_cannot_appear_bound(self, locations):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.make_episode(root)
            locations.return_value = {"user": root / "publish/s/episode"}
            narration_path = project / "audio/narration_beats.json"
            narration = json.loads(narration_path.read_text())
            for beats in (None, [], "not-a-list", {}):
                with self.subTest(beats=beats):
                    narration["beats"] = beats
                    narration_path.write_text(json.dumps(narration))
                    result = inspect_episode(root, "s", "e", {"project": "productions/s/e/v1"})
                    self.assertFalse(result["source"]["bound"])
                    self.assertIn("missing_or_invalid_beats", result["issues"])

    @patch("audit_audio_delivery_binding.locations")
    def test_invalid_metadata_does_not_stop_batch(self, locations):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            project = self.make_episode(root)
            locations.return_value = {"user": root / "publish/s/episode"}
            narration_path = project / "audio/narration_beats.json"
            narration = json.loads(narration_path.read_text())
            narration["beats"] = [None, {"id": "B02", "start": "bad", "end": 1}]
            narration_path.write_text(json.dumps(narration))
            with root.joinpath("workbench.yaml").open("a") as handle:
                handle.write("      second:\n        project: productions/s/e/v1\n")
            output = root / "audit.json"
            argv = ["audit_audio_delivery_binding.py", "--workspace", str(root), "--output", str(output)]
            with patch.object(sys, "argv", argv), patch("sys.stdout", new_callable=io.StringIO):
                main()
            result = json.loads(output.read_text())
            self.assertEqual(result["episodes_checked"], 2)
            self.assertEqual(result["attention_required"], 2)
            self.assertEqual(result["detail"][1]["episode"], "second")
            self.assertIn("invalid_beat_metadata", result["detail"][0]["source"]["beats"][0]["flags"])
            self.assertIn("generated_at", result)
            self.assertEqual(result["method"], "receipt_sha256_binding_read_only_v1")


if __name__ == "__main__":
    unittest.main()
