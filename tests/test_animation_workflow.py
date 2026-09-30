"""Regression checks for asset admission and explicit narration baselines."""
import asyncio
from contextlib import redirect_stdout
import io
import json
from pathlib import Path
import sys
import subprocess
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

    def test_pending_candidate_carries_review_debt_and_rejected_asset_returns_diagnostic(self):
        self.asset['status'] = 'pending_review'
        self.check()
        args = ['renderer', '--project-root', str(self.root), '--asset-manifest', 'assets.json',
                '--check-only', '--review-candidate']
        output = io.StringIO()
        with patch.object(sys, 'argv', args), patch('shutil.which', return_value='/fixture/tool'), redirect_stdout(output):
            render_javascript_animation.main()
        self.assertEqual(json.loads(output.getvalue())['status'], 'blocked')
        self.asset['status'] = 'rejected'
        path = self.root / 'assets.json'
        data = json.loads(path.read_text())
        data['assets'][0] = self.asset
        path.write_text(json.dumps(data))
        preview = self.root / 'preview'
        args = ['renderer', '--project-root', str(self.root), '--asset-manifest', 'assets.json',
                '--preview', '--preview-output', str(preview), '--review-candidate']
        output = io.StringIO()
        with patch.object(sys, 'argv', args), patch('shutil.which', return_value='/fixture/tool'), redirect_stdout(output):
            render_javascript_animation.main()
        report = json.loads((preview / 'preview.json').read_text())
        self.assertEqual(report['status'], 'not_rendered_with_quality_debt')
        self.assertFalse(report['output_created'])
        self.assertFalse(report['release_eligible'])
        self.assertTrue(any(item['code'] == 'asset_admission_unresolved' for item in report['quality_debt']))
        self.assertIn('rejected', report['quality_debt'][0]['detail'])

    def test_default_renderer_materializes_diagnostic_for_pending_assets(self):
        self.asset['status'] = 'pending_review'
        self.check()
        output_path = self.root / 'out' / 'candidate.mp4'
        args = ['renderer', '--project-root', str(self.root), '--asset-manifest', 'assets.json', '--output', str(output_path)]
        with patch.object(sys, 'argv', args), patch('shutil.which', return_value='/fixture/tool'), redirect_stdout(io.StringIO()):
            render_javascript_animation.main()
        report = json.loads(output_path.with_suffix('.receipt.json').read_text())
        self.assertEqual(report['status'], 'not_rendered_with_quality_debt')
        self.assertFalse(output_path.exists())
        self.assertFalse(report['release_eligible'])

    def test_pending_assets_are_top_level_render_quality_debt(self):
        self.asset['status'] = 'pending_review'
        admission = self.check()
        self.assertIn('asset_review_pending', {
            item['code'] for item in render_javascript_animation.asset_admission_quality_debt(admission)
        })

    def test_pending_review_render_receipt_preserves_quality_debt(self):
        self.asset['status'] = 'pending_review'
        self.check()
        audio = self.root / 'audio.wav'
        audio.write_bytes(b'fixture audio')
        output_path = self.root / 'out' / 'candidate.mp4'

        def render(command, cwd, capture_output=False):
            config = json.loads(Path(command[-1]).read_text())
            target = Path(config['output'])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b'fixture video')
            return subprocess.CompletedProcess(command, 0, stdout=json.dumps({
                'renderer_runtime': {'renderer_id': 'canvas2d', 'style_id': 'paper_collage'},
            }))

        args = ['renderer', '--project-root', str(self.root), '--asset-manifest', 'assets.json',
                '--output', str(output_path), '--audio', str(audio), '--review-candidate']
        with (
            patch.object(sys, 'argv', args),
            patch('shutil.which', return_value='/fixture/tool'),
            patch.object(render_javascript_animation, 'run', side_effect=render),
            patch.object(subprocess, 'run', return_value=subprocess.CompletedProcess(
                ['ffprobe'], 0,
                stdout='{"format":{"duration":"1"},"streams":[{"codec_type":"video"},{"codec_type":"audio"}]}',
            )),
            redirect_stdout(io.StringIO()),
        ):
            render_javascript_animation.main()
        receipt = json.loads(output_path.with_suffix('.receipt.json').read_text())
        self.assertEqual(receipt['status'], 'rendered')
        self.assertEqual({item['code'] for item in receipt['quality_debt']}, {'asset_review_pending'})
        self.assertFalse(receipt['release_eligible'])

    def test_failed_browser_preview_is_not_reported_as_previewed(self):
        self.check()
        preview = self.root / 'preview'

        def failed_preview(command, cwd, capture_output=False):
            preview.mkdir()
            (preview / 'preview.json').write_text(json.dumps({
                'status': 'failed', 'frames': [{'file': 'partial.png'}], 'errors': ['browser error'],
            }))
            raise SystemExit('browser error')

        args = ['renderer', '--project-root', str(self.root), '--asset-manifest', 'assets.json',
                '--preview', '--preview-output', str(preview), '--review-candidate']
        with (
            patch.object(sys, 'argv', args),
            patch('shutil.which', return_value='/fixture/tool'),
            patch.object(render_javascript_animation, 'run', side_effect=failed_preview),
            redirect_stdout(io.StringIO()),
        ):
            render_javascript_animation.main()
        report = json.loads((preview / 'preview.json').read_text())
        self.assertEqual(report['status'], 'preview_attempted_with_quality_debt')
        self.assertTrue(report['output_created'])
        self.assertTrue(any(item['code'] == 'animation_preview_failed' for item in report['quality_debt']))

    def test_renderer_selection_debt_does_not_block_a_candidate(self):
        report = render_javascript_animation.renderer_selection_report(
            'line_art', 'svg', {'renderer_id': 'canvas2d', 'requested_style_id': 'line_art'}
        )
        self.assertEqual(report['renderer_match'], False)
        self.assertIsNone(report['style_match'])
        self.assertEqual(
            {item['code'] for item in report['quality_debt']},
            {'style_realization_unreported', 'renderer_selection_mismatch'},
        )
        self.assertTrue(all(not item['blocks_stage_progress'] for item in report['quality_debt']))

    def test_renderer_report_never_reads_requested_style_as_runtime_realization(self):
        report = render_javascript_animation.renderer_selection_report(
            'paper_collage', 'canvas2d',
            {'renderer_id': 'canvas2d', 'requested_style_id': 'paper_collage'},
        )
        self.assertTrue(report['renderer_match'])
        self.assertFalse(report['style_realization_reported'])
        self.assertIsNone(report['style_match'])
        self.assertEqual(report['quality_debt'][0]['code'], 'style_realization_unreported')

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
