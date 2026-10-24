"""Regression checks for the read-only first-draft quality brief."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/workbench/scripts"))
from first_draft_preflight import preflight


class FirstDraftPreflightTests(unittest.TestCase):
    def test_empty_declared_project_is_a_candidate_without_domain_approval(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "src").mkdir()
            (project / "src/episodeshots.ts").write_text("export const shots = [];\n")
            (project / "asset_manifest.json").write_text(json.dumps({
                "schema": "medical_animation_assets/v1",
                "assets": [],
                "shots": [{"shot_id": "B01", "asset_ids": []}],
            }))
            report = preflight(project)
            self.assertEqual(report["status"], "candidate")
            self.assertEqual(report["manifest"]["check"]["domain_quality_approved"], False)
            self.assertEqual(report["quality_debt"], [])

    def test_missing_manifest_and_programmatic_person_remain_locators(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "src").mkdir()
            source = project / "src/episodeshots.ts"
            source.write_text("""
function patient() {
  oval(10, 10, 20, 20);
  poly(10, 30, 20, 50);
  limb(10, 50, 20, 80);
}
""")
            report = preflight(project)
            self.assertEqual(report["status"], "blocked")
            self.assertIn("asset_manifest_missing", report["quality_debt"])
            self.assertIn("programmatic_character_locator", report["quality_debt"])
            self.assertGreater(report["character_scale_locator_count"], 0)


if __name__ == "__main__":
    unittest.main()
