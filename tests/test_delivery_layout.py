"""Delivery replacement preserves recovery and never exposes multiple user versions."""
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
from delivery_layout import install, locations


class DeliveryLayoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / 'workbench.yaml').write_text('series:\n  s:\n    publish_root: publish/s\n')

    def staged(self, version):
        user, record = self.root / ('stage-' + version), self.root / ('record-' + version)
        user.mkdir(); record.mkdir()
        (user / 'video.mp4').write_bytes(version.encode())
        (record / 'manifest.json').write_text(json.dumps({'version': version}))
        return user, record

    def test_second_delivery_is_flat_and_old_bytes_are_recoverable(self):
        install(self.root, 's', '01', *self.staged('first'))
        result = install(self.root, 's', '01', *self.staged('second'))
        user = locations(self.root, 's', '01')['user']
        self.assertEqual([f.name for f in user.iterdir()], ['video.mp4'])
        self.assertEqual((user / 'video.mp4').read_bytes(), b'second')
        backup = Path(result['previous_delivery'])
        self.assertFalse(backup.is_relative_to(self.root / 'publish'))
        self.assertEqual((backup / 'publish/video.mp4').read_bytes(), b'first')
        self.assertEqual(json.loads((backup / 'record/manifest.json').read_text())['version'], 'first')

    def test_failed_record_install_restores_user_record_and_pointer(self):
        install(self.root, 's', '01', *self.staged('first'))
        loc = locations(self.root, 's', '01')
        before = loc['pointer'].read_bytes()
        user, record = self.staged('second')
        original = Path.rename
        def rename(source, destination):
            if source == record:
                raise OSError('injected storage failure')
            return original(source, destination)
        with patch.object(Path, 'rename', rename), self.assertRaises(OSError):
            install(self.root, 's', '01', user, record)
        self.assertEqual((loc['user'] / 'video.mp4').read_bytes(), b'first')
        self.assertEqual(json.loads((loc['record'] / 'manifest.json').read_text())['version'], 'first')
        self.assertEqual(loc['pointer'].read_bytes(), before)
