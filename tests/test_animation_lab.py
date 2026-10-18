"""The sample tool must remain isolated from production / author data."""
import json
import importlib.util
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

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
            self.assertTrue((project/'examples/action_gallery/main.ts').is_file())
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

    def test_create_performance_study_without_author_or_narration(self):
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary)/'study'
            subprocess.run([sys.executable,str(TOOL),'create','--study','followup_bag','--project',str(project)],check=True,capture_output=True)
            self.assertEqual(json.loads((project/'LAB.json').read_text())['study'],'followup_bag')
            self.assertEqual(json.loads((project/'score.json').read_text())['duration'],12)
            self.assertIsNone(json.loads((project/'LAB.json').read_text())['narration'])
            self.assertTrue((project/'TREATMENT.md').is_file())

    def test_failed_iteration_preserves_video_and_success_replaces_viewing_copy(self):
        spec=importlib.util.spec_from_file_location('mac_animation_lab',TOOL)
        lab=importlib.util.module_from_spec(spec);spec.loader.exec_module(lab)
        with tempfile.TemporaryDirectory() as temporary:
            project=Path(temporary);(project/'out').mkdir()
            (project/'score.json').write_text(json.dumps({'fps':24}))
            video=project/'out/style-study.mp4';video.write_bytes(b'previous watchable example')
            with mock.patch.object(lab,'audio') as audio, mock.patch.object(lab.subprocess,'run',return_value=subprocess.CompletedProcess([],1,'','render failed')):
                with self.assertRaises(subprocess.CalledProcessError):lab.capture(project,'render')
                self.assertEqual(video.read_bytes(),b'previous watchable example')
                audio.assert_called_once_with(project)
            def succeed(*_args,**_kwargs):
                target=Path(json.loads((project/'render-config.json').read_text())['output'])
                self.assertNotEqual(target,video)
                target.write_bytes(b'new rendered example')
                return subprocess.CompletedProcess([],0,json.dumps({'output':str(target)})+'\n','')
            with mock.patch.object(lab,'audio') as audio,mock.patch.object(lab.subprocess,'run',side_effect=succeed):
                lab.capture(project,'render');audio.assert_called_once_with(project)
            self.assertEqual(video.read_bytes(),b'new rendered example')
            receipt=json.loads((project/'out/render-receipt.json').read_text())
            self.assertEqual(receipt['output'],str(video))
