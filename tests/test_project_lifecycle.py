#!/usr/bin/env python3
"""Regression tests for lifecycle archive uniqueness, empty-batch safety, pinning, and rollback verification."""
from __future__ import annotations

import json
import subprocess
import sys
import tarfile
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/workbench/scripts"))

import delivery_layout  # noqa: E402
import project_lifecycle as pl  # noqa: E402


class ProjectLifecycleRegressionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.ws = (Path(self.tmp.name) / "ws").resolve()
        (self.ws / "archive").mkdir(parents=True, exist_ok=True)
        (self.ws / "productions").mkdir(parents=True, exist_ok=True)
        (self.ws / "deliveries").mkdir(parents=True, exist_ok=True)
        (self.ws / "publish").mkdir(parents=True, exist_ok=True)
        (self.ws / "workbench.yaml").write_text(
            "delivery_policy:\n  archive_keep_latest: 1\nseries:\n  s:\n    publish_root: publish/s\n    episodes:\n      e:\n        project: productions/s/e/v2\n",
            encoding="utf-8",
        )
        v2 = self.ws / "productions/s/e/v2"
        v2.mkdir(parents=True, exist_ok=True)
        (v2 / "project.json").write_text('{"id":"v2"}\n', encoding="utf-8")

    def _add_retired_rev(self, name: str, marker_text: str) -> Path:
        rev = self.ws / "productions/s/e" / name
        (rev / "src").mkdir(parents=True, exist_ok=True)
        (rev / "project.json").write_text(json.dumps({"id": name}) + "\n", encoding="utf-8")
        (rev / "src/shots.ts").write_text(f"// {marker_text}\n", encoding="utf-8")
        return rev

    def _make_delivery_snapshot(
        self,
        series: str,
        episode: str,
        snap_id: str,
        video_bytes: bytes,
        *,
        medical: str = "pending",
        pin: bool = False,
    ) -> Path:
        snap = self.ws / "archive/deliveries" / series / episode / snap_id
        pub = snap / "publish"
        rec = snap / "record"
        pub.mkdir(parents=True, exist_ok=True)
        rec.mkdir(parents=True, exist_ok=True)
        (pub / "video.mp4").write_bytes(video_bytes)
        (pub / "封面.jpg").write_bytes(b"jpg-data")
        (pub / "subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\n测试\n", encoding="utf-8")
        (pub / "小红书文案.txt").write_text("小红书测试", encoding="utf-8")
        (pub / "微信视频号文案.txt").write_text("视频号测试", encoding="utf-8")
        (pub / "发布交付包.md").write_text("# 交付说明", encoding="utf-8")
        sha = pl.sha256_file(pub / "video.mp4")
        manifest = {
            "schema": "medical_video_delivery_manifest/v1",
            "series_id": series,
            "episode_id": episode,
            "sha256": sha,
            "reviews": {"medical": medical},
        }
        (rec / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        if pin:
            pl.pin_delivery_snapshot(self.ws, snap, reason="published_release", release_tag="r1")
        return snap

    def test_retire_revisions_unique_same_day_and_noop_safe(self) -> None:
        self._add_retired_rev("v1", "first-run")
        r1 = pl.retire_revisions(self.ws, apply=True)
        self.assertEqual(r1["status"], "retired")
        arch1 = Path(r1["lineage_archive"])
        self.assertTrue(arch1.is_file())
        with tarfile.open(arch1, "r:gz") as tf1:
            names1 = tf1.getnames()
        self.assertIn("productions/s/e/v1/project.json", names1)

        before_bytes = arch1.read_bytes()
        r_empty = pl.retire_revisions(self.ws, apply=True)
        self.assertEqual(r_empty["status"], "noop_no_candidates")
        self.assertIsNone(r_empty["lineage_archive"])
        self.assertEqual(arch1.read_bytes(), before_bytes)

        self._add_retired_rev("v0", "second-run")
        r2 = pl.retire_revisions(self.ws, apply=True)
        self.assertEqual(r2["status"], "retired")
        arch2 = Path(r2["lineage_archive"])
        self.assertTrue(arch2.is_file())
        self.assertNotEqual(arch1, arch2)
        self.assertEqual(arch1.read_bytes(), before_bytes)
        with tarfile.open(arch2, "r:gz") as tf2:
            self.assertIn("productions/s/e/v0/project.json", tf2.getnames())

        self._add_retired_rev("v0b", "explicit-collision")
        with self.assertRaises(FileExistsError):
            pl.retire_revisions(self.ws, archive_path=arch2, apply=True)

    def test_prune_archived_deliveries_preserves_pinned_and_medical_approved(self) -> None:
        s1_pinned = self._make_delivery_snapshot("s", "e", "20261120T010000Z", b"v1", pin=True)
        s2_medical = self._make_delivery_snapshot("s", "e", "20261121T010000Z", b"v2", medical="approved")
        s3_draft_old = self._make_delivery_snapshot("s", "e", "20261122T010000Z", b"v3")
        s4_draft_new = self._make_delivery_snapshot("s", "e", "20261123T010000Z", b"v4")

        res = pl.prune_archived_deliveries(self.ws, keep_latest=1, apply=True)
        self.assertEqual(res["status"], "pruned")
        self.assertEqual(res["snapshots_removed"], 1)
        self.assertEqual(res["pinned_preserved_count"], 2)
        self.assertTrue(s1_pinned.is_dir())
        self.assertTrue(s2_medical.is_dir())
        self.assertFalse(s3_draft_old.exists())
        self.assertTrue(s4_draft_new.is_dir())

        s5_draft_newer = self._make_delivery_snapshot("s", "e", "20261124T010000Z", b"v5")
        removed = delivery_layout._prune_old_archived_deliveries(s1_pinned.parent, 1)
        self.assertEqual([Path(p).name for p in removed], ["20261123T010000Z"])
        self.assertTrue(s1_pinned.is_dir())
        self.assertTrue(s2_medical.is_dir())
        self.assertTrue(s5_draft_newer.is_dir())

    def test_verify_delivery_rollback_restores_and_checks_sha(self) -> None:
        snap = self._make_delivery_snapshot("s", "e", "20261125T010000Z", b"valid-mp4-bytes")
        restore_dir = self.ws / "restore-tmp"
        v = pl.verify_delivery_rollback(self.ws, snap, restore_to=restore_dir)
        self.assertEqual(v["status"], "verified", v)
        self.assertEqual(v["errors"], [])
        self.assertEqual((restore_dir / "publish/video.mp4").read_bytes(), b"valid-mp4-bytes")

        snap2 = self._make_delivery_snapshot("s", "e2", "20261125T020000Z", b"mp4-2")
        (snap2 / "publish/小红书文案.txt").unlink()
        (snap2 / "publish/微信视频号文案.txt").unlink()
        mf2_path = snap2 / "record/manifest.json"
        mf2 = json.loads(mf2_path.read_text(encoding="utf-8"))
        mf2["quality_debt"] = [{"code": "release_copy_pending"}]
        mf2_path.write_text(json.dumps(mf2) + "\n", encoding="utf-8")
        v2 = pl.verify_delivery_rollback(self.ws, snap2)
        self.assertEqual(v2["status"], "verified", v2)

    def test_verify_rollback_cli_refuses_unverified_video(self) -> None:
        snap = self._make_delivery_snapshot("s", "e", "20261125T010000Z", b"archived-video")
        manifest_path = snap / "record/manifest.json"
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        restore = self.ws / "restore"
        command = [
            sys.executable, str(ROOT / "runtime/workbench/scripts/project_lifecycle.py"),
            "verify-rollback", "--workspace", str(self.ws), "--snapshot", str(snap),
            "--restore-to", str(restore),
        ]
        for digest, error in (
            (None, "missing a valid video SHA-256"),
            ("invalid-sha", "missing a valid video SHA-256"),
            ("0" * 64, "SHA mismatch"),
        ):
            with self.subTest(digest=digest):
                body = {key: value for key, value in manifest.items() if key != "sha256"}
                if digest is not None:
                    body["sha256"] = digest
                manifest_path.write_text(json.dumps(body), encoding="utf-8")
                result = subprocess.run(command, capture_output=True, text=True)
                self.assertEqual(result.returncode, 1, result.stderr)
                receipt = json.loads(result.stdout)
                self.assertEqual(receipt["status"], "failed")
                self.assertIn(error, " ".join(receipt["errors"]))
                self.assertFalse(restore.exists())

        manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
        result = subprocess.run(command, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["status"], "verified")
        self.assertEqual((restore / "publish/video.mp4").read_bytes(), b"archived-video")


if __name__ == "__main__":
    unittest.main()
