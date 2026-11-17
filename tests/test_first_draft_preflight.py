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
    def test_declared_people_cannot_be_hidden_by_a_generic_name_or_diagram_role(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / 'src').mkdir()
            (project / 'src/episodeshots.ts').write_text('export const shots = [];')
            (project / 'figure.png').write_bytes(b'figure')
            asset = {'asset_id': 'figure', 'path': 'figure.png', 'visual_meaning': 'figure',
                     'must_not_imply': 'diagnosis', 'medical': False, 'source_type': 'authored_graphic'}
            manifest = {'schema': 'medical_animation_assets/v1',
                        'scale_contract': {'status': 'pending', 'enforcement': 'required',
                                           'human_asset_ids': ['figure']},
                        'assets': [asset], 'shots': [{'shot_id': 'B01', 'asset_ids': ['figure']}]}
            path = project / 'asset_manifest.json'
            path.write_text(json.dumps(manifest))
            report = preflight(project)
            self.assertEqual(report['status'], 'blocked')
            self.assertEqual(report['manifest']['human_scale_pending'], ['figure'])
            asset['scale_mode'] = 'diagrammatic_structure'
            path.write_text(json.dumps(manifest))
            report = preflight(project)
            self.assertEqual(report['status'], 'blocked')
            self.assertIn('scale_contract_human_diagram_conflict', report['quality_debt'])

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

    def test_required_same_scene_scale_contract_blocks_unmarked_people_but_allows_diagram_layer(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "src").mkdir()
            (project / "src/episodeshots.ts").write_text("export const shots = [];\n")
            human = project / "human.png"
            human.write_bytes(b"human")
            diagram = project / "diagram.png"
            diagram.write_bytes(b"diagram")
            (project / "asset_manifest.json").write_text(json.dumps({
                "schema": "medical_animation_assets/v1",
                "scale_contract": {
                    "status": "pending",
                    "enforcement": "required",
                    "pixels_per_cm": 2.7,
                },
                "assets": [
                    {
                        "asset_id": "patient",
                        "path": "human.png",
                        "visual_layer": "character",
                        "visual_meaning": "patient",
                        "must_not_imply": "not a diagnosis",
                        "medical": False,
                        "source_type": "authored_graphic",
                        "requires_alpha": False,
                    },
                    {
                        "asset_id": "thyroid_diagram",
                        "path": "diagram.png",
                        "visual_layer": "medical_diagram",
                        "visual_meaning": "thyroid diagram",
                        "must_not_imply": "not a patient image",
                        "medical": True,
                        "medical_reference": "diagram.png",
                        "source_type": "authored_graphic",
                        "requires_alpha": False,
                    },
                ],
                "shots": [{"shot_id": "B01", "asset_ids": ["patient", "thyroid_diagram"]}],
            }))
            report = preflight(project)
            self.assertEqual(report["status"], "blocked")
            self.assertIn("scale_contract_pending", report["quality_debt"])
            self.assertEqual(report["manifest"]["scale_contract"]["diagram_layer_exempt"], ["thyroid_diagram"])

    def test_explicit_diagram_is_not_reclassified_as_person_by_its_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "src").mkdir()
            (project / "src/episodeshots.ts").write_text("export const shots = [];")
            (project / "diagram.png").write_bytes(b"diagram")
            (project / "asset_manifest.json").write_text(json.dumps({
                "schema": "medical_animation_assets/v1",
                "scale_contract": {
                    "schema": "medical_scene_scale_contract/v1",
                    "status": "not_applicable",
                    "enforcement": "required",
                    "human_asset_ids": [],
                    "same_scene_test_fit": {"status": "not_applicable"},
                },
                "assets": [{
                    "asset_id": "patient_anatomy_diagram",
                    "path": "diagram.png",
                    "visual_layer": "medical_diagram",
                    "visual_meaning": "患者甲状腺解剖示意图",
                    "must_not_imply": "不是患者真实影像",
                    "medical": False,
                    "source_type": "authored_graphic",
                }],
                "shots": [{"shot_id": "B01", "asset_ids": ["patient_anatomy_diagram"]}],
            }))
            report = preflight(project)
            self.assertEqual(report["status"], "candidate")
            self.assertEqual(report["manifest"]["human_assets"], 0)
            self.assertEqual(report["manifest"]["scale_contract"]["diagram_layer_exempt"], ["patient_anatomy_diagram"])

    def test_diagrammatic_scale_mode_is_exempt_without_medical_diagram_label(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "src").mkdir()
            (project / "src/episodeshots.ts").write_text("export const shots = [];")
            (project / "chart.png").write_bytes(b"chart")
            (project / "asset_manifest.json").write_text(json.dumps({
                "schema": "medical_animation_assets/v1",
                "scale_contract": {
                    "schema": "medical_scene_scale_contract/v1",
                    "status": "not_applicable",
                    "enforcement": "required",
                    "human_asset_ids": [],
                    "same_scene_test_fit": {"status": "not_applicable"},
                },
                "assets": [{
                    "asset_id": "patient_risk_chart",
                    "path": "chart.png",
                    "scale_mode": "data_visualization",
                    "diagram_class": "risk_tiers",
                    "visual_meaning": "患者风险分层图",
                    "must_not_imply": "不是患者身体或真实比例",
                    "medical": False,
                    "source_type": "authored_graphic",
                }],
                "shots": [{"shot_id": "B01", "asset_ids": ["patient_risk_chart"]}],
            }))
            report = preflight(project)
            self.assertEqual(report["status"], "candidate")
            self.assertEqual(report["manifest"]["human_assets"], 0)
            self.assertEqual(report["manifest"]["scale_contract"]["diagram_classes"], {"patient_risk_chart": "risk_tiers"})

    def test_required_contract_needs_exact_people_and_same_scene_fit(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp)
            (project / "src").mkdir()
            (project / "src/episodeshots.ts").write_text("export const shots = [];")
            (project / "person.png").write_bytes(b"person")
            (project / "fit.html").write_text("fit")
            (project / "asset_manifest.json").write_text(json.dumps({
                "schema": "medical_animation_assets/v1",
                "scale_contract": {
                    "schema": "medical_scene_scale_contract/v1",
                    "status": "ready",
                    "enforcement": "required",
                    "pixels_per_cm": 3,
                    "human_asset_ids": ["other_person"],
                    "same_scene_test_fit": {"status": "pending", "evidence_refs": ["fit.html"]},
                },
                "assets": [{
                    "asset_id": "person",
                    "path": "person.png",
                    "visual_layer": "character",
                    "visual_meaning": "patient",
                    "must_not_imply": "not a diagnosis",
                    "medical": False,
                    "source_type": "authored_graphic",
                    "human_scale": {"calibration": {"status": "pending"}},
                }],
                "shots": [{"shot_id": "B01", "asset_ids": ["person"]}],
            }))
            report = preflight(project)
            self.assertEqual(report["status"], "blocked")
            self.assertIn("scale_contract_human_asset_ids_mismatch", report["quality_debt"])
            self.assertIn("same_scene_test_fit_pending", report["quality_debt"])


if __name__ == "__main__":
    unittest.main()
