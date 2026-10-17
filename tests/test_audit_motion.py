import json
import tempfile
import unittest
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/workbench/scripts"))
from audit_motion import audit


class MotionAuditTests(unittest.TestCase):
    def test_reports_repeated_recipe_and_missing_phases_without_blocking(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score = {
                "fps": 24,
                "duration": 12,
                "shots": [
                    {
                        "id": "a",
                        "start": 0,
                        "end": 6,
                        "events": {"enter": 1, "contact": 3, "settle": 5},
                        "shot_recipe": {
                            "audience_read": "看到资料",
                            "visual_anchor": "资料袋",
                            "primary_motion": "从左侧进入",
                            "motion_arc": "进入到落定",
                        },
                    },
                    {
                        "id": "b",
                        "start": 6,
                        "end": 12,
                        "events": {"enter": 1, "contact": 3, "settle": 5},
                        "shot_recipe": {
                            "audience_read": "看到资料",
                            "visual_anchor": "资料袋",
                            "primary_motion": "从左侧进入",
                            "motion_arc": "进入到落定",
                        },
                    },
                ],
            }
            path = root / "score.json"
            path.write_text(json.dumps(score), encoding="utf-8")
            report = audit(root)
            codes = {item["code"] for item in report["quality_debt"]}
            self.assertIn("repeated_shot_recipe", codes)
            self.assertIn("representative_shot_unregistered", codes)
            self.assertTrue(all(item["blocks_stage_progress"] is False for item in report["quality_debt"]))
            self.assertEqual(report["summary"]["blocking_debt_count"], 0)

    def test_accepts_explicit_representative_shot_and_reports_gap(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score = {
                "duration": 10,
                "signature_shot": "hero",
                "shots": [
                    {
                        "id": "hero",
                        "start": 0,
                        "end": 10,
                        "events": {"prepare": 1, "action": 3, "reaction": 4, "settle": 5},
                        "shot_recipe": "一个物件从资料袋进入桌面并停住",
                    }
                ],
            }
            (root / "score.json").write_text(json.dumps(score), encoding="utf-8")
            report = audit(root)
            self.assertEqual(report["representative_shot"], "hero")
            self.assertFalse(any(item["code"] == "representative_shot_unregistered" for item in report["quality_debt"]))
            self.assertTrue(any(item["code"] == "long_motion_dead_zone" for item in report["quality_debt"]))


if __name__ == "__main__":
    unittest.main()
