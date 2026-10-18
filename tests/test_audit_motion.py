import json
import tempfile
import unittest
from pathlib import Path
import sys
import subprocess

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "runtime/workbench/scripts"))
from audit_motion import audit


class MotionAuditTests(unittest.TestCase):
    def test_declared_holds_and_different_prose_do_not_hide_locating_intervals(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            score = {"duration": 40, "motion_review": {"schema": "motion_director_evidence/v1"}, "shots": []}
            for i in range(4):
                score["shots"].append({"id": str(i), "start": i*10, "end": (i+1)*10,
                    "events": {"contact": 1}, "motion_arc": f"different prose {i}",
                    "phase_evidence": {phase: {"at": 1} for phase in ["prepare","action","reaction","settle"]},
                    "hold_reason": "已登记阅读", "motion_quality_review": {"status": "intentional_reading_hold"}})
            (root / "score.json").write_text(json.dumps(score))
            report = audit(root)
            codes = [item["code"] for item in report["quality_debt"]]
            self.assertEqual(codes.count("long_motion_dead_zone"), 4)
            self.assertIn("repeated_event_signature", codes)
            self.assertTrue(all(row["legacy_auto_enriched"] for row in report["shots"]))
            self.assertTrue(all("reaction" in row["missing_phases"] for row in report["shots"]))

    def test_review_export_does_not_mutate_scores_or_infer_missing_events(self):
        tool = Path(__file__).resolve().parents[1] / "runtime/workbench/scripts/resolve_motion_audit.py"
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = root / "productions/one"; project.mkdir(parents=True)
            score_path = project / "score.json"
            original = b'{"shots":[{"id":"one","events":{"contact":1}}]}'
            score_path.write_bytes(original)
            (root / "workbench.yaml").write_text("series:\n  s:\n    episodes:\n      e:\n        project: productions/one\n")
            subprocess.run([sys.executable, str(tool), "--workspace", str(root)], check=True, capture_output=True)
            report = json.loads((root / "work/review/motion-review-packet.json").read_text())
            self.assertEqual(score_path.read_bytes(), original)
            self.assertFalse(report["production_inputs_modified"])
            self.assertFalse(report["source_code_or_frames_inspected"])
            row = report["detail"][0]["shots"][0]
            self.assertEqual(row["events"], {"contact": 1})
            self.assertEqual(row["declared"], {})
            # Even an explicitly requested output cannot overwrite a score.
            result = subprocess.run([sys.executable, str(tool), "--workspace", str(root), "--output", str(score_path)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(score_path.read_bytes(), original)

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
