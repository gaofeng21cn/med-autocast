"""Exercise real Framework v2 package inspection against staged agent definitions."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest


class HostedStageBindingsTest(unittest.TestCase):
    @unittest.skipUnless(os.environ.get('OPL_FRAMEWORK_ROOT'), 'requires explicit Framework source checkout')
    def test_every_stage_compiles_against_framework_runtime(self):
        root = Path(__file__).resolve().parents[1]
        opl_bin = os.environ.get('OPL_BIN') or str(Path(os.environ['OPL_FRAMEWORK_ROOT']) / 'bin' / 'opl')
        with tempfile.TemporaryDirectory() as iso:
            env = {
                **os.environ,
                'OPL_STATE_DIR': str(Path(iso) / 'state'),
                'OPL_DATA_DIR': str(Path(iso) / 'data'),
                'OPL_CACHE_DIR': str(Path(iso) / 'cache'),
            }
            result = subprocess.run([opl_bin, 'pack', 'inspect', str(root), '--json'],
                                    env=env, text=True, capture_output=True)
        self.assertEqual(result.returncode, 0, result.stderr or result.stdout)
        inspected = json.loads(result.stdout)
        manifest_v2 = inspected['manifest']
        self.assertEqual(manifest_v2['schema_version'], 'opl.package.v2')
        stages_ref = os.path.normpath(manifest_v2['provides']['agent']['stages_ref'])
        self.assertEqual(stages_ref, 'agent/stages/manifest.json')
        stages_doc = json.loads((root / 'agent/stages/manifest.json').read_text())
        for stage in stages_doc['stages']:
            for ref in [stage['policy_ref'], stage['prompt_ref'], *stage['knowledge_refs'], *stage['quality_gate_refs'], *stage.get('skill_refs', [])]:
                self.assertTrue((root / ref).is_file(), ref)
        self.assertTrue(len(stages_doc['stages']) > 0)
