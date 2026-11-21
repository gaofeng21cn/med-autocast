"""Delivery replacement preserves recovery and never exposes multiple user versions."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
from delivery_layout import install, locations
import plan_workspace_retention as life


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

    @unittest.skipUnless(shutil.which('flac'), 'requires flac for lossless archive verification')
    def test_archived_delivery_wav_compacted_losslessly_with_exact_restore(self):
        user1, rec1 = self.staged('first')
        wav = rec1 / 'audio.wav'
        with wave.open(str(wav), 'wb') as stream:
            stream.setnchannels(1)
            stream.setsampwidth(2)
            stream.setframerate(8000)
            stream.writeframes(bytes(1600))
        original = wav.read_bytes()
        install(self.root, 's', '01', user1, rec1)
        result = install(self.root, 's', '01', *self.staged('second'))
        backup_record = Path(result['previous_delivery']) / 'record'
        self.assertFalse((backup_record / 'audio.wav').exists())
        self.assertTrue((backup_record / 'audio.flac').is_file())
        self.assertTrue((backup_record / 'storage-compaction.json').is_file())
        life.restore_file(backup_record / 'audio.flac')
        self.assertEqual((backup_record / 'audio.wav').read_bytes(), original)

    def test_third_delivery_prunes_oldest_archive_keeping_latest_one_rollback(self):
        install(self.root, 's', '01', *self.staged('first'))
        r2 = install(self.root, 's', '01', *self.staged('second'))
        first_backup = Path(r2['previous_delivery'])
        self.assertTrue(first_backup.is_dir())
        r3 = install(self.root, 's', '01', *self.staged('third'))
        second_backup = Path(r3['previous_delivery'])
        self.assertTrue(second_backup.is_dir())
        self.assertFalse(first_backup.exists())
        self.assertEqual((second_backup / 'publish/video.mp4').read_bytes(), b'second')
        self.assertEqual(len(list(locations(self.root, 's', '01')['archive'].iterdir())), 1)
