"""An old internally-consistent movie must not hide changed production source."""
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from audit_audio_freshness import build_current, project_report
from unittest.mock import patch


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class FreshBuildTests(unittest.TestCase):
    def project(self, root):
        p = root / 'project'
        for directory in ('src', 'scripts', 'dist', 'out', 'audio'):
            (p / directory).mkdir(parents=True)
        for name, content in {'src/main.ts': 'drawOriginal()', 'dist/film.js': 'old bundle',
                              'score.json': '{}', 'audio.wav': 'mix',
                              'audio/narration-normalized.wav': 'voice', 'out/movie.mp4': 'movie'}.items():
            (p / name).write_text(content)
        (p / 'project.json').write_text('{}')
        (p / 'dist/build-receipt.json').write_text(json.dumps({
            'inputs': {f: digest(p / f) for f in ('src/main.ts', 'score.json')},
            'bundle_sha256': digest(p / 'dist/film.js')}))
        hashes = {'voice_sha256': digest(p / 'audio/narration-normalized.wav'),
                  'score_sha256': digest(p / 'score.json'), 'audio_sha256': digest(p / 'audio.wav')}
        for name in ('timing-receipt.json', 'mix-receipt.json'):
            (p / 'audio' / name).write_text(json.dumps(hashes))
        (p / 'out/current.json').write_text(json.dumps({**hashes, 'status': 'rendered',
            'path': str(p / 'out/movie.mp4'), 'sha256': digest(p / 'out/movie.mp4'),
            'bundle_sha256': digest(p / 'dist/film.js')}))
        return p

    def test_changed_source_invalidates_matching_old_movie_bundle(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            p = self.project(root)
            with patch('audit_audio_freshness.locations', return_value={'user': p / 'out'}):
                before = project_report(root, 's', 'e', {'project': 'project'})
                self.assertTrue(before['bindings']['render_current'])
                (p / 'src/main.ts').write_text('drawRepaired()')
                after = project_report(root, 's', 'e', {'project': 'project'})
            self.assertFalse(after['bindings']['render_current'])
            self.assertFalse(after['bindings']['build_inputs_current'])
            self.assertIn('build_inputs_stale_or_missing', after['issues'])

    def test_deleted_added_source_and_corrupt_receipt_are_diagnostics(self):
        for mutation in ('delete', 'add', 'corrupt'):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as folder:
                p = self.project(Path(folder))
                if mutation == 'delete':
                    (p / 'src/main.ts').unlink()
                elif mutation == 'add':
                    (p / 'src/second.ts').write_text('drawNew()')
                else:
                    (p / 'dist/build-receipt.json').write_text('{')
                ok, diagnostic = build_current(p)
                self.assertFalse(ok)
                self.assertTrue(diagnostic)


if __name__ == '__main__':
    unittest.main()
