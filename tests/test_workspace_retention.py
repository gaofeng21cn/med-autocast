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
import project_lifecycle as plc
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

    def test_round2_archive_work_wav_non_qa_preview_orphans_renders_and_gz_receipts(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            project, _qa = self.fixture(root)
            active_proj = root / 'productions/s/e/v2'
            active_proj.mkdir(parents=True)
            life.write(active_proj / 'project.json', {'audio': 'audio.wav'})
            (root / 'workbench.yaml').write_text(
                f"series:\n  s:\n    episodes:\n      e:\n        project: {active_proj.relative_to(root)}\n"
            )
            used_seg = active_proj / 'audio/segments/01_hook-keep.wav'
            orphan_seg = active_proj / 'audio/segments/01_hook-rejected.wav'
            write_valid_wav(used_seg)
            write_valid_wav(orphan_seg)
            life.write(orphan_seg.with_suffix('.json'), {'pronunciation_review': {'status': 'rejected'}})
            life.write(active_proj / 'audio/narration_beats.json', {
                'beats': [{'id': 'b1', 'audio': str(used_seg)}],
            })
            cur_mp4 = active_proj / 'out/final.mp4'
            old_mp4 = active_proj / 'out/draft.mp4'
            cur_mp4.parent.mkdir(parents=True)
            cur_mp4.write_bytes(b'current-mp4-bytes')
            old_mp4.write_bytes(b'old-draft-bytes')
            life.write(active_proj / 'out/current.json', {
                'path': str(cur_mp4),
                'sha256': life.sha(cur_mp4),
                'status': 'current',
            })
            out_prev = project / 'out/v1-preview.mp4'
            out_prev.mkdir(parents=True)
            for name in ('000-s1-0.00.png', 'contact.jpg', 'strip-s1.jpg'):
                Image.new('RGB', (16, 16), (30, 40, 50)).save(out_prev / name)
            life.write(out_prev / 'preview.json', {
                'project': str(project),
                'frames': [{'file': '000-s1-0.00.png'}],
                'motionStrips': [{'sheet': 'strip-s1.jpg'}],
            })
            ret_wav = project / 'audio/narration.wav'
            write_valid_wav(ret_wav)
            orig_ret = ret_wav.read_bytes()
            (root / 'work/review').mkdir(parents=True, exist_ok=True)
            (root / 'work/review/batch-summary.md').write_text(str(ret_wav))
            arch_wav = root / 'archive/deliveries/s/e/20261120/record/audio.wav'
            work_wav = root / 'work/voice-cache/seg1.wav'
            write_valid_wav(arch_wav)
            write_valid_wav(work_wav)
            orig_arch = arch_wav.read_bytes()
            orig_work = work_wav.read_bytes()

            wip_plan = life.plan(root, {'protected_projects': [str(active_proj.relative_to(root))]})
            wip_orphans = [r for r in wip_plan['decisions'] if r['category'] == 'orphan_take']
            wip_renders = [r for r in wip_plan['decisions'] if r['category'] == 'superseded_render']
            self.assertEqual(wip_orphans, [])
            self.assertEqual(wip_renders[0]['decision'], 'keep_operational')

            data = life.plan(root, {})
            plan_gz = root / 'work/disk-lifecycle-test/plan.json.gz'
            receipt_gz = root / 'work/disk-lifecycle-test/receipt.json.gz'
            life.write(plan_gz, data)
            self.assertEqual(life.read(plan_gz)['schema'], life.SCHEMA)

            with patch.object(life, 'assert_idle'):
                life.apply(
                    plan_gz, receipt_gz,
                    parts={'review_frame', 'audio', 'orphan_take', 'superseded_render'},
                )

            self.assertFalse((out_prev / '000-s1-0.00.png').exists())
            self.assertTrue((out_prev / 'contact.jpg').is_file())
            self.assertTrue(used_seg.is_file())
            self.assertFalse(orphan_seg.exists())
            self.assertTrue(cur_mp4.is_file())
            self.assertFalse(old_mp4.exists())
            self.assertFalse(ret_wav.exists())
            self.assertFalse(arch_wav.exists())
            self.assertFalse(work_wav.exists())
            for wav_orig, raw in ((ret_wav, orig_ret), (arch_wav, orig_arch), (work_wav, orig_work)):
                flac = wav_orig.with_suffix('.flac')
                self.assertTrue(flac.is_file())
                life.restore_file(flac)
                self.assertEqual(wav_orig.read_bytes(), raw)
            self.assertTrue(receipt_gz.is_file())
            self.assertIn('deleted', life.read(receipt_gz)['summary']['actions'])

    def test_three_state_lifecycle_seal_hydrate_revise_retire_and_delivery_cap(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            lib_asset = root / 'assets/paper-theatre/entries/desk_v1/desk.png'
            lib_asset.parent.mkdir(parents=True)
            Image.new('RGBA', (24, 24), (100, 120, 140, 255)).save(lib_asset)
            lib_bytes = lib_asset.read_bytes()

            v1 = root / 'productions/s/e/v1'
            v2 = root / 'productions/s/e/v2'
            for proj in (v1, v2):
                (proj / 'src').mkdir(parents=True)
                (proj / 'src/scene.ts').write_text('export const x = 1;\n')
                (proj / 'assets').mkdir(parents=True)
                (proj / 'qa/preview').mkdir(parents=True)
                (proj / 'out').mkdir(parents=True)
                life.write(proj / 'project.json', {
                    'schema': 'paper_project/v1',
                    'series_id': 's', 'episode_id': 'e',
                    'score': 'score.json', 'narration': 'narration.json',
                    'audio': 'audio.wav', 'voice': 'audio/narration-normalized.wav',
                })
                life.write(proj / 'score.json', {'shots': []})
                life.write(proj / 'narration.json', {'beats': []})
            (v2 / 'assets/desk.png').write_bytes(lib_bytes)
            custom_asset = v2 / 'assets/custom.png'
            Image.new('RGBA', (16, 16), (255, 10, 10, 255)).save(custom_asset)
            custom_bytes = custom_asset.read_bytes()
            write_valid_wav(v2 / 'audio.wav')
            write_valid_wav(v2 / 'audio/narration.wav')
            write_valid_wav(v2 / 'audio/narration-normalized.wav')
            write_valid_wav(v2 / 'audio/segments/01.wav')
            write_valid_wav(v2 / 'audio/mix-history/old/audio.wav')
            orig_audio = (v2 / 'audio.wav').read_bytes()
            orig_norm = (v2 / 'audio/narration-normalized.wav').read_bytes()
            orig_seg = (v2 / 'audio/segments/01.wav').read_bytes()
            for name in ('contact.jpg', 'strip-s1.jpg', 'event-S01-at.webp', 'clean-001-s1-1.0.webp'):
                Image.new('RGB', (16, 16), (50, 60, 70)).save(v2 / 'qa/preview' / name)
            life.write(v2 / 'qa/preview/preview.json', {'frames': []})

            pub_v = root / 'publish/s/e/video.mp4'
            pub_v.parent.mkdir(parents=True)
            pub_v.write_bytes(b'published-mp4-v2')
            deliv_m = root / 'deliveries/s/e/manifest.json'
            deliv_m.parent.mkdir(parents=True)
            life.write(deliv_m, {'project': str(v2)})
            (root / 'workbench.yaml').write_text(
                "series:\n  s:\n    publish_root: publish/s\n    episodes:\n      e:\n        project: productions/s/e/v2\n"
            )

            cur_mp4 = v2 / 'out/final.mp4'
            cur_mp4.write_bytes(b'unsynced-working-mp4')
            life.write(v2 / 'out/current.json', {'path': str(cur_mp4), 'sha256': life.sha(cur_mp4)})
            skip_res = plc.seal_project(v2, root, apply=True)
            self.assertEqual(skip_res['status'], 'skipped_working')
            self.assertTrue((v2 / 'assets/desk.png').is_file())

            cur_mp4.write_bytes(b'published-mp4-v2')
            life.write(v2 / 'out/current.json', {'path': str(cur_mp4), 'sha256': life.sha(cur_mp4)})
            with patch.object(life, 'assert_idle'):
                seal_res = plc.seal_project(v2, root, apply=True)
            self.assertEqual(seal_res['status'], 'sealed')
            self.assertFalse((v2 / 'audio/mix-history').exists())
            self.assertFalse((v2 / 'qa/preview/event-S01-at.webp').exists())
            self.assertTrue((v2 / 'qa/preview/contact.jpg').is_file())
            self.assertTrue((v2 / 'qa/preview/strip-s1.jpg').is_file())
            self.assertFalse((v2 / 'assets/desk.png').exists())
            self.assertTrue(custom_asset.is_file())
            self.assertFalse(cur_mp4.exists())
            self.assertFalse((v2 / 'audio.wav').exists())
            self.assertTrue((v2 / 'audio.flac').is_file())
            self.assertTrue((v2 / 'audio/narration.wav').is_file())
            self.assertTrue((v2 / 'storage-hydration.json').is_file())

            v3 = root / 'productions/s/e/v3'
            from types import SimpleNamespace
            pp.revise(SimpleNamespace(workspace=root, from_project=v2, project=v3))
            self.assertTrue((v2 / 'storage-hydration.json').is_file())
            self.assertFalse((v3 / 'storage-hydration.json').exists())
            self.assertEqual((v3 / 'assets/desk.png').read_bytes(), lib_bytes)
            self.assertEqual((v3 / 'assets/custom.png').read_bytes(), custom_bytes)
            self.assertEqual((v3 / 'audio.wav').read_bytes(), orig_audio)
            self.assertEqual((v3 / 'audio/narration-normalized.wav').read_bytes(), orig_norm)
            self.assertEqual((v3 / 'audio/segments/01.wav').read_bytes(), orig_seg)

            hyd = plc.hydrate_project(v2, root)
            self.assertEqual(hyd['status'], 'hydrated')
            self.assertFalse((v2 / 'storage-hydration.json').exists())
            self.assertEqual((v2 / 'assets/desk.png').read_bytes(), lib_bytes)
            self.assertEqual(cur_mp4.read_bytes(), b'published-mp4-v2')
            self.assertEqual((v2 / 'audio.wav').read_bytes(), orig_audio)

            with patch.object(life, 'assert_idle'):
                ret = plc.retire_revisions(root, apply=True)
            self.assertEqual(ret['status'], 'retired')
            self.assertEqual(ret['retired_revisions_removed'], 2)
            self.assertFalse(v1.exists())
            self.assertFalse(v3.exists())
            self.assertTrue(v2.is_dir())
            self.assertTrue(Path(ret['lineage_archive']).is_file())

            for ts in ('20261110T000000Z', '20261115T000000Z', '20261120T000000Z'):
                d = root / 'archive/deliveries/s/e' / ts / 'publish'
                d.mkdir(parents=True)
                (d / 'video.mp4').write_bytes(ts.encode())
            with patch.object(life, 'assert_idle'):
                pr = plc.prune_archived_deliveries(root, keep_latest=1, apply=True)
            self.assertEqual(pr['snapshots_removed'], 2)
            self.assertEqual(pr['snapshots_kept'], 1)
            self.assertEqual([p.name for p in (root / 'archive/deliveries/s/e').iterdir()], ['20261120T000000Z'])

    def test_expanded_health_check_and_one_command_optimize_loop(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp).resolve()
            lib_png = root / 'assets/paper-theatre/entries/desk/desk.png'
            lib_png.parent.mkdir(parents=True)
            payload = bytes([i % 251 for i in range(90000)])
            lib_png.write_bytes(payload)
            dup_copy = root / 'assets/copy_desk.bin'
            dup_copy.write_bytes(payload)

            v1 = root / 'productions/s/e/v1'
            v2 = root / 'productions/s/e/v2'
            for proj in (v1, v2):
                (proj / 'src').mkdir(parents=True)
                (proj / 'src/scene.ts').write_text('export const x = 1;\n')
                (proj / 'out').mkdir(parents=True)
                life.write(proj / 'project.json', {
                    'schema': 'paper_project/v1', 'series_id': 's', 'episode_id': 'e',
                    'score': 'score.json', 'narration': 'narration.json',
                    'audio': 'audio.wav', 'voice': 'audio/narration-normalized.wav',
                })
                life.write(proj / 'score.json', {'shots': []})
                life.write(proj / 'narration.json', {'beats': []})
            (v2 / 'node_modules').symlink_to(root / 'nonexistent_nm')
            (v1 / 'entries/dup').mkdir(parents=True)
            (v1 / 'entries/dup/a.txt').write_text('mirror')
            write_valid_wav(v2 / 'audio.wav')
            write_valid_wav(v2 / 'audio/mix-history/m1/audio.wav')
            pub_v = root / 'publish/s/e/video.mp4'
            pub_v.parent.mkdir(parents=True)
            pub_v.write_bytes(b'pub-mp4')
            cur_mp4 = v2 / 'out/final.mp4'
            cur_mp4.write_bytes(b'pub-mp4')
            life.write(v2 / 'out/current.json', {'path': str(cur_mp4), 'sha256': life.sha(cur_mp4)})
            deliv_m = root / 'deliveries/s/e/manifest.json'
            deliv_m.parent.mkdir(parents=True)
            life.write(deliv_m, {'project': str(v2)})
            (root / 'workbench.yaml').write_text(
                "delivery_policy:\n  archive_keep_latest: 1\nseries:\n  s:\n    publish_root: publish/s\n    episodes:\n      e:\n        project: productions/s/e/v2\n"
            )
            for ts in ('20261101T000000Z', '20261110T000000Z'):
                p = root / 'archive/deliveries/s/e' / ts / 'publish'
                p.mkdir(parents=True)
                (p / 'video.mp4').write_bytes(ts.encode())
            done_work = root / 'work/done-batch'
            done_work.mkdir(parents=True)
            (done_work / 'notes.md').write_text('# keep me\n')
            (done_work / 'cache.png').write_bytes(b'png-cache')
            active_work = root / 'work/active-batch'
            active_work.mkdir(parents=True)
            life.write(active_work / 'episode-queue.json', [{'id': 'e1', 'status': 'pending'}])
            (active_work / 'keep.png').write_bytes(b'active-png')

            before = life.check_health(root)
            codes = {f['code'] for f in before['findings']}
            self.assertEqual(before['status'], 'attention_needed')
            self.assertTrue({
                'dangling_node_modules_symlinks',
                'misplaced_entries_mirrors',
                'unsealed_published_episodes',
                'retired_revisions_present',
                'excess_archived_deliveries',
            }.issubset(codes))

            with patch.object(life, 'assert_idle'):
                opt = plc.optimize_workspace(root, include_work_prune=True, apply=True)

            self.assertEqual(opt['after']['health_status'], 'clean')
            self.assertEqual(opt['after']['findings'], [])
            self.assertFalse((v2 / 'node_modules').is_symlink())
            self.assertFalse(v1.exists())
            self.assertTrue((v2 / 'storage-hydration.json').is_file())
            self.assertTrue((done_work / 'notes.md').is_file())
            self.assertFalse((done_work / 'cache.png').exists())
            self.assertTrue((active_work / 'keep.png').is_file())
            self.assertIn('cow_dedup', opt['stages'])
            rep = plc.storage_report(root)
            self.assertGreater(rep['total_files'], 0)


if __name__ == '__main__':
    unittest.main()
