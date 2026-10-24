"""Preserve distinct nested payload paths during real companion import."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/workbench/scripts"))
import animation_library as library

SPEC = importlib.util.spec_from_file_location(
    "payload_mapping_companion", ROOT / "runtime/workbench/scripts/media_asset_library.py"
)
companion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(companion)


class PayloadMappingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()
        self.workspace = self.base / "workspace"
        self.external = self.base / "external"
        original = self.base / "original"
        original.mkdir()
        contents = {
            "index.html": b"<!doctype html><p>Component sample</p>",
            "USAGE.md": b"Use the full component in the current shot.\n",
            "original/USAGE.md": b"Original layer source and its separate usage notes.\n",
        }
        files = []
        for relative, body in contents.items():
            path = original / relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
            files.append({"source": str(path), "path": relative})
        archived = library.archive(self.external, {
            "id": "documented_component", "kind": "code_component",
            "entry": "index.html", "reuse_scope": {"kind": "general"},
        }, files)
        self.record = library.read(self.external / archived["record"])
        self.package = (self.external / archived["record"]).parent
        self.row = {
            "id": "paper:documented_component@" + archived["revision"],
            "source_id": "documented_component", "revision": archived["revision"],
            "kind": "code_component", "portable_record": archived["record"],
            "payload": [{**part, "path": str(
                Path(archived["record"]).parent / part["path"]
            )} for part in self.record["files"]],
        }
        (self.external / "catalog").mkdir()
        (self.external / "tools").mkdir()
        (self.external / "tools/query_assets.py").write_text("# valid discovery fixture\n")
        self.write_catalog()
        self.workspace.mkdir()
        (self.workspace / "workbench.yaml").write_text(
            "asset_library:\n  root: " + json.dumps(str(self.external)) + "\n"
        )
        self.project = self.workspace / "productions/s/e"
        self.project.mkdir(parents=True)
        library.write(self.project / "project.json", {"series_id": "s", "episode_id": "e"})
        library.write(self.project / "asset_manifest.json", {"assets": []})
        self.contents = contents

    def write_catalog(self):
        (self.external / "catalog/assets.jsonl").write_text(json.dumps(self.row) + "\n")

    def test_actual_use_preserves_top_level_and_original_usage_documents(self):
        result = companion.use(self.workspace, "productions/s/e", self.row["id"])
        self.assertEqual(result["status"], "copied_and_verified")
        destination = Path(result["directory"])
        for relative, expected in self.contents.items():
            self.assertEqual((destination / relative).read_bytes(), expected)
        self.assertNotEqual((destination / "USAGE.md").read_bytes(),
                            (destination / "original/USAGE.md").read_bytes())
        self.assertEqual(library.read(destination / "library-record.json")["revision"],
                         self.record["revision"])

    def test_duplicate_exact_mapping_still_fails_closed(self):
        self.row["payload"].append(dict(self.row["payload"][1]))
        self.write_catalog()
        with self.assertRaisesRegex(ValueError, "缺少精确载荷映射"):
            companion.use(self.workspace, "productions/s/e", self.row["id"])

    def test_nested_document_hash_is_checked_before_import(self):
        (self.package / "original/USAGE.md").write_bytes(b"Changed original notes")
        with self.assertRaisesRegex(ValueError, "载荷字节与所选版本不一致"):
            companion.use(self.workspace, "productions/s/e", self.row["id"])


if __name__ == "__main__":
    unittest.main()
