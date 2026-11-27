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

    def test_actor_naturalness_heading_in_camera_and_revise_refresh_kit(self):
        import paper_project

        with tempfile.TemporaryDirectory() as tmp:
            ws = Path(tmp).resolve()
            (ws / "workbench.yaml").write_text("schema: test\n", encoding="utf-8")
            project = ws / "productions/s/e/v1"
            (project / "src/kit").mkdir(parents=True)
            (project / "src/kit/acting.ts").write_text("// custom helper\n", encoding="utf-8")
            (project / "src/kit/actor.ts").write_text("// stale kit\n", encoding="utf-8")
            (project / "score.json").write_text(
                json.dumps({"duration": 5.0, "shots": [{"id": "S01", "start": 0.0, "end": 5.0}]}),
                encoding="utf-8",
            )
            (project / "narration.json").write_text("{}\n", encoding="utf-8")
            (project / "project.json").write_text(
                json.dumps({
                    "schema": "paper_project/v1",
                    "series_id": "s",
                    "episode_id": "e",
                    "narration": "narration.json",
                    "score": "score.json",
                    "assets": "asset_manifest.json",
                }),
                encoding="utf-8",
            )
            (project / "sheet.png").write_bytes(b"sheet")
            (project / "asset_manifest.json").write_text(
                json.dumps({
                    "schema": "medical_animation_assets/v1",
                    "assets": [{
                        "asset_id": "presenter_acting_v2__sheet",
                        "path": "sheet.png",
                        "visual_layer": "character",
                        "visual_meaning": "presenter atlas",
                        "must_not_imply": "not a diagnosis",
                        "medical": False,
                        "source_type": "authored_graphic",
                        "requires_alpha": False,
                    }],
                    "shots": [{"shot_id": "S01", "asset_ids": ["presenter_acting_v2__sheet"]}],
                }),
                encoding="utf-8",
            )
            (project / "src/episodeshots.ts").write_text(
                "import { drawActorAtlas } from './kit/actor';\n"
                "export const shots = [{ id: 'S01', render(c: any) {\n"
                "  c.stage.camera({x:640,y:360,zoom:1.1}, () => { heading(c, 'title'); });\n"
                "  drawActorAtlas(c.stage, c.t, { spec: {} as any, beats: [{ at: 0, pose: 'a' }, { at: 0.8, pose: 'b' }], x: 960, y: 500, spanOrBeat: 5, context: c });\n"
                "  desk(c, 960, 440, 560, 560);\n"
                "} }];\n",
                encoding="utf-8",
            )
            report = preflight(project, scan_interactions=False)
            an = report["actor_naturalness"]
            self.assertEqual(an["bust_behind_hollow_desk"], 1)
            self.assertEqual(an["rapid_actor_switches"], 1)
            self.assertEqual(an["heading_inside_camera"], 1)
            self.assertIn("bust_behind_hollow_desk_detected", report["quality_debt"])
            self.assertIn("heading_inside_camera_detected", report["quality_debt"])

            rev = ws / "productions/s/e/v2"
            args = type("Args", (), {"workspace": ws, "project": rev, "from_project": project, "refresh_kit": True})()
            res = paper_project.revise(args)
            self.assertTrue(res["refreshed_kit"])
            self.assertTrue((rev / "src/kit/acting.ts").is_file())
            self.assertIn("drawForegroundDesk", (rev / "src/kit/actor.ts").read_text(encoding="utf-8"))
            self.assertIn("drawCloseWallBackdrop", (rev / "src/kit/rooms.ts").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
