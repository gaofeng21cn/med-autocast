"""Persistence, provenance, and non-destructive reuse of local animation elements."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/workbench/scripts"))
import animation_library as library


class LibraryTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.workspace = Path(temporary.name).resolve()
        self.root = self.workspace / "assets/paper-theatre"
        self.project = self.workspace / "productions/s/e"
        self.project.mkdir(parents=True)
        library.write(self.project / "project.json", {"series_id": "s", "episode_id": "e"})
        (self.project / "paper.png").write_bytes(b"transparent paper")
        (self.project / "source.md").write_text("Original source evidence")
        self.asset = {
            "asset_id": "paper", "path": "paper.png", "source_type": "imagegen",
            "prompt_ref": "source.md", "status": "approved_direct_use", "medical": True,
            "registration": {"anchors": {"fold": {"x": .2, "y": .3}}},
            "visual_review": {"status": "passed"}, "medical_review": {"status": "pending"},
        }
        library.write(self.project / "asset_manifest.json", {"assets": [self.asset]})

    def ingest(self):
        return library.ingest_project(self.workspace, self.root, self.project, notes={
            "paper": {"reuse_scope": {"kind": "general"}, "usage_notes": "Fold at registered anchor"},
        })

    def test_archive_survives_source_removal_and_preserves_evidence(self):
        result, debts = self.ingest()
        self.assertFalse(debts)
        package = (self.root / result[0]["record"]).parent
        record = library.read(package / "record.json")
        (self.project / "paper.png").unlink()
        (self.project / "source.md").unlink()
        self.assertEqual((package / record["entry"]).read_bytes(), b"transparent paper")
        self.assertEqual((package / record["asset"]["prompt_ref"]).read_text(), "Original source evidence")
        self.assertEqual(record["asset"]["registration"], self.asset["registration"])
        self.assertEqual(record["asset"]["medical_review"]["status"], "pending")

    def test_repeated_ingest_is_idempotent_and_new_bytes_create_revision(self):
        first, _ = self.ingest()
        second, _ = self.ingest()
        self.assertEqual(first, second)
        (self.project / "paper.png").write_bytes(b"new paper")
        third, _ = self.ingest()
        self.assertNotEqual(first[0]["revision"], third[0]["revision"])
        self.assertEqual(len(library.read(self.root / "catalog.json")["items"]), 2)
        original = (self.root / first[0]["record"]).parent / "files/payload.png"
        self.assertEqual(original.read_bytes(), b"transparent paper")

    def test_query_does_not_overwrite_complete_index(self):
        self.ingest()
        args = argparse.Namespace(workspace=self.workspace, refresh=True, query=None)
        library.run(args)
        original = (self.root / "index.json").read_bytes()
        args.refresh, args.query = False, "no matching element"
        self.assertEqual(library.run(args)["count"], 0)
        self.assertEqual((self.root / "index.json").read_bytes(), original)
        self.assertNotIn("autoplay", (self.root / "index.html").read_text())

    def test_missing_payload_does_not_discard_other_entries(self):
        manifest = library.read(self.project / "asset_manifest.json")
        manifest["assets"].append({"asset_id": "missing", "path": "missing.png"})
        library.write(self.project / "asset_manifest.json", manifest)
        result, debts = self.ingest()
        self.assertEqual(len(result), 1)
        self.assertEqual(debts[0]["asset_id"], "missing")

    def test_reuse_resets_review_and_refuses_changed_destination(self):
        result, _ = self.ingest()
        target = self.workspace / "productions/s/second"
        target.mkdir()
        library.write(target / "project.json", {"series_id": "s", "episode_id": "second"})
        library.write(target / "asset_manifest.json", {"assets": []})
        imported = library.reuse(self.workspace, self.root, target, result[0]["id"])
        self.assertEqual(imported["status"], "copied_and_verified")
        row = library.read(target / "asset_manifest.json")["assets"][0]
        self.assertEqual(row["status"], "pending_review")
        self.assertEqual(row["source_review"]["status"], "passed")
        self.assertEqual(row["medical_review"]["status"], "pending")
        self.assertTrue((target / row["prompt_ref"]).is_file())
        Path(imported["entry"]).write_bytes(b"local edit")
        with self.assertRaisesRegex(ValueError, "不覆盖"):
            library.reuse(self.workspace, self.root, target, result[0]["id"])
        self.assertEqual(Path(imported["entry"]).read_bytes(), b"local edit")
        self.assertEqual(len(library.read(self.root / "uses.json")["uses"]), 1)

    def test_author_identity_and_path_boundaries(self):
        asset = {**self.asset, "path": "../outside.png"}
        library.write(self.project / "asset_manifest.json", {"assets": [asset]})
        with self.assertRaisesRegex(ValueError, "越界"):
            self.ingest()
        archived = library.archive(self.root, {
            "id": "author_seal", "entry": "files/seal.png", "kind": "image",
            "reuse_scope": {"kind": "author", "id": "author_a"},
        }, [{"source": self.project / "paper.png", "path": "files/seal.png"}])
        with patch("workbench_config.load_author_profile", return_value=(None, {"profile_id": "author_b"})):
            result = library.reuse(self.workspace, self.root, self.project, archived["id"])
        self.assertEqual(result["status"], "not_imported")
        self.assertFalse((self.project / "assets/library").exists())

    def test_layered_bundle_imports_each_part_and_is_idempotent(self):
        cap = self.workspace / "cap.png"
        cap.write_bytes(b"independent cap")
        archived = library.archive(self.root, {
            "id": "bottle", "kind": "image", "entry": "files/body.png",
            "asset_bundle": [
                {"asset_id": "body", "path": "files/body.png", "medical": True},
                {"asset_id": "cap", "path": "files/cap.png", "registration": {"pivot": {"x": .5, "y": .9}}},
            ],
            "assembly": {"parts": ["body", "cap"]},
        }, [{"source": self.project / "paper.png", "path": "files/body.png"},
            {"source": cap, "path": "files/cap.png"}])
        result = library.reuse(self.workspace, self.root, self.project, archived["id"], asset_id="drug")
        rows = library.read(self.project / "asset_manifest.json")["assets"]
        parts = {row["asset_id"]: row for row in rows if row["asset_id"].startswith("drug__")}
        self.assertEqual(set(parts), {"drug__body", "drug__cap"})
        self.assertEqual((self.project / parts["drug__cap"]["path"]).read_bytes(), b"independent cap")
        self.assertEqual(parts["drug__cap"]["registration"]["pivot"], {"x": .5, "y": .9})
        self.assertEqual(parts["drug__body"]["medical_review"]["status"], "pending")
        self.assertEqual(len(result["imported_assets"]), 2)
        library.reuse(self.workspace, self.root, self.project, archived["id"], asset_id="drug")
        self.assertEqual(len(library.read(self.project / "asset_manifest.json")["assets"]), len(rows))
        self.assertEqual(len(library.read(self.root / "uses.json")["uses"]), 1)

    def test_incomplete_bundle_preserves_manifest_and_existing_files(self):
        archived = library.archive(self.root, {
            "id": "incomplete", "kind": "image", "entry": "files/body.png",
            "asset_bundle": [{"asset_id": "body", "path": "files/body.png"},
                             {"asset_id": "cap", "path": "files/missing.png"}],
        }, [{"source": self.project / "paper.png", "path": "files/body.png"}])
        before = (self.project / "asset_manifest.json").read_bytes()
        with self.assertRaisesRegex(ValueError, "独立文件"):
            library.reuse(self.workspace, self.root, self.project, archived["id"])
        self.assertEqual((self.project / "asset_manifest.json").read_bytes(), before)
        self.assertFalse((self.project / "assets/library").exists())

    def test_withdrawn_exact_revision_is_not_reused(self):
        result, _ = self.ingest()
        identifier = f"paper:{result[0]['id']}@{result[0]['revision']}"
        library.write(self.root / "curation.json", {"assets": {identifier: {"status": "needs_rebuild", "reason": "baked halo"}}})
        before = (self.project / "asset_manifest.json").read_bytes()
        reused = library.reuse(self.workspace, self.root, self.project, result[0]["id"], result[0]["revision"])
        self.assertEqual(reused["status"], "not_imported")
        self.assertEqual(reused["quality_debt"], ["baked halo"])
        self.assertEqual((self.project / "asset_manifest.json").read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
