import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('mac_knowledge_locator', ROOT / 'runtime/native_helpers/med_autocast.py')
helper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(helper)


class ProjectKnowledgeLocatorTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.project = self.root / 'productions/disease/episode-one'
        self.project.mkdir(parents=True)
        self.config = {'schema': 'medical_video_workbench/v2', 'series': {
            'disease': {'episodes': {'01': {'project': 'productions/disease/episode-one'}}}}}
        (self.root / 'workbench.yaml').write_text(yaml.safe_dump(self.config))
        (self.project / 'project.json').write_text(json.dumps({'series_id': 'disease', 'episode_id': '01'}))
        self.rows = [{'project_id': 'confirmed-episode-a', 'project_root': 'productions/disease/episode-one'}]

    def save_index(self):
        # Focused locator fixture; full Framework inventory is exercised by the integration probe.
        (self.root / 'workspace_index.json').write_text(json.dumps({'projects': self.rows}))

    def locate(self):
        return helper.project_knowledge_locator(self.root, 'disease', '01')

    def test_missing_registration_is_visible_and_never_invents_identity(self):
        before = (self.root / 'workbench.yaml').read_bytes()
        result = self.locate()
        self.assertEqual(result['status'], 'missing')
        self.assertIsNone(result['project_id'])
        self.assertEqual(result['knowledge_project_args'], [])
        self.assertFalse((self.root / 'workspace_index.json').exists())
        self.assertEqual((self.root / 'workbench.yaml').read_bytes(), before)

    def test_registered_real_root_is_returned_without_relocating_episode(self):
        self.save_index()
        result = self.locate()
        self.assertEqual(result['project_id'], 'confirmed-episode-a')
        self.assertEqual(result['knowledge_project_args'], ['--project', str(self.project.resolve())])
        self.assertEqual(result['quality_debt'], [])

    def test_wrong_native_identity_is_rejected_even_when_index_matches(self):
        self.save_index()
        (self.project / 'project.json').write_text(json.dumps({'series_id': 'disease', 'episode_id': '02'}))
        with self.assertRaises(helper.ContractError):
            self.locate()

    def test_ambiguous_index_never_selects_the_first_row(self):
        self.rows.append({'project_id': 'other-id', 'project_root': 'productions/disease/episode-one'})
        self.save_index()
        with self.assertRaises(helper.ContractError):
            self.locate()

    def test_wrong_project_root_and_unknown_episode_do_not_leak_other_identity(self):
        self.rows[0]['project_root'] = 'productions/disease/episode-two'
        self.save_index()
        self.assertEqual(self.locate()['status'], 'missing')
        with self.assertRaises(helper.ContractError):
            helper.project_knowledge_locator(self.root, 'disease', '02')

    def test_native_path_escape_is_rejected(self):
        self.config['series']['disease']['episodes']['01']['project'] = '../outside'
        (self.root / 'workbench.yaml').write_text(yaml.safe_dump(self.config))
        with self.assertRaises(helper.ContractError):
            self.locate()
