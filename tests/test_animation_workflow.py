"""Regression checks for asset admission and explicit narration baselines."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
from check_animation_assets import check_assets
from render_edge_tts import synthesize, scene_intervals
from audio_baseline import inspect_audio
import render_javascript_animation


class AnimationWorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for name in ['anatomy.png', 'facts.yaml', 'prompt.txt', 'generation.json']:
            (self.root / name).write_text('fixture only')
        self.asset = {'asset_id': 'pituitary', 'path': 'anatomy.png', 'source_type': 'imagegen',
            'medical': True, 'medical_reference': 'facts.yaml', 'visual_meaning': 'location',
            'must_not_imply': 'diagnostic image', 'prompt_ref': 'prompt.txt',
            'generation_receipt': 'generation.json', 'status': 'approved_direct_use',
            'visual_review': {'status': 'passed', 'evidence_ref': 'review.json'},
            'medical_review': {'status': 'passed', 'evidence_ref': 'review.json'}}
        (self.root / 'review.json').write_text(json.dumps({'asset_id': 'pituitary',
            'asset_ref': 'anatomy.png', 'visual_review': 'passed', 'medical_review': 'passed',
            'reviewer': 'test fixture', 'notes': 'fixture, not actual medical approval'}))

    def check(self, ids=None):
        path = self.root / 'assets.json'
        path.write_text(json.dumps({'schema': 'medical_animation_assets/v1', 'assets': [self.asset],
            'shots': [{'shot_id': 'B01', 'asset_ids': ids or ['pituitary']}]}))
        return check_assets(path)

    def test_complete_declared_references_do_not_mint_medical_approval(self):
        report = self.check()
        self.assertEqual(report['status'], 'passed')
        self.assertFalse(report['domain_quality_approved'])

    def test_pending_and_rejected_assets_block(self):
        self.asset['status'] = 'pending_review'
        self.assertEqual(self.check()['status'], 'blocked')
        self.asset['status'] = 'rejected'
        with self.assertRaisesRegex(ValueError, 'rejected'): self.check()

    def test_candidate_allows_pending_but_never_rejected(self):
        self.asset['status'] = 'pending_review'
        self.check()
        args = ['renderer', '--project-root', str(self.root), '--asset-manifest', 'assets.json',
                '--check-only', '--review-candidate']
        with patch.object(sys, 'argv', args), patch('shutil.which', return_value='/fixture/tool'):
            render_javascript_animation.main()
        self.asset['status'] = 'rejected'
        with self.assertRaises(ValueError): self.check()
        with patch.object(sys, 'argv', args), patch('shutil.which', return_value='/fixture/tool'):
            with self.assertRaisesRegex(SystemExit, 'rejected'):
                render_javascript_animation.main()

    def test_default_renderer_still_blocks_pending(self):
        self.asset['status'] = 'pending_review'
        self.check()
        args = ['renderer', '--project-root', str(self.root), '--asset-manifest', 'assets.json', '--check-only']
        with patch.object(sys, 'argv', args), patch('shutil.which', return_value='/fixture/tool'):
            with self.assertRaises(SystemExit): render_javascript_animation.main()

    def test_missing_generation_provenance_blocks(self):
        (self.root / 'generation.json').unlink()
        with self.assertRaisesRegex(ValueError, 'Missing'): self.check()

    def test_unknown_shot_asset_blocks(self):
        with self.assertRaisesRegex(ValueError, 'unknown'): self.check(['unregistered'])

    def test_review_for_different_asset_blocks(self):
        data = json.loads((self.root / 'review.json').read_text())
        data['asset_id'] = 'different'
        (self.root / 'review.json').write_text(json.dumps(data))
        with self.assertRaisesRegex(ValueError, 'does not match'): self.check()

    def test_edge_uses_one_context_and_explicit_parameters(self):
        calls = []
        class Communicate:
            def __init__(self, text, voice, **kwargs): calls.append((text, voice, kwargs))
            async def stream(self):
                yield {'type': 'audio', 'data': b'fixture'}
                yield {'type': 'SentenceBoundary', 'text': 'sentence', 'offset': 0, 'duration': 10_000_000}
        with patch.dict(sys.modules, edge_tts=types.SimpleNamespace(Communicate=Communicate)):
            boundaries = asyncio.run(synthesize('first. second.', 'voice', self.root / 'audio.mp3', '-8%', '+0Hz', '+0%'))
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0][2]['rate'], '-8%')
        self.assertEqual(calls[0][2]['pitch'], '+0Hz')
        self.assertEqual(boundaries[0]['end'], 1)

    def test_loudness_outlier_never_approves_tone(self):
        levels = iter([-16, -9, -16])
        def measured(*args): return {'input_i': next(levels), 'input_tp': -1, 'input_lra': 3}
        with patch('audio_baseline.subprocess.check_output', return_value='{"format":{"duration":"10"}}'), patch('audio_baseline.measure', measured):
            report = inspect_audio(self.root / 'audio.wav', [{'id': 'a', 'start': 0, 'end': 4}, {'id': 'b', 'start': 5, 'end': 10}])
        self.assertEqual(report['tone_consistency'], 'pending')
        self.assertEqual(report['full_listening'], 'pending')
        self.assertEqual(report['acoustic_status'], 'needs_audio_review')

    def test_unreviewed_boundaries_can_measure_but_not_align_subtitles(self):
        rows = scene_intervals('one.\ntwo.three.', [
            {'text': 'one.', 'start': .1, 'end': 2.1},
            {'text': 'two.', 'start': 2, 'end': 3},
            {'text': 'three.', 'start': 3, 'end': 5}], 5.1)
        self.assertEqual(rows, [{'id': 'B01', 'start': .1, 'end': 2}, {'id': 'B02', 'start': 2, 'end': 5.1}])
        with self.assertRaisesRegex(ValueError, 'does not match'):
            scene_intervals('missing.', [{'text': 'other.', 'start': 0, 'end': 1}], 1)


if __name__ == '__main__': unittest.main()
