import json
import hashlib
import tempfile
import unittest
from pathlib import Path

import sys

SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "runtime/workbench/scripts"
sys.path.insert(0, str(SCRIPT_ROOT))

from reclassify_quality_debt import (  # noqa: E402
    classify_asset_review,
    classify_motion_locator,
    json_hash,
    load_actual_asset_usage,
    source_binding,
)


class ReclassifyQualityDebtTests(unittest.TestCase):
    def test_motion_locator_starts_unresolved_without_bound_review(self):
        locator = {"code": "long_motion_dead_zone", "shot": "s01", "max_gap": 5.0}
        result = classify_motion_locator("series", "episode", locator, {
            "score_sha256": "score", "source_sha256": "source",
        })
        self.assertEqual(result["triage_status"], "unresolved")
        self.assertNotIn("FRAME_STRIP_RESOLVED", json.dumps(result))

    def test_only_current_hash_and_locator_identity_can_classify(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "score.json").write_text("{}", encoding="utf-8")
            (project / "src").mkdir()
            (project / "src/main.ts").write_text("export {};", encoding="utf-8")
            (project / "assets").mkdir()
            image = project / "assets/paper.png"
            image.write_bytes(b"paper-v1")
            locator = {"code": "long_motion_dead_zone", "shot": "s01"}
            evidence = project / "review.json"
            evidence.write_text("{\"frames\": [\"before\", \"after\"]}", encoding="utf-8")
            binding = source_binding(project)
            image.write_bytes(b"paper-v2")
            self.assertNotEqual(binding["source_sha256"], source_binding(project)["source_sha256"])
            binding = source_binding(project)
            review = {
                "series": "series", "episode": "episode",
                "locator": locator,
                "locator_sha256": json_hash(locator),
                "score_sha256": binding["score_sha256"],
                "source_sha256": binding["source_sha256"],
                "decision": "not_a_defect", "reason": "连续帧显示为有意阅读停留。",
                "review_method": "continuous_strip",
                "evidence_ref": str(evidence),
                "evidence_sha256": hashlib.sha256(evidence.read_bytes()).hexdigest(),
            }
            result = classify_motion_locator("series", "episode", locator, binding,
                                             [review], project)
            self.assertEqual(result["triage_status"], "reviewed_not_defect")
            stale = dict(review, source_sha256="stale")
            result = classify_motion_locator("series", "episode", locator, binding,
                                             [stale], project)
            self.assertEqual(result["triage_status"], "unresolved")
            self.assertEqual(result["review_diagnostics"][0]["code"], "stale_or_unbound_review")

    def test_catalog_payload_must_match_declared_sha(self):
        from reclassify_quality_debt import active_catalog_hashes

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            repo = root / "mac-media-assets"
            payload = repo / "payloads/piece.png"
            payload.parent.mkdir(parents=True)
            payload.write_bytes(b"payload")
            catalog = repo / "catalog/assets.jsonl"
            catalog.parent.mkdir(parents=True)
            record = {"id": "paper:piece", "curation": {"status": "active"},
                      "payload": [{"path": "payloads/piece.png",
                                   "sha256": hashlib.sha256(b"payload").hexdigest()}]}
            catalog.write_text(json.dumps(record) + "\n", encoding="utf-8")
            diagnostics = []
            hashes = active_catalog_hashes(root, {"asset_library": {"catalog": str(catalog)}},
                                           {}, diagnostics)
            self.assertIn(record["payload"][0]["sha256"], hashes)
            payload.write_bytes(b"tampered")
            hashes = active_catalog_hashes(root, {"asset_library": {"catalog": str(catalog)}},
                                           {}, diagnostics)
            self.assertNotIn(record["payload"][0]["sha256"], hashes)
            self.assertEqual(diagnostics[-1]["code"], "catalog_payload_not_verified")

    def test_asset_source_readback_is_not_scene_or_medical_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            source = project / "piece.png"
            source.write_bytes(b"asset")
            asset = {
                "asset_id": "piece", "path": "piece.png", "medical": True,
                "visual_review": {"status": "passed"},
            }
            result = classify_asset_review(project, asset, {"piece"}, {"asset"})
            self.assertEqual(result["tier"], "medical_and_scene_review_required")
            self.assertEqual(result["coverage_source"], "manifest_declaration_unverified")
            self.assertFalse(result["domain_quality_approved"])
            self.assertTrue(result["source_payload_readable"])
            self.assertFalse(result["catalog_payload_sha_verified"])

    def test_actual_asset_usage_keeps_mounted_only_out_of_scene_queue(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "actual.json"
            path.write_text(json.dumps({"episodes": [{
                "series": "s", "episode": "e", "coverage_method": "source_trace",
                "shots": [{"shot_id": "B01", "used_asset_ids": ["drawn"],
                           "procedural_refs": ["paperRoom"], "uncertain": ["static_only"]}],
            }]}), encoding="utf-8")
            usage, diagnostics = load_actual_asset_usage(path)
            self.assertFalse(diagnostics)
            self.assertEqual(usage[("s", "e")]["shots"]["B01"]["used_asset_ids"], ["drawn"])
            self.assertEqual(usage[("s", "e")]["coverage_method"], "source_trace")


if __name__ == "__main__":
    unittest.main()
