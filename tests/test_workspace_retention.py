import json
import shutil
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
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
import plan_workspace_retention as life
import shared_node_deps as deps
import paper_project as pp


def write_valid_wav(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), 'wb') as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(8000)
        stream.writeframes(bytes(1600))


@unittest.skipUnless(Image is not None, 'requires Pillow for lossless image fixture')
class RetentionTests(unittest.TestCase):
    def fixture(self, root):
        project = root / 'productions/s/e/v1'
        qa = project / 'qa/preview'
        qa.mkdir(parents=True)
        life.write(project / 'project.json', {'audio': 'audio.wav'})
        (root / 'workbench.yaml').write_text('series: {}\n')
        for name in [
            '000-s1-0.00.png', 'event-S01-action-at.png', 'event-S01-action-before.png',
            'clean-000-s1-0.00.png', 'contact.jpg', 'strip-s1.jpg',
        ]:
            Image.new('RGB', (16, 16), (10, 20, 30)).save(qa / name)
        life.write(qa / 'preview.json', {
            'project': str(project),
            'frames': [{'file': '000-s1-0.00.png'}],
            'motionStrips': [{'sheet': 'strip-s1.jpg'}],
        })
        return project, qa

    def test_necessity_before_format_and_explicit_reference(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project, qa = self.fixture(root)
            (project / 'review.md').write_text('[问题](qa/preview/000-s1-0.00.png)')
            data = life.plan(root, {})
            rows = {Path(r['path']).name: r for r in data['decisions']}
            self.assertEqual(rows['000-s1-0.00.png']['decision'], 'keep_operational')
            self.assertEqual(rows['event-S01-action-before.png']['decision'], 'delete_redundant')
            self.assertEqual(rows['event-S01-action-at.png']['decision'], 'keep_compressed')
            self.assertNotIn('contact.jpg', rows)

    def test_wip_protection_and_incomplete_summary(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project, qa = self.fixture(root)
            data = life.plan(root, {'protected_projects': [str(project.relative_to(root))]})
            self.assertEqual(next(r for r in data['decisions'] if Path(r['path']).name == 'event-S01-action-at.png')['decision'], 'keep_compressed')
            self.assertEqual(next(r for r in data['decisions'] if Path(r['path']).name == '000-s1-0.00.png')['decision'], 'delete_redundant')
            (qa / 'strip-s1.jpg').unlink()
            data = life.plan(root, {})
            self.assertTrue(all(not r['decision'].startswith('delete') for r in data['decisions']))

    def test_stale_plan_prevalidates_before_any_delete(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project, qa = self.fixture(root)
            data = life.plan(root, {})
            selected = [r for r in data['decisions'] if r['decision'].startswith('delete')]
            self.assertGreater(len(selected), 1)
            Path(selected[-1]['path']).write_bytes(b'changed')
            plan = root / 'plan.json'
            life.write(plan, data)
            with patch.object(life, 'assert_idle'):
                with self.assertRaises(RuntimeError):
                    life.apply(plan, root / 'result.json', parts={'review_frame'})
            self.assertTrue(Path(selected[0]['path']).exists())

    def test_lossless_apply_preserves_original_review_binding(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project, qa = self.fixture(root)
            (project / 'review.md').write_text('[问题](qa/preview/000-s1-0.00.png)')
            data = life.plan(root, {})
            plan = root / 'plan.json'
            life.write(plan, data)
            with patch.object(life, 'assert_idle'):
                life.apply(plan, root / 'result.json', parts={'review_frame'})
            self.assertTrue((qa / '000-s1-0.00.png').exists())
            self.assertTrue((qa / 'event-S01-action-at.webp').exists())
            self.assertFalse((qa / 'event-S01-action-before.png').exists())
            report = life.read(qa / 'preview.json')
            self.assertEqual(report['frames'][0]['file'], '000-s1-0.00.png')
            self.assertTrue((qa / 'lifecycle-receipt.json').is_file())

    def test_retained_historical_audio_restores_exact_wav_bytes(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project, _qa = self.fixture(root)
            audio = project / 'audio.wav'
            write_valid_wav(audio)
            original = audio.read_bytes()
            data = life.plan(root, {})
            plan = root / 'plan.json'
            life.write(plan, data)
            with patch.object(life, 'assert_idle'):
                life.apply(plan, root / 'result.json', parts={'audio'})
            self.assertFalse(audio.exists())
            life.restore_file(audio.with_suffix('.flac'))
            self.assertEqual(audio.read_bytes(), original)

    def test_symlink_escape_rejected_before_delete(self):
        with tempfile.TemporaryDirectory() as temp, tempfile.TemporaryDirectory() as external:
            root = Path(temp).resolve()
            project, qa = self.fixture(root)
            data = life.plan(root, {})
            selected = [r for r in data['decisions'] if r['decision'].startswith('delete')]
            first = Path(selected[0]['path'])
            first.unlink()
            first.symlink_to(Path(external) / 'file')
            plan = root / 'plan.json'
            life.write(plan, data)
            with patch.object(life, 'assert_idle'):
                with self.assertRaises(ValueError):
                    life.apply(plan, root / 'result.json', parts={'review_frame'})
            self.assertTrue(Path(selected[-1]['path']).exists())

    def test_project_node_modules_pruned_while_root_and_cache_protected(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project, _qa = self.fixture(root)
            (root / 'node_modules/playwright').mkdir(parents=True)
            (root / 'node_modules/playwright/index.js').write_text('root runtime')
            (root / '.cache/node-deps/abc/node_modules/esbuild').mkdir(parents=True)
            (root / '.cache/node-deps/abc/.ready.json').write_text('{}')
            life.write(project / 'package.json', {'name': 'kit', 'devDependencies': {'typescript': '5.9.3'}})
            life.write(project / 'package-lock.json', {'lockfileVersion': 3, 'packages': {'': {'devDependencies': {'typescript': '5.9.3'}}}})
            (project / 'node_modules/typescript').mkdir(parents=True)
            (project / 'node_modules/typescript/index.js').write_text('dup')
            orphan = root / 'productions/s/e/v_nolock'
            (orphan / 'node_modules/pkg').mkdir(parents=True)
            (orphan / 'node_modules/pkg/a.js').write_text('keep')

            data = life.plan(root, {})
            nm_rows = {Path(r['path']).parent.name: r for r in data['decisions'] if r['category'] == 'node_modules'}
            self.assertEqual(nm_rows['v1']['decision'], 'delete_rebuildable')
            self.assertEqual(nm_rows['v_nolock']['decision'], 'defer_review')
            self.assertNotIn(root.name, nm_rows)

            plan = root / 'plan.json'
            life.write(plan, data)
            with patch.object(life, 'assert_idle'):
                life.apply(plan, root / 'result.json', parts={'node_modules'})
            self.assertFalse((project / 'node_modules').exists())
            self.assertTrue((orphan / 'node_modules/pkg/a.js').is_file())
            self.assertTrue((root / 'node_modules/playwright/index.js').is_file())
            self.assertTrue((root / '.cache/node-deps/abc/node_modules/esbuild').is_dir())

    def test_active_mix_history_wav_compressed_and_render_scratch_scoped(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project, _qa = self.fixture(root)
            (root / 'workbench.yaml').write_text(
                f"series:\n  s:\n    episodes:\n      e:\n        project: {project.relative_to(root)}\n"
            )
            active_audio = project / 'audio.wav'
            write_valid_wav(active_audio)
            hist_dir = project / 'audio/mix-history/20261121T000000'
            hist_wav = hist_dir / 'audio.wav'
            write_valid_wav(hist_wav)
            orig_hist = hist_wav.read_bytes()
            life.write(hist_dir / 'snapshot.json', {'files': {'audio.wav': {'sha256': life.sha(hist_wav)}}})

            scratch = root / 'out/.render-abc/frame-0.png'
            scratch.parent.mkdir(parents=True)
            scratch.write_bytes(b'scratch')
            lib_sample = root / 'assets/paper-theatre/entries/p1/.render-xyz/frame-0.png'
            lib_sample.parent.mkdir(parents=True)
            lib_sample.write_bytes(b'asset sample')

            data = life.plan(root, {})
            audio_rows = {Path(r['path']): r for r in data['decisions'] if r['category'] == 'audio'}
            self.assertEqual(audio_rows[active_audio]['decision'], 'keep_operational')
            self.assertEqual(audio_rows[hist_wav]['decision'], 'keep_compressed')
            render_paths = {Path(r['path']) for r in data['decisions'] if r['category'] == 'render_temporary'}
            self.assertIn(scratch, render_paths)
            self.assertNotIn(lib_sample, render_paths)

            plan = root / 'plan.json'
            life.write(plan, data)
            with patch.object(life, 'assert_idle'):
                life.apply(plan, root / 'result.json', parts={'audio', 'render_temporary'})
            self.assertTrue(active_audio.is_file())
            self.assertFalse(hist_wav.exists())
            self.assertTrue(hist_wav.with_suffix('.flac').is_file())
            self.assertIn('audio.flac', life.read(hist_dir / 'snapshot.json')['files'])
            self.assertFalse(scratch.parent.exists())
            self.assertTrue(lib_sample.is_file())
            life.restore_file(hist_wav.with_suffix('.flac'))
            self.assertEqual(hist_wav.read_bytes(), orig_hist)

    def test_shared_deps_fingerprint_and_preserve_mix_flac(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            p1, p2 = root / 'p1', root / 'p2'
            p1.mkdir(); p2.mkdir()
            lock1 = {'lockfileVersion': 3, 'packages': {'': {'name': 'kit', 'version': '1.1.0', 'devDependencies': {'esbuild': '0.25.12'}}, 'node_modules/esbuild': {'version': '0.25.12'}}}
            lock2 = {'lockfileVersion': 3, 'packages': {'': {'name': 'kit', 'version': '1.2.0', 'devDependencies': {'esbuild': '0.25.12'}}, 'node_modules/esbuild': {'version': '0.25.12'}}}
            life.write(p1 / 'package-lock.json', lock1)
            life.write(p2 / 'package-lock.json', lock2)
            fp1, _ = deps.dependency_fingerprint(p1)
            fp2, _ = deps.dependency_fingerprint(p2)
            self.assertEqual(fp1, fp2)
            lock2['packages']['node_modules/esbuild']['version'] = '0.26.0'
            life.write(p2 / 'package-lock.json', lock2)
            fp3, _ = deps.dependency_fingerprint(p2)
            self.assertNotEqual(fp1, fp3)

            if shutil.which('flac'):
                proj = root / 'proj'
                proj.mkdir()
                config = {'audio': 'audio.wav', 'score': 'score.json', 'voice': 'voice.wav'}
                life.write(proj / 'project.json', config)
                life.write(proj / 'score.json', {'shots': []})
                write_valid_wav(proj / 'audio.wav')
                orig = (proj / 'audio.wav').read_bytes()
                history = Path(pp.preserve_mix(proj, config))
                self.assertTrue((history / 'audio.flac').is_file())
                self.assertFalse((history / 'audio.wav').exists())
                life.restore_file(history / 'audio.flac')
                self.assertEqual((history / 'audio.wav').read_bytes(), orig)

            health = life.check_health(root)
            self.assertEqual(health['status'], 'clean')


if __name__ == '__main__':
    unittest.main()
