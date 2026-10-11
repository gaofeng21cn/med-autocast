"""Exercise the real Git/install/query/copy path, including non-blocking misses."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/workbench/scripts'))
import animation_library as local
import media_asset_library as companion


class MediaCompanionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / 'workspace'
        self.workspace.mkdir()
        self.repo = self.base / 'remote'
        self.repo.mkdir()
        (self.repo / 'tools').mkdir()
        (self.repo / 'catalog').mkdir()
        (self.repo / 'collections').mkdir()
        (self.repo / 'collections/series.json').write_text('{}')
        (self.repo / 'tools/query_assets.py').write_text("import json;from pathlib import Path;print((Path(__file__).resolve().parents[1]/'catalog/assets.jsonl').read_text().strip() or '[]')")
        (self.repo / 'tools/verify_catalog.py').write_text("print('verified')")
        original = self.base / 'original.png'
        original.write_bytes(b'actual paper bytes')
        archive = local.archive(self.repo, {'id': 'paper', 'kind': 'image', 'entry': 'files/paper.png',
                               'reuse_scope': {'kind': 'general'},
                               'asset': {'asset_id': 'paper', 'path': 'files/paper.png', 'medical': True,
                                         'status': 'approved_direct_use', 'visual_review': {'status': 'passed'}}},
                                [{'source': str(original), 'path': 'files/paper.png'}])
        record = local.read(self.repo / archive['record'])
        self.record = record
        self.row = {'id': 'paper:paper@' + record['revision'], 'source_id': 'paper',
                    'revision': record['revision'], 'kind': 'image', 'portable_record': archive['record'],
                    'reuse_scope': {'kind': 'general'}, 'review_boundary': {'admission': 'review_candidate'},
                    'payload': [{**record['files'][0], 'path': str(Path(archive['record']).parent/'files/paper.png')} ]}
        (self.repo / 'catalog/assets.jsonl').write_text(json.dumps(self.row) + '\n')
        # The fake query still runs through a real subprocess, returning the documented array.
        (self.repo / 'tools/query_assets.py').write_text("import json;from pathlib import Path;print(json.dumps([json.loads(s) for s in (Path(__file__).resolve().parents[1]/'catalog/assets.jsonl').read_text().splitlines() if s]))")
        subprocess.run(['git', 'init', '-b', 'main', str(self.repo)], check=True, capture_output=True)
        subprocess.run(['git', '-C', str(self.repo), 'add', '.'], check=True)
        subprocess.run(['git', '-C', str(self.repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'fixture'], check=True, capture_output=True)
        self.target = self.base / 'installed'
        (self.workspace / 'workbench.yaml').write_text('asset_library:\n  root: ' + str(self.target) + '\n')
        self.project = self.workspace / 'productions/s/e'
        self.project.mkdir(parents=True)
        local.write(self.project/'project.json', {'series_id':'s','episode_id':'e'})
        local.write(self.project/'asset_manifest.json', {'assets':[]})

    def test_real_install_reuse_copy_review_and_idempotence(self):
        installed = companion.ensure(self.workspace, repository=str(self.repo))
        self.assertEqual(installed['installation'], 'installed_and_verified')
        (self.target/'local-note.md').write_text('preserve this user edit')
        reused = companion.ensure(self.workspace, repository='/not-used')
        self.assertEqual(reused['installation'], 'reused_existing')
        self.assertEqual((self.target/'local-note.md').read_text(), 'preserve this user edit')
        found = companion.query(self.workspace)
        self.assertEqual(found['count'], 1)
        self.assertTrue(Path(found['assets'][0]['resolved_payloads'][0]['path']).is_file())
        result = companion.use(self.workspace, 'productions/s/e', self.row['id'])
        self.assertEqual(result['status'], 'copied_and_verified')
        self.assertEqual(Path(result['entry']).read_bytes(), b'actual paper bytes')
        asset = local.read(self.project/'asset_manifest.json')['assets'][0]
        self.assertEqual(asset['visual_review']['status'], 'pending')
        self.assertEqual(asset['medical_review']['status'], 'pending')
        self.assertEqual(companion.use(self.workspace,'productions/s/e', self.row['id'])['status'], 'copied_and_verified')
        self.assertEqual(len(local.read(self.workspace/'assets/paper-theatre/uses.json')['uses']), 1)

    def test_real_native_entry_selects_bundled_tool(self):
        completed = subprocess.run([sys.executable, str(ROOT/'runtime/native_helpers/workbench_tool.py'),
                                    '--workspace',str(self.workspace),'--name','media_asset_library','--','status'],
                                   capture_output=True,text=True,check=True)
        report=json.loads(completed.stdout)
        self.assertEqual(report['status'],'unavailable')
        self.assertFalse(report['blocks_production'])
        self.assertFalse(self.target.exists())

    def test_offline_empty_query_and_existing_directory_continue(self):
        report = companion.ensure(self.workspace, offline=True)
        self.assertFalse(report['blocks_production'])
        self.assertFalse(self.target.exists())
        self.assertEqual(companion.query(self.workspace)['count'], 0)
        self.target.mkdir()
        (self.target/'keep').write_text('keep')
        report = companion.ensure(self.workspace, repository=str(self.repo))
        self.assertEqual(report['installation'], 'preserved_existing')
        self.assertEqual((self.target/'keep').read_text(), 'keep')

    def test_author_scope_filtered_and_not_importable_for_other_author(self):
        companion.ensure(self.workspace, repository=str(self.repo))
        row = dict(self.row, reuse_scope={'kind':'author','id':'another_author'})
        (self.target/'catalog/assets.jsonl').write_text(json.dumps(row)+'\n')
        with patch.object(companion, 'author_id', return_value='current_author'):
            self.assertEqual(companion.query(self.workspace)['count'], 0)
            self.assertEqual(companion.query(self.workspace,include_author_assets=True)['count'],1)
        record = local.read(self.target / row['portable_record'])
        record['reuse_scope'] = row['reuse_scope']
        local.write(self.target/row['portable_record'],record)
        with patch.object(companion, 'author_id', return_value='current_author'):
            result = companion.use(self.workspace,'productions/s/e',row['id'])
        self.assertEqual(result['status'],'not_imported')
        self.assertFalse((self.project/'assets/library').exists())

    def test_corrupt_payload_and_static_reference_do_not_enter_motion_manifest(self):
        companion.ensure(self.workspace, repository=str(self.repo))
        row = dict(self.row, kind='reference_frame')
        (self.target/'catalog/assets.jsonl').write_text(json.dumps(row)+'\n')
        self.assertEqual(companion.use(self.workspace,'productions/s/e',row['id'])['status'],'not_imported')
        (self.target/'catalog/assets.jsonl').write_text(json.dumps(self.row)+'\n')
        (self.target/self.row['payload'][0]['path']).write_bytes(b'different')
        with self.assertRaises(ValueError):
            companion.use(self.workspace,'productions/s/e',self.row['id'])
        self.assertEqual(local.read(self.project/'asset_manifest.json')['assets'],[])


if __name__ == '__main__':
    unittest.main()
