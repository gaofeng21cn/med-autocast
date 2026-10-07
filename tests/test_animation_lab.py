"""The sample tool must remain isolated from production / author data."""
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
TOOL=ROOT/'runtime/workbench/scripts/animation_lab.py'

class AnimationLabTest(unittest.TestCase):
    def test_create_offline_source_and_preserve_existing_work(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'study'
            subprocess.run([sys.executable,str(TOOL),'create','--project',str(project)],check=True,capture_output=True)
            self.assertFalse(json.loads((project/'brand.json').read_text())['enabled'])
            self.assertFalse(json.loads((project/'LAB.json').read_text())['medical_content'])
            self.assertEqual(len(json.loads((project/'score.json').read_text())['shots']),7)
            self.assertTrue((project/'src/kit/paths.ts').is_file())
            (project/'important.txt').write_text('preserve this work')
            result=subprocess.run([sys.executable,str(TOOL),'create','--project',str(project)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual((project/'important.txt').read_text(),'preserve this work')
            self.assertTrue((project/'review/lab-diagnostic-create.json').is_file())
            production=Path(temporary)/'production';production.mkdir()
            (production/'important.txt').write_text('a real episode')
            result=subprocess.run([sys.executable,str(TOOL),'create','--project',str(production)],capture_output=True)
            self.assertNotEqual(result.returncode,0)
            self.assertEqual(list(production.iterdir()),[production/'important.txt'])

    def test_style_discovery_reads_actual_resources(self):
        result=subprocess.run([sys.executable,str(TOOL),'list'],check=True,capture_output=True,text=True)
        data=json.loads(result.stdout)
        for profile in data['profiles']:
            path=ROOT/'runtime/workbench/templates/animation/styles'/profile['style_ref']
            self.assertTrue(path.is_file())
