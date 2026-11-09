"""Exercise the owner projection and note lifecycle without medical material."""
import json
import hashlib
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'runtime/native_helpers'))
from app_contribution import read_workspace, record_note, ContractError


class MiniAppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name).resolve()
        self.project = self.root / 'productions/demo/ep01'
        (self.project / 'out').mkdir(parents=True)
        (self.root / 'workbench.yaml').write_text('schema: medical_video_workbench/v2\nseries:\n  demo:\n    title: Example\n    episodes:\n      ep01:\n        project: productions/demo/ep01\n')
        self.write('project.json', {'schema':'paper_project/v1','series_id':'demo','episode_id':'ep01','title':'Paper motion','score':'score.json'})
        self.write('score.json', {'shots':[{'id':'fold','title':'Fold','start':0,'end':2}]})
        (self.project / 'out/video.mp4').write_bytes(b'fixture-media-not-a-quality-proof')
        self.write('out/current.json', {'path':'out/video.mp4','status':'rendered_with_quality_debt'})

    def tearDown(self):
        self.temp.cleanup()

    def write(self, name, value):
        (self.project / name).write_text(json.dumps(value))

    def selected(self):
        return read_workspace(self.root, {'series_id':'demo','episode_id':'ep01','shot_id':'fold'}, 'media')['data']['items'][0]

    def test_workspace_selects_current_candidate_and_shot_without_paths(self):
        row = self.selected()
        self.assertEqual(row['media']['artifact_ref'], str(self.project / 'out/video.mp4'))
        self.assertEqual((row['media']['start'], row['media']['end']), (0, 2))
        self.assertEqual(row['current_candidate']['status'], 'rendered_with_quality_debt')
        self.assertFalse((self.project / 'qa').exists())
        (self.project / 'out/video.mp4').unlink()
        row = self.selected()
        self.assertEqual(row['status'], 'in_progress')
        self.assertEqual(len(row['shots']), 1)

    def test_note_is_revision_bound_idempotent_and_never_approves(self):
        row = self.selected()
        value = {**row['actions'][0]['input'], 'shot_id':'fold','note':'Slow this motion so the change is visible.'}
        result = record_note(self.root, value)
        saved = json.loads(Path(result['result']['artifact_ref']).read_text())
        self.assertFalse(saved['domain_quality_approved'])
        self.assertEqual(saved['shot']['id'], 'fold')
        self.assertEqual(record_note(self.root, value), result)
        with self.assertRaisesRegex(ContractError, '不同输入'):
            record_note(self.root, {**value, 'note':'Different note'})
        self.write('score.json', {'shots':[{'id':'fold','title':'Fold','start':0,'end':3}]})
        with self.assertRaisesRegex(ContractError, '已变化'):
            record_note(self.root, {**value, 'request_id':'new-request'})
        self.assertFalse(self.selected()['review_notes'][0]['matches_current_revision'])

    def test_unregistered_selection_and_escaping_media_are_rejected(self):
        with self.assertRaisesRegex(ContractError, '未登记'):
            read_workspace(self.root, {'series_id':'demo','episode_id':'absent'}, 'media')
        self.write('out/current.json', {'path':'../../../../outside.mp4'})
        with self.assertRaisesRegex(ContractError, '越出'):
            self.selected()

    def test_exact_media_bytes_invalidate_an_old_review_even_with_same_stat(self):
        row = self.selected()
        path = self.project / 'out/video.mp4'
        stat = path.stat()
        path.write_bytes(b'x' * stat.st_size)
        os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
        current = self.selected()
        self.assertNotEqual(row['revision'], current['revision'])
        self.assertEqual(current['media']['sha256'], hashlib.sha256(path.read_bytes()).hexdigest())
        with self.assertRaisesRegex(ContractError, '已变化'):
            record_note(self.root, {**row['actions'][0]['input'], 'note': 'Old candidate'})

    def test_unknown_write_is_read_back_after_reopen_and_removed_shot(self):
        row = self.selected()
        value = {**row['actions'][0]['input'], 'note': 'Review this motion'}
        recorded = record_note(self.root, value)
        self.write('score.json', {'shots': []})
        # The caller lost the response; its known request ID resolves through
        # the read owner, without another write or a currently valid shot.
        lookup = {key: value[key] for key in ('series_id', 'episode_id', 'request_id')}
        reopened = read_workspace(self.root, lookup, 'status')['data']['items'][0]
        self.assertEqual(reopened['requested_note']['status'], 'recorded')
        self.assertFalse(reopened['requested_note']['note']['matches_current_revision'])
        self.assertEqual(record_note(self.root, value), recorded)
        missing = read_workspace(self.root, {**lookup, 'request_id': 'absent'}, 'status')['data']['items'][0]
        self.assertEqual(missing['requested_note']['status'], 'not_found')
        self.assertEqual(len(list((self.project / 'qa/miniapp-notes').iterdir())), 1)

    def test_revoked_workspace_registration_cannot_write_or_read_old_note(self):
        row = self.selected()
        value = {**row['actions'][0]['input'], 'note': 'Review this motion'}
        record_note(self.root, value)
        (self.root / 'workbench.yaml').write_text('schema: medical_video_workbench/v2\nseries: {}\n')
        with self.assertRaisesRegex(ContractError, '未登记'):
            record_note(self.root, value)
        with self.assertRaisesRegex(ContractError, '未登记'):
            read_workspace(self.root, {key: value[key] for key in ('series_id', 'episode_id', 'request_id')}, 'status')

    def test_installed_adapter_calls_the_same_owner(self):
        carrier = self.root / 'isolated-carrier'
        shutil.copytree(ROOT / 'plugins/med-autocast', carrier)
        adapter = json.loads((carrier / 'app-contribution-adapter.json').read_text())
        entry = adapter['reads']['med-autocast.workspace.v1#media']
        result = subprocess.run(entry['argv'], cwd=carrier, env={**os.environ,'OPL_PROFILE_WORKSPACE':str(self.root)},
                                input='{}', text=True, capture_output=True, check=True)
        body = json.loads(result.stdout)
        self.assertEqual(body['data']['items'][0]['id'], 'demo/ep01')
        self.assertEqual(body['state'], 'ready')
        value = {**body['data']['items'][0]['actions'][0]['input'], 'note': 'Review from relocated carrier'}
        action = adapter['actions']['med-autocast.workspace.v1#review.note']
        written = subprocess.run(action['argv'], cwd=carrier, env={**os.environ,'OPL_PROFILE_WORKSPACE':str(self.root)},
                                 input=json.dumps(value), text=True, capture_output=True, check=True)
        receipt = json.loads(written.stdout)['result']
        readback = adapter['reads'][receipt['readback']['data_ref']]
        reopened = subprocess.run(readback['argv'], cwd=carrier, env={**os.environ,'OPL_PROFILE_WORKSPACE':str(self.root)},
                                  input=json.dumps(receipt['readback']['input']), text=True, capture_output=True, check=True)
        note = json.loads(reopened.stdout)['data']['items'][0]['requested_note']
        self.assertEqual(note['status'], 'recorded')
        self.assertEqual(note['note']['note'], value['note'])
        self.assertTrue(note['note']['matches_current_revision'])


if __name__ == '__main__':
    unittest.main()
