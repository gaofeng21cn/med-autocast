import json
import sys
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch
try:
    from PIL import Image
except ImportError:  # Optional visual dependency in the fast lane.
    Image = None
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'runtime/workbench/scripts'))
import plan_workspace_retention as life


@unittest.skipUnless(Image is not None, 'requires Pillow for lossless image fixture')
class RetentionTests(unittest.TestCase):
    def fixture(self,root):
        project=root/'productions/s/e/v1';qa=project/'qa/preview';qa.mkdir(parents=True)
        life.write(project/'project.json',{'audio':'audio.wav'})
        (root/'workbench.yaml').write_text('series: {}\n')
        for name in ['000-s1-0.00.png','event-S01-action-at.png','event-S01-action-before.png','clean-000-s1-0.00.png','contact.jpg','strip-s1.jpg']:
            Image.new('RGB',(16,16),(10,20,30)).save(qa/name)
        life.write(qa/'preview.json',{'project':str(project),'frames':[{'file':'000-s1-0.00.png'}],
                 'motionStrips':[{'sheet':'strip-s1.jpg'}]})
        return project,qa

    def test_necessity_before_format_and_explicit_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();project,qa=self.fixture(root)
            (project/'review.md').write_text('[问题](qa/preview/000-s1-0.00.png)')
            data=life.plan(root,{})
            rows={Path(r['path']).name:r for r in data['decisions']}
            self.assertEqual(rows['000-s1-0.00.png']['decision'],'keep_operational')
            self.assertEqual(rows['event-S01-action-before.png']['decision'],'delete_redundant')
            self.assertEqual(rows['event-S01-action-at.png']['decision'],'keep_compressed')
            self.assertNotIn('contact.jpg',rows)

    def test_wip_protection_and_incomplete_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();project,qa=self.fixture(root)
            data=life.plan(root,{'protected_projects':[str(project.relative_to(root))]})
            self.assertEqual(next(r for r in data['decisions'] if Path(r['path']).name=='event-S01-action-at.png')['decision'], 'keep_operational')
            self.assertEqual(next(r for r in data['decisions'] if Path(r['path']).name=='000-s1-0.00.png')['decision'], 'keep_operational')
            (qa/'strip-s1.jpg').unlink()
            data=life.plan(root,{})
            self.assertTrue(all(not r['decision'].startswith('delete') for r in data['decisions']))

    def test_stale_plan_prevalidates_before_any_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();project,qa=self.fixture(root)
            data=life.plan(root,{})
            selected=[r for r in data['decisions'] if r['decision'].startswith('delete')]
            self.assertGreater(len(selected),1)
            Path(selected[-1]['path']).write_bytes(b'changed')
            plan=root/'plan.json';life.write(plan,data)
            with patch.object(life,'assert_idle'):
                with self.assertRaises(RuntimeError):life.apply(plan,root/'result.json',parts={'review_frame'})
            self.assertTrue(Path(selected[0]['path']).exists())

    def test_lossless_apply_preserves_original_review_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();project,qa=self.fixture(root)
            (project/'review.md').write_text('[问题](qa/preview/000-s1-0.00.png)')
            data=life.plan(root,{})
            plan=root/'plan.json';life.write(plan,data)
            with patch.object(life,'assert_idle'):life.apply(plan,root/'result.json',parts={'review_frame'})
            self.assertTrue((qa/'000-s1-0.00.png').exists())
            self.assertTrue((qa/'event-S01-action-at.webp').exists())
            self.assertFalse((qa/'event-S01-action-before.png').exists())
            report=life.read(qa/'preview.json')
            self.assertEqual(report['frames'][0]['file'],'000-s1-0.00.png')
            self.assertTrue((qa/'lifecycle-receipt.json').is_file())

    def test_retained_historical_audio_restores_exact_wav_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp).resolve();project,qa=self.fixture(root)
            audio=project/'audio.wav'
            with wave.open(str(audio),'wb') as stream:
                stream.setnchannels(1);stream.setsampwidth(2);stream.setframerate(8000)
                stream.writeframes(bytes(1600))
            original=audio.read_bytes()
            data=life.plan(root,{})
            plan=root/'plan.json';life.write(plan,data)
            with patch.object(life,'assert_idle'):life.apply(plan,root/'result.json',parts={'audio'})
            self.assertFalse(audio.exists())
            life.restore_file(audio.with_suffix('.flac'))
            self.assertEqual(audio.read_bytes(),original)

    def test_symlink_escape_rejected_before_delete(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as external:
            root=Path(temp).resolve();project,qa=self.fixture(root)
            data=life.plan(root,{})
            selected=[r for r in data['decisions'] if r['decision'].startswith('delete')]
            first=Path(selected[0]['path']);first.unlink();first.symlink_to(Path(external)/'file')
            plan=root/'plan.json';life.write(plan,data)
            with patch.object(life,'assert_idle'):
                with self.assertRaises(ValueError):life.apply(plan,root/'result.json',parts={'review_frame'})
            self.assertTrue(Path(selected[-1]['path']).exists())

if __name__=='__main__':unittest.main()
