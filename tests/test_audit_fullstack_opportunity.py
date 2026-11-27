"""Regression tests for full-stack opportunity & actor naturalness static locators."""
from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "runtime/workbench/scripts"))

import audit_fullstack_opportunity as fullstack_audit  # noqa: E402


class FullstackOpportunityAuditTests(unittest.TestCase):
    def test_detects_bust_behind_hollow_desk_rapid_switches_and_heading_inside_camera(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "ep_check"
            (project / "src").mkdir(parents=True)
            (project / "score.json").write_text(
                json.dumps({
                    "duration": 5.0,
                    "shots": [{
                        "id": "S01",
                        "start": 0.0,
                        "end": 5.0,
                        "events": {"prepare": 0.3, "action": 1.5, "reaction": 2.6, "settle": 3.6},
                        "motion_arc": "consult",
                        "visual_anchor": "presenter",
                    }],
                    "cues": [{"start": 0.2, "end": 4.5, "text": "复诊时带齐资料。"}],
                }),
                encoding="utf-8",
            )
            (project / "asset_manifest.json").write_text(
                json.dumps({
                    "schema": "medical_animation_assets/v1",
                    "scale_contract": {"enforcement": "required", "human_asset_ids": ["presenter_acting_v2__sheet"]},
                    "assets": [
                        {"asset_id": "presenter_acting_v2__sheet", "path": "src/sheet.png", "visual_layer": "character"},
                        {"asset_id": "doctor_legacy", "path": "assets/library/clinician_pointing_v1/a/payload.png", "visual_layer": "character"},
                    ],
                }),
                encoding="utf-8",
            )
            (project / "src/episodeshots.ts").write_text(
                "import { drawActorAtlas } from './kit/actor';\n"
                "export const shots = [{ id: 'S01', render(c: any) {\n"
                "  c.stage.camera({ x: 640, y: 360, zoom: 1.08 }, () => {\n"
                "    heading(c, '推镜内不该放顶栏标题');\n"
                "  });\n"
                "  drawActorAtlas(c.stage, c.t, { spec: {} as any, beats: [{ at: 0, pose: 'listen' }, { at: 0.7, pose: 'explain' }], x: 960, y: 500, spanOrBeat: 5, context: c });\n"
                "  desk(c, 960, 440, 560, 560);\n"
                "} }];\n",
                encoding="utf-8",
            )
            rep = fullstack_audit.analyze_project(project)
            ao = rep["actor_opportunities"]
            sb = rep["storyboard_opportunities"]
            self.assertEqual(ao["bust_behind_hollow_desk"], 1)
            self.assertEqual(ao["rapid_actor_switches"], 1)
            self.assertEqual(ao["uses_legacy_stiff_poses"], ["clinician_pointing_v1"])
            self.assertTrue(ao["stiff_actor_risk"])
            self.assertEqual(sb["heading_inside_camera"], 1)
            self.assertIn("actor_performance", rep["recommended_layers"])
            self.assertIn("storyboard", rep["recommended_layers"])

            # Fixing to floorless desk_close + drawForegroundDesk + calm 2-state switch + heading outside camera clears all risks
            (project / "asset_manifest.json").write_text(
                json.dumps({
                    "schema": "medical_animation_assets/v1",
                    "scale_contract": {"enforcement": "required", "human_asset_ids": ["presenter_acting_v2__sheet"]},
                    "assets": [
                        {"asset_id": "presenter_acting_v2__sheet", "path": "src/sheet.png", "visual_layer": "character"},
                    ],
                }),
                encoding="utf-8",
            )
            (project / "src/episodeshots.ts").write_text(
                "import { drawActorAtlas, drawForegroundDesk } from './kit/actor';\n"
                "export const shots = [{ id: 'S01', render(c: any) {\n"
                "  c.stage.camera({ x: 640, y: 360, zoom: 1.05 }, () => {\n"
                "    drawActorAtlas(c.stage, c.t, { spec: {} as any, beats: [{ at: 0, pose: 'listen' }, { at: 2.1, pose: 'explain' }], x: 980, y: 540, clipBottomY: 532, spanOrBeat: 5, context: c });\n"
                "    drawForegroundDesk(c.stage, { topY: 524 });\n"
                "  });\n"
                "  heading(c, '顶栏标题位于camera之外');\n"
                "} }];\n",
                encoding="utf-8",
            )
            clean = fullstack_audit.analyze_project(project)
            self.assertEqual(clean["actor_opportunities"]["bust_behind_hollow_desk"], 0)
            self.assertEqual(clean["actor_opportunities"]["rapid_actor_switches"], 0)
            self.assertFalse(clean["actor_opportunities"]["stiff_actor_risk"])
            self.assertEqual(clean["storyboard_opportunities"]["heading_inside_camera"], 0)


if __name__ == "__main__":
    unittest.main()
