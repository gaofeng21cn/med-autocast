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
        self.root = Path(self.tmp.name)

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
