"""Behavior regressions for local project edits and safe narration retries."""

import argparse
import hashlib
import io
import json
from contextlib import redirect_stdout
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from types import SimpleNamespace
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

    def test_preview_cli_keeps_locator_counts_and_reference_without_replaying_every_frame(self):
        full = {'status': 'previewed', 'preview_receipt': '/review/preview.json',
                'quality_debt': [{'kind': 'text_subject_intersection', 'element': 'label',
                                 'rect': {'x': i, 'y': 20, 'w': 100, 'h': 30},
                                 'blocks_stage_progress': False,
                                 'semantic_review_required': True} for i in range(500)]}
        output = io.StringIO()
        with patch.object(pp, 'preview', return_value=full), patch.object(sys, 'argv', [
                'paper_project', '--workspace', str(self.root), '--project', str(self.root), 'preview']), redirect_stdout(output):
            pp.main()
        compact = json.loads(output.getvalue())
        self.assertEqual(compact['quality_debt_count'], 500)
        self.assertEqual(len(compact['quality_debt']), 1)
        self.assertEqual(compact['quality_debt'][0]['count'], 500)
        self.assertEqual(compact['quality_debt'][0]['evidence_ref'], '/review/preview.json')
        self.assertTrue(compact['quality_debt'][0]['semantic_review_required'])
        self.assertEqual(len(full['quality_debt']), 500)
        self.assertLess(len(output.getvalue()), 1000)

    def test_missing_asset_evidence_preserves_manifest_and_existing_unregistered_file(self):
        source = self.root / 'new.png'
        source.write_bytes(b'new candidate')
        dest = self.root / 'assets/imported/cuff.png'
        dest.parent.mkdir(parents=True)
        dest.write_bytes(b'prior recoverable candidate')
        manifest = self.root / 'asset_manifest.json'
        pp.save(manifest, {'assets': [], 'shots': []})
        manifest_before = manifest.read_bytes()
        meta = self.root / 'preproduction/meta.json'
        pp.save(meta, {'prompt_ref': 'missing-receipt.json'})
        args = SimpleNamespace(asset=source, asset_id='cuff', source='test',
            usage='fitted cuff', kind='imagegen', limits='candidate', metadata=meta,
            registration=None)
        with patch.object(pp, 'get_project', return_value=(self.root, {'assets': 'asset_manifest.json'})):
            with self.assertRaisesRegex(ValueError, 'prompt_ref.*尚未导入'):
                pp.assets(args)
        self.assertEqual(dest.read_bytes(), b'prior recoverable candidate')
        self.assertEqual(manifest.read_bytes(), manifest_before)
        self.assertFalse((self.root / 'assets/evidence').exists())

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

    def test_mix_snapshot_survives_failed_remix_and_marks_stale_score(self):
        p = self.root
        config = {"audio": "audio.wav", "score": "score.json", "voice": "voice.wav"}
        pp.save(p / "project.json", config)
        pp.save(p / "score.json", {"shots": []})
        (p / "voice.wav").write_bytes(b"voice")
        (p / "audio.wav").write_bytes(b"accepted original mix")
        pp.save(p / "audio/mix-receipt.json", {
            "audio_sha256": pp.sha(p / "audio.wav"),
            "score_sha256": "older-score-not-present",
            "voice_sha256": pp.sha(p / "voice.wav"),
        })
        history = Path(pp.preserve_mix(p, config))
        (p / "audio.wav").write_bytes(b"failed partial overwrite")
        snapshot = pp.read(history / "snapshot.json")
        self.assertEqual((history / "audio.wav").read_bytes(), b"accepted original mix")
        self.assertFalse(snapshot["receipt_matches_current_inputs"]["score_sha256"])
        self.assertTrue(snapshot["receipt_matches_current_inputs"]["audio_sha256"])
        self.assertEqual(pp.read(history / "mix-receipt.json")["score_sha256"], "older-score-not-present")

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

    def test_package_source_documents_resolve_after_install_and_internal_export(self):
        import yaml

        project = self.root / "productions/s/e"
        for folder in ("audio", "dist", "out", "src", "scripts"):
            (project / folder).mkdir(parents=True)
        (project / "out/review.mp4").write_bytes(b"encoded video")
        (project / "dist/film.js").write_text("bundle")
        (project / "audio/narration-normalized.wav").write_bytes(b"voice")
        (project / "audio.wav").write_bytes(b"mixed audio")
        pp.save(project / "project.json", {
            "schema": "paper_project/v1", "series_id": "s", "episode_id": "e", "title": "本集",
            "score": "score.json", "narration": "narration.json",
            "voice": "audio/narration-normalized.wav", "audio": "audio.wav", "entry": "index.html",
        })
        pp.save(project / "score.json", {"duration": 10, "shots": [], "cues": []})
        pp.save(project / "narration.json", {"beats": [{"id": "b1", "text": "本集旁白"}]})
        pp.save(project / "dist/build-receipt.json", {
            "inputs": {}, "bundle_sha256": pp.sha(project / "dist/film.js"),
        })
        pp.save(project / "audio/mix-receipt.json", {
            "voice_sha256": pp.sha(project / "audio/narration-normalized.wav"),
        })
        pp.save(project / "out/current.json", {
            "status": "rendered", "path": str(project / "out/review.mp4"),
            "sha256": pp.sha(project / "out/review.mp4"),
            "bundle_sha256": pp.sha(project / "dist/film.js"),
            "score_sha256": pp.sha(project / "score.json"),
            "audio_sha256": pp.sha(project / "audio.wav"),
        })
        (self.root / "workbench.yaml").write_text(yaml.safe_dump({
            "series": {"s": {"title": "系列", "publish_root": "publish/s", "episodes": {"e": {}}}},
        }))

        for internal in (False, True):
            with self.subTest(internal_export=internal):
                target = self.root / "work/export" if internal else None
                args = argparse.Namespace(project=project, workspace=self.root, output=target, review=None)
                with patch.object(pp.subprocess, "run", side_effect=OSError("cover unavailable")):
                    result = pp.package(args)
                manifest_path = target / "manifest.json" if internal else Path(result["manifest"])
                manifest = pp.read(manifest_path)
                expected_record = target if internal else self.root / "deliveries/s/e"
                for key, name in (("score", "score.json"), ("narration_script", "narration.json")):
                    reference = Path(manifest["artifacts"][key])
                    self.assertEqual(reference, expected_record / name)
                    self.assertTrue(reference.is_file())
                    self.assertEqual(reference.read_bytes(), (project / name).read_bytes())
                self.assertEqual(manifest["artifacts"]["video"], "video.mp4")
                self.assertEqual(manifest["artifacts"]["subtitles"], "subtitles.srt")
                self.assertFalse(list((self.root / "tmp").glob("delivery-*")))

    def frozen_mix_pair(self, name="reuse", *, registered_sound=False, captured=True):
        source, target = self.root / name / "before", self.root / name / "after"
        config = {
            "schema": "paper_project/v1", "series_id": "s", "episode_id": "e",
            "score": "score.json", "voice": "audio/voice.wav", "audio": "audio.wav",
            "assets": "asset_manifest.json", "entry": "index.html",
        }
        cue = {"shot": "s1", "event": "touch", "kind": "paper", "gain": 0.3}
        if registered_sound:
            cue["asset_id"] = "paper-sound"
        score = {
            "duration": 10, "fps": 24, "sounds": [cue],
            "shots": [{"id": "s1", "start": 0, "end": 10,
                       "events": {"touch": 3, "visual_only": 5}, "shot_recipe": "原动作说明"}],
        }
        for project in (source, target):
            (project / "audio").mkdir(parents=True)
            (project / "audio/voice.wav").write_bytes(b"frozen voice")
            (project / "audio/paper.wav").write_bytes(b"frozen foley")
            (project / "audio.wav").write_bytes(b"frozen mix" if project == source else b"prior target")
            (project / "index.html").write_text('<script src="film.js"></script>')
            pp.save(project / "project.json", config)
            pp.save(project / "score.json", score)
            pp.save(project / "asset_manifest.json", {"assets": [
                {"asset_id": "paper-sound", "path": "audio/paper.wav"},
                {"asset_id": "image", "path": "unused-image.png"},
            ]})
            pp.save(project / "audio/timing-receipt.json", {
                "voice_sha256": pp.sha(project / "audio/voice.wav"),
            })
        receipt = {
            "voice_sha256": pp.sha(source / config["voice"]),
            "score_sha256": pp.sha(source / config["score"]),
            "audio_sha256": pp.sha(source / config["audio"]),
            "full_listening": "passed", "tone_consistency": "passed",
        }
        if captured:
            receipt["audio_score_inputs"] = pp.audio_score_inputs(source, config)
        pp.save(source / "audio/mix-receipt.json", receipt)
        args = argparse.Namespace(project=target, workspace=self.root,
                                  reuse_from_project=source, music=None, music_plan=None)
        return source, target, config, args

    def test_visual_score_revision_reuses_audio_bytes_and_keeps_source(self):
        source, target, config, args = self.frozen_mix_pair(registered_sound=True)
        source_receipt = (source / "audio/mix-receipt.json").read_bytes()
        score = pp.read(target / "score.json")
        score["shots"][0]["shot_recipe"] = "修正人物坐姿，原声音事件不变"
        score["shots"][0]["camera"] = {"x": 20, "scale": 1.1}
        pp.save(target / "score.json", score)
        with patch.object(pp, "run") as runner:
            result = pp.mix(args)
        runner.assert_not_called()
        self.assertEqual(result["status"], "mixed_reused")
        self.assertEqual((target / "audio.wav").read_bytes(), b"frozen mix")
        self.assertEqual((source / "audio/mix-receipt.json").read_bytes(), source_receipt)
        receipt = pp.read(target / "audio/mix-receipt.json")
        self.assertEqual(receipt["score_sha256"], pp.sha(target / "score.json"))
        self.assertNotEqual(receipt["score_sha256"], receipt["reused_mix"]["source_score_sha256"])
        self.assertEqual(receipt["audio_sha256"], pp.sha(source / "audio.wav"))
        self.assertEqual(receipt["full_listening"], "pending")
        self.assertEqual(receipt["reused_mix"]["source_receipt_sha256"], pp.sha(source / "audio/mix-receipt.json"))
        self.assertIn('id="voice"', (target / "index.html").read_text())

    def test_unused_visual_events_and_silent_shots_do_not_require_remix(self):
        source, target, config, args = self.frozen_mix_pair("visual-events", registered_sound=True)
        score = pp.read(target / "score.json")
        del score["shots"][0]["events"]["visual_only"]
        score["shots"][0]["events"]["new_visual_landing"] = 6
        score["shots"].append({"id": "silent_insert", "start": 7, "events": {"reveal": 1}})
        pp.save(target / "score.json", score)
        with patch.object(pp, "run") as runner:
            self.assertEqual(pp.mix(args)["status"], "mixed_reused")
        runner.assert_not_called()
        self.assertEqual((target / "audio.wav").read_bytes(), (source / "audio.wav").read_bytes())
        receipt = pp.read(target / "audio/mix-receipt.json")
        self.assertIn("new_visual_landing", receipt["audio_score_inputs"]["shots"][0]["events"])

    def test_reuse_rejects_changed_audio_inputs_before_replacing_target(self):
        for change in ("duration", "event", "removed_event", "removed_shot", "shot_start", "cue", "voice", "foley", "timing"):
            with self.subTest(change=change):
                source, target, config, args = self.frozen_mix_pair(change, registered_sound=True)
                score = pp.read(target / "score.json")
                if change == "duration":
                    score["duration"] += 1
                elif change == "event":
                    score["shots"][0]["events"]["touch"] += 1
                elif change == "removed_event":
                    del score["shots"][0]["events"]["touch"]
                elif change == "removed_shot":
                    score["shots"] = []
                elif change == "shot_start":
                    score["shots"][0]["start"] += 1
                elif change == "cue":
                    score["sounds"][0]["gain"] += 0.1
                elif change == "voice":
                    (target / config["voice"]).write_bytes(b"changed voice")
                    pp.save(target / "audio/timing-receipt.json", {
                        "voice_sha256": pp.sha(target / config["voice"]),
                    })
                elif change == "foley":
                    (target / "audio/paper.wav").write_bytes(b"changed sound")
                elif change == "timing":
                    pp.save(target / "audio/timing-receipt.json", {"voice_sha256": "stale"})
                pp.save(target / "score.json", score)
                with self.assertRaises(ValueError), patch.object(pp, "run") as runner:
                    pp.mix(args)
                runner.assert_not_called()
                self.assertEqual((target / "audio.wav").read_bytes(), b"prior target")
                self.assertFalse((target / "audio/mix-receipt.json").exists())

    def test_reuse_checks_source_receipt_and_episode_identity(self):
        for change in ("score", "voice", "audio", "sound_snapshot", "episode", "same_project", "score_path"):
            with self.subTest(change=change):
                source, target, config, args = self.frozen_mix_pair("source-" + change, registered_sound=True)
                if change in ("score", "voice", "audio"):
                    (source / config[change]).write_bytes(b"changed source")
                elif change == "sound_snapshot":
                    for project in (source, target):
                        (project / "audio/paper.wav").write_bytes(b"same new bytes, absent from original mix")
                elif change == "episode":
                    source_config = pp.read(source / "project.json")
                    source_config["episode_id"] = "other"
                    pp.save(source / "project.json", source_config)
                elif change == "same_project":
                    args.reuse_from_project = target
                elif change == "score_path":
                    target_config = pp.read(target / "project.json")
                    target_config["score"] = "alternate-score.json"
                    pp.save(target / "alternate-score.json", pp.read(target / "score.json"))
                    pp.save(target / "project.json", target_config)
                with self.assertRaises(ValueError), patch.object(pp, "run") as runner:
                    pp.mix(args)
                runner.assert_not_called()
                self.assertEqual((target / "audio.wav").read_bytes(), b"prior target")

    def test_legacy_mix_reuse_requires_historical_registered_sound_bytes(self):
        source, target, config, args = self.frozen_mix_pair("legacy-procedural", captured=False)
        self.assertEqual(pp.mix(args)["status"], "mixed_reused")
        source, target, config, args = self.frozen_mix_pair("legacy-registered", registered_sound=True, captured=False)
        with self.assertRaisesRegex(ValueError, "未记录音效载荷字节"):
            pp.mix(args)
        self.assertEqual((target / "audio.wav").read_bytes(), b"prior target")

    def test_failed_force_keeps_successful_take_and_virtualenv_path(self):
        root = self.root
        runtime = root / "tts"
        model = root / "models"
        model.mkdir()
        (model / "config.json").write_text("config")
        reference = root / "reference.wav"
        reference.write_bytes(b"voice")
        python = runtime / ".venv/bin/python"
        python.parent.mkdir(parents=True)
        python.symlink_to(sys.executable)
        author = {"voice": {"reference_audio": str(reference)}}
        spec = {
            "definition": "voxcpm_2",
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

        def decoded_or_probed(cmd, **kwargs):
            if cmd[0] == "ffprobe":
                return json.dumps({"streams": [{"sample_rate": "24000"}]})
            return b"\x10\x10" * 24000

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
            patch.object(rn.subprocess, "check_output", side_effect=decoded_or_probed),
            patch.object(rn, "normalize", side_effect=normalization),
        ):
            with patch.object(rn.subprocess, "run", side_effect=successful):
                first = rn.synthesize(root, narration, output)
            take = output / "segments" / target[0]
            receipt = take.with_suffix(".json").read_bytes()
            import wave
            with wave.open(first["audio"], "rb") as wav:
                self.assertAlmostEqual(first["duration"], wav.getnframes()/wav.getframerate(), places=6)
                pcm = wav.readframes(wav.getnframes())
            self.assertEqual(first["beats"][0]["start"], .32)
            self.assertEqual(pcm[:round(24000*.32)*2], b"\0"*round(24000*.32)*2)
            self.assertNotEqual(pcm[round(24000*.32)*2:round(24000*.32)*2+2], b"\0\0")
            self.assertAlmostEqual(first["duration"], first["beats"][-1]["end"]+.7, places=6)
            self.assertEqual(first["full_listening"], "pending")
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
            # A pronunciation-only edit must invalidate the old take, while
            # preserving the public script and the previously successful audio.
            pp.save(narration, {"beats": [{"id": "B01", "text": "一句话", "tts_text": "<一|YI2>句话"}]})
            with patch.object(rn.subprocess, "run", side_effect=successful):
                corrected = rn.synthesize(root, narration, output, selected=["B01"])
            self.assertEqual(corrected["generated"], ["B01"])
            self.assertEqual(corrected["beats"][0]["text"], "一句话")
            self.assertEqual(corrected["beats"][0]["tts_text"], "<一|YI2>句话")
            self.assertNotEqual(corrected["beats"][0]["audio"], str(take))
            self.assertEqual(take.with_suffix(".json").read_bytes(), receipt)
            corrected_take = Path(corrected["beats"][0]["audio"])
            corrected_meta = pp.read(corrected_take.with_suffix(".json"))
            corrected_meta["pronunciation_review"] = {"status": "rejected", "notes": "wrong reading"}
            pp.save(corrected_take.with_suffix(".json"), corrected_meta)
            # Known bad audio cannot be reused even if its SHA and cache key match.
            with patch.object(rn.subprocess, "run", side_effect=successful):
                retried = rn.synthesize(root, narration, output, selected=["B01"])
            self.assertEqual(retried["generated"], ["B01"])
            self.assertEqual(pp.read(corrected_take.with_suffix(".json"))["pronunciation_review"]["status"], "pending")

    def test_pronunciation_control_is_part_of_narration_identity(self):
        p = self.root
        pp.save(p / "audio/narration_beats.json", {"beats": [{"id": "B01", "text": "还清楚"}]})
        pp.save(p / "narration.json", {"beats": [{"id": "B01", "text": "还清楚", "tts_text": "<还|HAI2>清楚"}]})
        with self.assertRaisesRegex(ValueError, "发音控制已变化"):
            pp.assert_narration(p, {"narration": "narration.json"})
        with self.assertRaisesRegex(ValueError, "与正文不同"):
            rn.tts_text({"id": "B01", "text": "还清楚", "tts_text": "<仍|HAI2>清楚"})

    def test_native_pronunciation_controls_and_malformed_input(self):
        self.assertEqual(rn.voxcpm_text("抽<血|XVE4>"), "抽{xue4}")
        self.assertEqual(rn.voxcpm_text("<重影|CHONG2 YING3>"), "{chong2}{ying3}")
        self.assertEqual(rn.voxcpm_text("<分泌|FEN1 MI4>、<钼靶|MU4 BA3>、<视网膜|SHI4 WANG3 MO2>"),
                         "{fen1}{mi4}、{mu4}{ba3}、{shi4}{wang3}{mo2}")
        self.assertEqual(rn.voxcpm_text("<hello|HH AH0 L OW1>"), "{HH AH0 L OW1}")
        self.assertEqual(rn.voxcpm_text("<5mg|WU3 HAO2 KE4>"), "{wu3}{hao2}{ke4}")
        self.assertEqual(rn.tts_text({"id": "B01", "text": "剂量5mg。", "tts_text": "剂量<5mg|WU3 HAO2 KE4>。"}),
                         "剂量<5mg|WU3 HAO2 KE4>。")
        for bad in ("<血|XYZ4>", "<还|>", "<还|HAI2", "<hello|BAD>"):
            with self.subTest(bad=bad), self.assertRaises(ValueError): rn.voxcpm_text(bad)
        with self.assertRaisesRegex(ValueError, "不支持"):
            rn.prepare_model_text("<还|HAI2>", "edge_tts")

    def test_retime_preserves_editorial_caption_breaks(self):
        p = self.root
        pp.save(p / "project.json", {"schema": "paper_project/v1", "series_id": "s", "episode_id": "e",
            "score": "score.json", "voice": "voice.wav", "beat_shots": {"B01": "s1"}})
        (p / "voice.wav").write_bytes(b"new-voice")
        pp.save(p / "score.json", {"duration": 10, "shots": [{"id": "s1", "start": 0, "end": 10, "events": {"contact": 2}}],
            "cues": [{"start": 1, "end": 4, "text": "第一句。"}, {"start": 4, "end": 9, "text": "第二句。"}]})
        pp.save(p / "audio/narration_beats.json", {"duration": 12, "beats": [{"id": "B01", "text": "第一句。第二句。", "start": 1, "end": 11}]})
        args = argparse.Namespace(project=p, workspace=p, reference_score=None)
        with patch.object(pp, "get_project", return_value=(p, pp.read(p / "project.json"))):
            pp.retime(args)
        score = pp.read(p / "score.json")
        self.assertEqual([q["text"] for q in score["cues"]], ["第一句。", "第二句。"])
        self.assertEqual(score["shots"][0]["events"], {"contact": 2.4})
        # Real production retries used the same padded voice interval repeatedly.
        # The second call used to move subtitles again despite unchanged media.
        pp.retime(args)
        self.assertEqual(pp.read(p / "score.json")["cues"], score["cues"])
        # A voice edit still requires remapping, so idempotence cannot hide edits.
        (p / "voice.wav").write_bytes(b"different-voice")
        pp.save(p / "audio/narration_beats.json", {"duration": 14, "beats": [
            {"id": "B01", "text": "第一句。第二句。", "start": 1, "end": 13}]})
        pp.retime(args)
        self.assertNotEqual(pp.read(p / "score.json")["cues"], score["cues"])

    def test_revision_edit_does_not_mutate_source(self):
        src = self.root / "v1"; src.mkdir()
        pp.save(src / "project.json", {"narration": "narration.json", "score": "score.json"})
        pp.save(src / "narration.json", {"beats": [{"id": "B01", "text": "原文"}]})
        pp.save(src / "score.json", {"cues": []})
        target = self.root / "v2"
        pp.revise(argparse.Namespace(workspace=self.root, project=target, from_project=src))
        (target / "narration.json").write_text("new")
        self.assertEqual(pp.read(src / "narration.json")["beats"][0]["text"], "原文")

    def test_reference_caption_timing_uses_voice_not_shot_padding(self):
        p = self.root
        config = {"score": "score.json", "voice": "voice.wav", "beat_shots": {"B01": "s1"}}
        (p / "voice.wav").write_bytes(b"voice")
        score = {"duration": 10, "shots": [{"id": "s1", "start": 0, "end": 10, "events": {}}],
            "cues": [{"start": .65, "end": 8.65, "text": "原文"}]}
        pp.save(p / "score.json", score)
        reference = p / "reference/score.json"
        pp.save(reference, score)
        pp.save(reference.parent / "narration_beats.json", {
            "beats": [{"id": "B01", "text": "原文", "start": .65, "end": 8.65}]})
        pp.save(p / "audio/narration_beats.json", {"duration": 12,
            "beats": [{"id": "B01", "text": "原文", "start": .65, "end": 10.65}]})
        with patch.object(pp, "get_project", return_value=(p, config)):
            pp.retime(argparse.Namespace(project=p, workspace=p, reference_score=reference))
        cue = pp.read(p / "score.json")["cues"][0]
        self.assertEqual(cue["start"], .65)
        self.assertEqual(cue["end"], 10.65)

    def test_partial_asr_does_not_drop_editorial_opening_caption(self):
        import align_narration
        from paper_captions import caption_rows_text, caption_text
        voice = self.root / "voice.wav"
        voice.write_bytes(b"voice")
        pp.save(self.root / "receipt.json", {"audio": str(voice), "beats": [{
            "id": "B01", "text": "第一句。后一条说明。", "audio": str(voice), "start": .65, "end": 10.65, "trimmed_head_seconds": .4}]})
        model = SimpleNamespace(transcribe=lambda *args, **kwargs: {
            "text": "后一条说明", "segments": [{"start": 4.2, "end": 9.8, "words": []}]})
        fake = SimpleNamespace(load_model=lambda *args, **kwargs: model)
        argv = ["align_narration", "--receipt", str(self.root / "receipt.json"),
            "--output", str(self.root / "alignment"), "--model", "local"]
        with patch.dict(sys.modules, {"whisper": fake}), patch.object(sys, "argv", argv):
            align_narration.main()
        segment = pp.read(self.root / "alignment/alignment.json")["beats"][0]["segments"][0]
        self.assertAlmostEqual(segment["start"], 4.2)
        proposal = pp.read(self.root / "alignment/cues.proposed.json")
        cues = proposal["cues"]
        self.assertEqual((cues[0]["start"], cues[-1]["end"]), (.65, 10.65))
        self.assertEqual(caption_rows_text("第一句。后一条说明。", cues), caption_text("第一句。后一条说明。"))
        self.assertEqual(len(cues), 2)
        self.assertEqual(proposal["timing_coordinates"], "timeline_global_seconds")

    def test_pronunciation_audit_checks_each_word_and_rejected_take(self):
        import yaml
        p = self.root / "productions/s/e/v1"
        pp.save(p / "project.json", {"narration": "input.json"})
        pp.save(p / "input.json", {"beats": [{"id": "B01", "text": "还看得到重影。",
            "tts_text": "<还|HAI2>看得到重影。"}]})
        take = p / "audio/segments/one.wav"
        take.parent.mkdir(parents=True)
        take.write_bytes(b"audio")
        pp.save(take.with_suffix(".json"), {"pronunciation_review": {"status": "rejected"}})
        pp.save(p / "audio/narration_beats.json", {"beats": [{"id": "B01", "audio": str(take)}]})
        (self.root / "workbench.yaml").write_text(yaml.safe_dump({
            "series": {"s": {"episodes": {"e": {"project": "productions/s/e/v1"}}}}}))
        script, _ = resolve_tool(self.root, "audit_pronunciation")
        self.assertIn("runtime/workbench", str(script))
        output = self.root / "audit.json"
        subprocess.run([sys.executable, str(script), "--workspace", str(self.root),
            "--series", "s", "--output", str(output)], check=True, capture_output=True)
        audit = pp.read(output)
        rows = {r["phrase"]: r for r in audit["targets"]}
        self.assertTrue(rows["还"]["tts_control_present"])
        self.assertFalse(rows["重影"]["tts_control_present"])
        self.assertEqual(len(audit["confirmed_errors"]), 2)
