"""Behavior regressions for local project edits and safe narration retries."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / "runtime/workbench/scripts"),
    str(ROOT / "runtime/native_helpers"),
]
import paper_project as pp
import render_narration as rn
from workbench_adapter import resolve_tool, tool_inventory


class ProjectTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()

    def test_renderer_and_inventory_share_canonical_entry_and_venv(self):
        (self.root / "scripts").mkdir()
        (self.root / "scripts/render_javascript_animation.py").write_text("old")
        venv = self.root / ".venv/bin/python"
        venv.parent.mkdir(parents=True)
        venv.symlink_to(sys.executable)
        script, python = resolve_tool(self.root, "render_javascript_animation")
        self.assertIn("runtime/workbench", str(script))
        self.assertEqual(python, venv)
        row = next(
            r
            for r in tool_inventory(self.root)["tools"]
            if r["name"] == "render_javascript_animation"
        )
        self.assertEqual(row["python"], str(venv))
        self.assertEqual(row["path"], str(script))

    def test_new_source_invalidates_build(self):
        p = self.root
        (p / "src").mkdir()
        (p / "dist").mkdir()
        (p / "scripts").mkdir()
        (p / "src/main.ts").write_text("old")
        (p / "dist/film.js").write_text("bundle")
        pp.save(
            p / "dist/build-receipt.json",
            {
                "inputs": {"src/main.ts": pp.sha(p / "src/main.ts")},
                "bundle_sha256": pp.sha(p / "dist/film.js"),
            },
        )
        pp.assert_built(p)
        (p / "src/new.ts").write_text("new")
        with self.assertRaisesRegex(ValueError, "文件列表"):
            pp.assert_built(p)

    def test_init_outside_workspace_does_not_create_directory(self):
        target = self.root.parent / (self.root.name + "-outside")
        a = argparse.Namespace(
            project=target, workspace=self.root, series="s", episode="e"
        )
        with self.assertRaisesRegex(ValueError, "工作区"):
            pp.initialize(a)
        self.assertFalse(target.exists())

    def test_init_uses_series_author_override(self):
        import yaml

        for name, text in [("default", "Default"), ("series", "Series Brand")]:
            (self.root / (name + ".yaml")).write_text(
                yaml.safe_dump({
                    "brand": {"overlay_text": text},
                    "visual_format": {
                        "style_id": "user_defined_ink_style",
                        "renderer": "svg",
                    } if name == "series" else {},
                })
            )
        (self.root / "workbench.yaml").write_text(
            yaml.safe_dump(
                {
                    "schema": "medical_video_workbench/v2",
                    "active_profiles": {"author": "default.yaml"},
                    "series": {"s": {"author_profile": "series.yaml"}},
                }
            )
        )
        a = argparse.Namespace(
            workspace=self.root,
            project=self.root / "productions/s/e",
            series="s",
            episode="e",
            title=None,
            from_project=None,
            narration=None,
        )
        pp.initialize(a)
        self.assertEqual(pp.read(a.project / "brand.json")["text"], "Series Brand")
        score_style = pp.read(a.project / "score.json")["style"]
        self.assertEqual(score_style["styleId"], "user_defined_ink_style")
        self.assertEqual(score_style["renderer"], "svg")
        self.assertNotIn("appliedStyleId", score_style)
        score_style["styleId"] = "changed_after_adoption"
        score = pp.read(a.project / "score.json")
        score["style"] = score_style
        pp.save(a.project / "score.json", score)
        self.assertEqual(
            pp.project_style_selection(a.project, pp.read(a.project / "project.json"))["style_id"],
            "changed_after_adoption",
        )
        a.project = self.root / "productions/s/one-off"
        a.episode = "one-off"
        a.style_id = "one_off_style"
        a.renderer = "one_off_renderer"
        a.style_profile_ref = "local/style-profile.json"
        pp.initialize(a)
        one_off_style = pp.read(a.project / "score.json")["style"]
        self.assertEqual(one_off_style["styleId"], "one_off_style")
        self.assertEqual(one_off_style["renderer"], "one_off_renderer")
        self.assertEqual(one_off_style["styleProfileRef"], "local/style-profile.json")
        self.assertNotIn("appliedStyleId", one_off_style)
        self.assertTrue((a.project / "tests/motion.test.ts").is_file())
        self.assertTrue((a.project / "compare.html").is_file())

    def test_preview_returns_diagnostic_without_claiming_a_preview(self):
        project = self.root / "productions/s/e"
        project.mkdir(parents=True)
        pp.save(project / "project.json", {
            "schema": "paper_project/v1", "series_id": "s", "episode_id": "e",
            "score": "score.json", "assets": "asset_manifest.json", "entry": "index.html",
        })
        pp.save(project / "score.json", {"duration": 10, "shots": []})

        def write_diagnostic(command, cwd, workspace):
            output = Path(command[command.index("--preview-output") + 1])
            output.mkdir(parents=True, exist_ok=True)
            pp.save(output / "preview.json", {
                "status": "not_rendered_with_quality_debt",
                "quality_debt": [{"code": "asset_admission_unresolved", "blocks_stage_progress": False}],
            })

        args = argparse.Namespace(
            project=project, workspace=self.root, shot=None, neighbors=False,
            start=None, end=None, output=None, clean=False, width=320, height=180,
        )
        with patch.object(pp, "assert_built"), patch.object(pp, "run", side_effect=write_diagnostic):
            result = pp.preview(args)
        self.assertEqual(result["status"], "not_rendered_with_quality_debt")
        self.assertEqual(result["quality_debt"][0]["code"], "asset_admission_unresolved")
        self.assertIsNotNone(result["preview_receipt"])

    def test_render_returns_failure_diagnostic_without_replacing_current_candidate(self):
        project = self.root / "productions/s/e"
        (project / "audio").mkdir(parents=True)
        (project / "dist").mkdir()
        (project / "out").mkdir()
        (project / "audio/narration-normalized.wav").write_bytes(b"voice")
        (project / "audio.wav").write_bytes(b"mix")
        (project / "dist/film.js").write_text("bundle")
        pp.save(project / "score.json", {
            "fps": 24, "duration": 1, "shots": [],
            "style": {"styleId": "paper_collage", "renderer": "canvas2d"},
        })
        pp.save(project / "project.json", {
            "schema": "paper_project/v1", "series_id": "s", "episode_id": "e",
            "score": "score.json", "voice": "audio/narration-normalized.wav",
            "audio": "audio.wav", "entry": "index.html",
        })
        pp.save(project / "audio/mix-receipt.json", {
            "voice_sha256": pp.sha(project / "audio/narration-normalized.wav"),
            "score_sha256": pp.sha(project / "score.json"),
            "audio_sha256": pp.sha(project / "audio.wav"),
        })
        pp.save(project / "out/current.json", {"path": "prior-review.mp4", "status": "rendered"})

        def write_diagnostic(command, cwd, workspace):
            output = Path(command[command.index("--output") + 1])
            pp.save(output.with_suffix(".receipt.json"), {
                "status": "not_rendered_with_quality_debt",
                "quality_debt": [{"code": "asset_admission_unresolved", "blocks_stage_progress": False}],
                "release_eligible": False,
            })

        args = argparse.Namespace(project=project, workspace=self.root, output=None)
        with (
            patch.object(pp, "assert_narration"),
            patch.object(pp, "assert_built"),
            patch.object(pp, "run", side_effect=write_diagnostic),
        ):
            result = pp.render(args)
        self.assertEqual(result["status"], "not_rendered_with_quality_debt")
        self.assertIsNone(result["path"])
        self.assertEqual(result["quality_debt"][0]["code"], "asset_admission_unresolved")
        self.assertEqual(pp.read(project / "out/current.json")["path"], "prior-review.mp4")

    def test_failed_force_keeps_successful_take_and_virtualenv_path(self):
        root = self.root
        runtime = root / "tts"
        model = root / "models"
        model.mkdir()
        (model / "config.yaml").write_text("config")
        reference = root / "reference.wav"
        reference.write_bytes(b"voice")
        python = runtime / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        author = {"voice": {"reference_audio": str(reference)}}
        spec = {
            "definition": "indextts_2_5",
            "root": str(runtime),
            "model_root": str(model),
            "python": str(python),
            "device": "cpu",
        }
        narration = root / "narration.json"
        pp.save(narration, {"beats": [{"id": "B01", "text": "一句话"}]})
        output = root / "audio"
        target = []

        def successful(cmd, **kwargs):
            if "--job" in cmd:
                self.assertEqual(cmd[0], str(python))
                job = json.loads(Path(cmd[-1]).read_text())
                f = Path(job["beats"][0]["output"])
                f.write_bytes(b"good-take")
                target.append(f.name)
            return subprocess.CompletedProcess(cmd, 0)

        def normalization(src, dst):
            dst.write_bytes(src.read_bytes())

        with (
            patch.object(
                rn, "load_author_profile", return_value=(root / "author.yaml", author)
            ),
            patch.object(
                rn,
                "load_backend_profile",
                return_value=(root / "backend.yaml", {"audio": {"voice": spec}}),
            ),
            patch.object(rn, "select_audio_backend", return_value="voice"),
            patch.object(rn.subprocess, "check_output", return_value=b"\0" * 48000),
            patch.object(rn, "normalize", side_effect=normalization),
        ):
            with patch.object(rn.subprocess, "run", side_effect=successful):
                first = rn.synthesize(root, narration, output)
            take = output / "segments" / target[0]
            receipt = take.with_suffix(".json").read_bytes()
            with patch.object(
                rn.subprocess, "run", side_effect=RuntimeError("worker failed")
            ):
                with self.assertRaisesRegex(RuntimeError, "worker failed"):
                    rn.synthesize(root, narration, output, force=True)
            self.assertEqual(take.read_bytes(), b"good-take")
            self.assertEqual(take.with_suffix(".json").read_bytes(), receipt)
            with patch.object(
                rn.subprocess, "run", side_effect=AssertionError("must reuse")
            ):
                again = rn.synthesize(root, narration, output)
            self.assertEqual(again["reused"], ["B01"])
            self.assertEqual(again["generated"], [])
