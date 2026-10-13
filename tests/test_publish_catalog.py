"""Localized delivery keeps technical IDs, actual bytes, reviews and recovery."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
from delivery_layout import locations, install
from publish_catalog import migrate, refresh, check, prepare_names


class PublishCatalogTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'content').mkdir()
        self.eid = '01_report'
        self.config = {'series': {'s': {'title': '科普系列', 'publish_root': 'publish/s',
                        'release_catalog': 'content/catalog.yaml',
                        'delivery': {'display_name': '中文主题'}}}}
        self.catalog = {'series_id': 's', 'series_title': '主题系列', 'episodes': [
            {'id': self.eid, 'number': 1, 'title': '报告告诉了什么？'}]}
        self.write_config()
        (self.root / 'content/catalog.yaml').write_text(yaml.safe_dump(self.catalog, allow_unicode=True))

    def write_config(self):
        (self.root / 'workbench.yaml').write_text(yaml.safe_dump(self.config, allow_unicode=True))

    def original_delivery(self):
        loc = locations(self.root, 's', self.eid)
        loc['user'].mkdir(parents=True)
        for name, data in [('video.mp4', b'actual-video'), ('小红书文案.txt', '文案全文'.encode()),
                           ('微信视频号文案.txt', '另一个平台全文'.encode()), ('subtitles.srt', b'cue')]:
            (loc['user'] / name).write_bytes(data)
        loc['record'].mkdir(parents=True)
        receipt = {'schema': 'paper_review_delivery/v1', 'series_id': 's', 'episode_id': self.eid,
                   'sha256': hashlib.sha256(b'actual-video').hexdigest(),
                   'video': '../../../publish/s/01_report/video.mp4',
                   'reviews': {'medical': 'pending', 'full_motion': 'failed'}, 'release_eligible': False}
        (loc['record'] / 'manifest.json').write_text(json.dumps(receipt))
        loc['pointer'].write_text(json.dumps({'current': str(loc['user']), 'manifest': str(loc['record'] / 'manifest.json'), 'layout': 'latest_only'}))
        (loc['user'].parent / 'README.md').write_text('previous navigation')
        return loc, receipt

    def test_migration_preserves_bytes_review_and_internal_ids(self):
        old, receipt = self.original_delivery()
        result = migrate(self.root, ['s'])
        loc = locations(self.root, 's', self.eid)
        self.assertEqual(loc['user'].parent.name, '中文主题')
        self.assertTrue(loc['user'].name.startswith('01_报告'))
        self.assertEqual(loc['record'], old['record'])
        self.assertEqual((loc['user'] / 'video.mp4').read_bytes(), b'actual-video')
        after = json.loads((loc['record'] / 'manifest.json').read_text())
        self.assertEqual(after['reviews'], receipt['reviews'])
        self.assertFalse(after['release_eligible'])
        self.assertTrue((loc['record'] / after['video']).is_file())
        self.assertEqual(json.loads(loc['pointer'].read_text())['current'], str(loc['user']))
        self.assertEqual(check(self.root)['status'], 'passed')
        self.assertEqual(result['navigation']['episodes'], 1)
        self.assertTrue((Path(result['archive']) / 'workbench.before.yaml').is_file())
        self.assertIn('文案全文', (loc['user'].parent / '全季发布文案.md').read_text())
        # Editorial corrections do not silently rename a delivered folder.
        first = loc['user']
        self.catalog['episodes'][0]['title'] = '修订标题'
        (self.root / 'content/catalog.yaml').write_text(yaml.safe_dump(self.catalog, allow_unicode=True))
        prepare_names(self.root, 's')
        self.assertEqual(locations(self.root, 's', self.eid)['user'], first)

    def test_conflicting_destination_leaves_original_and_config_intact(self):
        old, _ = self.original_delivery()
        before = (self.root / 'workbench.yaml').read_bytes()
        (self.root / 'publish/中文主题').mkdir()
        with self.assertRaisesRegex(ValueError, '已经存在'):
            migrate(self.root, ['s'])
        self.assertEqual((old['user'] / 'video.mp4').read_bytes(), b'actual-video')
        self.assertEqual((self.root / 'workbench.yaml').read_bytes(), before)

    def test_legacy_series_and_batch_move_outside_user_directory(self):
        self.original_delivery()
        self.config['series']['legacy'] = {'publish_root': 'publish/legacy'}
        self.write_config()
        (self.root / 'publish/legacy').mkdir()
        (self.root / 'publish/legacy/old.mp4').write_bytes(b'legacy')
        (self.root / 'publish/batch.html').write_text('old batch')
        result = migrate(self.root, ['s'], ['legacy'], ['batch.html'])
        self.assertFalse((self.root / 'publish/legacy').exists())
        self.assertFalse((self.root / 'publish/batch.html').exists())
        archive = Path(result['archive'])
        self.assertEqual((archive / 'legacy-series/legacy/old.mp4').read_bytes(), b'legacy')
        self.assertEqual((archive / 'navigation/batch.html').read_text(), 'old batch')
        self.assertEqual(check(self.root)['series'], 1)

    def test_repackage_uses_same_folder_and_refreshes_navigation(self):
        self.original_delivery()
        migrate(self.root, ['s'])
        loc = locations(self.root, 's', self.eid)
        user = self.root / 'new-user'; record = self.root / 'new-record'
        user.mkdir(); record.mkdir()
        (user / 'video.mp4').write_bytes(b'new-video')
        (record / 'manifest.json').write_text(json.dumps({'reviews': {'medical':'pending'}}))
        result = install(self.root, 's', self.eid, user, record)
        self.assertEqual((loc['user'] / 'video.mp4').read_bytes(), b'new-video')
        self.assertFalse((self.root / 'publish/s').exists())
        self.assertEqual(result['navigation']['episodes'], 1)
        self.assertEqual((Path(result['previous_delivery']) / 'publish/video.mp4').read_bytes(), b'actual-video')
        self.assertEqual(check(self.root)['status'], 'passed')

    def test_navigation_failure_keeps_completed_migration_and_delivery(self):
        self.original_delivery()
        with patch('publish_catalog.refresh', side_effect=RuntimeError('导航需修复')):
            result = migrate(self.root, ['s'])
        loc = locations(self.root, 's', self.eid)
        self.assertEqual((loc['user'] / 'video.mp4').read_bytes(), b'actual-video')
        self.assertFalse(result['navigation']['blocks_stage_progress'])
        self.assertEqual(json.loads(loc['pointer'].read_text())['current'], str(loc['user']))
        user = self.root / 'new-user'; record = self.root / 'new-record'
        user.mkdir(); record.mkdir()
        (user / 'video.mp4').write_bytes(b'new-video')
        (record / 'manifest.json').write_text('{}')
        with patch('publish_catalog.refresh', side_effect=RuntimeError('导航需修复')):
            result = install(self.root, 's', self.eid, user, record)
        self.assertFalse(result['navigation']['blocks_stage_progress'])
        self.assertEqual((loc['user'] / 'video.mp4').read_bytes(), b'new-video')

    def test_new_workspace_names_and_missing_library_do_not_gate_delivery(self):
        self.config['delivery_policy'] = {'naming':'localized_titles'}
        self.write_config()
        prepare_names(self.root, 's')
        self.assertEqual(locations(self.root,'s',self.eid)['user'].parent.name, '中文主题')
        self.assertEqual(refresh(self.root)['episodes'], 0)
        self.assertEqual(locations(self.root,'s',self.eid)['record'].parent.name, 's')


if __name__ == '__main__': unittest.main()
