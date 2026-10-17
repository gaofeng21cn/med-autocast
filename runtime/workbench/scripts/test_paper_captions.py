#!/usr/bin/env python3
"""Caption loss/retime regressions; synthetic fixtures are not listening proof."""

import argparse
import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import paper_project as pp
from audit_paper_captions import project_report
from paper_captions import caption_audit, caption_text, complete_caption_proposal


class CaptionRepairTests(unittest.TestCase):
    def test_missing_final_clause_is_restored(self):
        beats = [{'id': 'B01', 'start': .32, 'end': 8., 'text': '检查血常规；就诊时说明正在用的药，别继续硬扛。'}]
        old = [{'start': 5., 'end': 8., 'text': '检查血常规'}]
        cues, report = complete_caption_proposal(beats, old, preserve_timing=True)
        self.assertEqual(caption_text(''.join(c['text'] for c in cues)), caption_text(beats[0]['text']))
        self.assertTrue(report['complete_text_check']['text_complete'])
        self.assertEqual(cues[0]['start'], .32)
        self.assertEqual(cues[-1]['end'], 8.)
        self.assertEqual(report['changes'][0]['action'], 'rebuilt_missing_text')

    def test_numeric_punctuation_is_semantically_preserved(self):
        self.assertNotEqual(caption_text('每日服用 1.5 毫克。'), caption_text('每日服用 15 毫克。'))
        self.assertNotEqual(caption_text('每日服用 .5 毫克。'), caption_text('每日服用 5 毫克。'))
        self.assertNotEqual(caption_text('变化 -.5。'), caption_text('变化 -5。'))
        self.assertNotEqual(caption_text('等待 1-2 周。'), caption_text('等待 12 周。'))
        beats = [{'id': 'B01', 'start': .3, 'end': 5., 'text': '每日服用 1.5 毫克。'}]
        old = [{'start': .4, 'end': 4.9, 'text': '每日服用 15 毫克。'}]
        cues, report = complete_caption_proposal(beats, old)
        self.assertEqual(caption_text(cues[0]['text']), caption_text(beats[0]['text']))
        self.assertEqual(report['changes'][0]['action'], 'rebuilt_missing_text')

    def test_rebuilt_caption_preserves_english_and_numeric_spaces(self):
        beats = [{'id': 'B01', 'start': .3, 'end': 5., 'text': '检查 A B、记录 1 2。'}]
        old = [{'start': .4, 'end': 4.9, 'text': '检查 AB、记录 12。'}]
        self.assertFalse(caption_audit(beats, old)['text_complete'])
        cues, report = complete_caption_proposal(beats, old)
        self.assertIn('A B', ''.join(c['text'] for c in cues))
        self.assertIn('1 2', ''.join(c['text'] for c in cues))
        self.assertTrue(report['complete_text_check']['text_complete'])
        abbreviation = [{'id': 'B01', 'start': .3, 'end': 5., 'text': 'U.S. adults'}]
        abbreviation_cues, abbreviation_report = complete_caption_proposal(abbreviation, [])
        self.assertEqual(abbreviation_cues[0]['text'], 'U.S. adults')
        self.assertTrue(abbreviation_report['complete_text_check']['text_complete'])
        self.assertNotEqual(caption_text('U.S. adults'), caption_text('USadults'))

    def test_english_word_boundary_between_cues_is_not_a_missing_word(self):
        beats = [{'id': 'B01', 'start': .3, 'end': 8., 'text': 'Take 1 mg daily.'}]
        cues = [{'start': .4, 'end': 3., 'text': 'Take 1'},
                {'start': 3., 'end': 7.8, 'text': 'mg daily.'}]
        self.assertTrue(caption_audit(beats, cues)['text_complete'])
        proposed, report = complete_caption_proposal(beats, cues, preserve_timing=True)
        self.assertEqual([q['text'] for q in proposed], [q['text'] for q in cues])
        self.assertEqual(report['changes'][0]['action'], 'preserved_complete_current_timing')
        damaged = [{'start': .4, 'end': 7.8, 'text': 'Take 1mg daily.'}]
        self.assertFalse(caption_audit(beats, damaged)['text_complete'])
        long_beats = [{'id': 'B01', 'start': .3, 'end': 8.,
                       'text': 'Take 1 mg daily for stable results.'}]
        rebuilt, rebuilt_report = complete_caption_proposal(long_beats, [])
        self.assertGreater(len(rebuilt), 1)
        self.assertTrue(rebuilt_report['complete_text_check']['text_complete'])

    def test_caption_audit_records_partial_beat_boundary(self):
        beats = [{'id': 'B01', 'start': .3, 'end': 8., 'text': '第一段正文。'}]
        cues = [{'start': 0., 'end': 8.2, 'text': '第一段正文。'}]
        report = caption_audit(beats, cues)
        self.assertIn('caption_crosses_own_narration_boundary', report['beats'][0]['issues'])

    def test_midpoint_in_wrong_shot_does_not_change_text_owner(self):
        beats = [
            {'id': 'B01', 'start': .3, 'end': 5., 'text': '第一段的事实。'},
            {'id': 'B02', 'start': 5., 'end': 10., 'text': '第二段的行动。'},
        ]
        old = [{'start': 7., 'end': 9., 'text': '第一段的事实。'}, {'start': 9., 'end': 10., 'text': '第二段的行动。'}]
        cues, report = complete_caption_proposal(beats, old)
        self.assertEqual([c['beat_id'] for c in cues], ['B01', 'B02'])
        self.assertEqual(cues[0]['start'], .3)
        self.assertEqual(cues[0]['end'], 5.)
        self.assertTrue(report['complete_text_check']['text_complete'])

    def test_complete_editorial_breaks_use_real_prior_voice_window(self):
        beats = [{'id': 'B01', 'start': .65, 'end': 10.65, 'text': '第一句。第二句。'}]
        old = [{'start': .65, 'end': 4.65, 'text': '第一句。'}, {'start': 4.65, 'end': 8.65, 'text': '第二句。'}]
        cues, _ = complete_caption_proposal(beats, old, prior_beats={'B01': {'text': beats[0]['text'], 'start': .65, 'end': 8.65}})
        self.assertEqual(cues[0]['start'], .65)
        self.assertEqual(cues[-1]['end'], 10.65)
        self.assertEqual([q['text'] for q in cues], [q['text'] for q in old])

    def test_exact_editorial_timing_can_be_kept(self):
        beats = [{'id': 'B01', 'start': .3, 'end': 8., 'text': '完整正文。'}]
        old = [{'start': .5, 'end': 7.5, 'text': '完整正文。', 'editorial_note': 'heard'}]
        cues, _ = complete_caption_proposal(beats, old, preserve_timing=True)
        self.assertEqual(cues, [{**old[0], 'beat_id': 'B01'}])

    def test_preserved_timing_corrects_stale_beat_identity(self):
        beats = [
            {'id': 'B01', 'start': 0., 'end': 5., 'text': '第一段。'},
            {'id': 'B02', 'start': 5., 'end': 10., 'text': '第二段。'},
        ]
        old = [
            {'start': .3, 'end': 4.7, 'text': '第一段。', 'beat_id': 'B02'},
            {'start': 5.3, 'end': 9.7, 'text': '第二段。', 'beat_id': 'B01'},
        ]
        cues, _ = complete_caption_proposal(beats, old, preserve_timing=True)
        self.assertEqual([q['beat_id'] for q in cues], ['B01', 'B02'])
        self.assertEqual([(q['start'], q['end']) for q in cues], [(q['start'], q['end']) for q in old])

    def test_missing_approved_audio_beat_cannot_claim_full_caption_coverage(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary)
            (p / 'voice.wav').write_bytes(b'voice')
            pp.save(p / 'project.json', {'schema': 'paper_project/v1', 'score': 'score.json', 'voice': 'voice.wav',
                                       'narration': 'narration.json', 'beat_shots': {'B01': 's1'}})
            pp.save(p / 'narration.json', {'beats': [
                {'id': 'B01', 'text': '第一段正文。'}, {'id': 'B02', 'text': '第二段正文。'}]})
            pp.save(p / 'audio/narration_beats.json', {'duration': 8.7, 'beats': [
                {'id': 'B01', 'text': '第一段正文。', 'start': .3, 'end': 8.}]})
            pp.save(p / 'score.json', {'duration': 8.7, 'shots': [
                {'id': 's1', 'start': 0., 'end': 8.7, 'events': {}}],
                'cues': [{'start': .3, 'end': 8., 'text': '第一段正文。'}]})
            report = project_report(p, 'series', 'episode', {'project': '.'})
            self.assertEqual(report['status'], 'audio_regeneration_required')
            self.assertFalse(report['current_audit']['text_complete'])
            self.assertFalse(report['repair']['complete_text_check']['text_complete'])
            self.assertFalse(report['proposal']['text_complete'])
            self.assertEqual(report['proposal']['source_beats_without_audio'], ['B02'])
            result = pp.retime(argparse.Namespace(project=p, workspace=p, reference_score=None))
            self.assertFalse(result['caption_text_complete'])
            self.assertEqual(result['source_beats_without_audio'], ['B02'])
            self.assertEqual({c['beat_id'] for c in pp.read(p / 'score.json')['cues']}, {'B01'})
            self.assertEqual(pp.read(p / 'audio/timing-receipt.json')['source_beats_without_audio'], ['B02'])

    def test_audit_does_not_preserve_timing_from_another_voice(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary)
            (p / 'voice.wav').write_bytes(b'current-voice')
            pp.save(p / 'project.json', {'score': 'score.json', 'voice': 'voice.wav', 'narration': 'narration.json'})
            pp.save(p / 'narration.json', {'beats': [{'id': 'B01', 'text': '第一段正文。'}]})
            pp.save(p / 'audio/narration_beats.json', {'duration': 8.7, 'beats': [
                {'id': 'B01', 'text': '第一段正文。', 'start': .3, 'end': 8.}]})
            pp.save(p / 'score.json', {'duration': 8.7, 'cues': [
                {'start': .6, 'end': 7.5, 'text': '第一段正文。'}]})
            pp.save(p / 'audio/timing-receipt.json', {'voice_sha256': 'stale', 'caption_status': 'editorial_timing'})
            report = project_report(p, 'series', 'episode', {'project': '.'})
            self.assertEqual(report['repair']['changes'][0]['action'], 'remapped_complete_editorial_breaks')
            self.assertEqual(report['proposal']['cues'][0]['start'], .3)
            pp.save(p / 'audio/timing-receipt.json', {'voice_sha256': pp.sha(p / 'voice.wav'),
                                                    'caption_status': 'editorial_timing'})
            current = project_report(p, 'series', 'episode', {'project': '.'})
            self.assertEqual(current['repair']['changes'][0]['action'], 'preserved_complete_current_timing')
            self.assertEqual(current['proposal']['cues'][0]['start'], .6)

    def test_retime_twice_is_idempotent_and_repairs_incomplete_same_voice(self):
        with tempfile.TemporaryDirectory() as temporary:
            p = Path(temporary)
            (p / 'voice.wav').write_bytes(b'voice')
            pp.save(p / 'project.json', {'schema': 'paper_project/v1', 'score': 'score.json', 'voice': 'voice.wav',
                                       'narration': 'narration.json', 'beat_shots': {'B01': 's1'}})
            pp.save(p / 'narration.json', {'beats': [{'id': 'B01', 'text': '第一句。第二句。'}]})
            pp.save(p / 'audio/narration_beats.json', {'duration': 12., 'beats': [
                {'id': 'B01', 'text': '第一句。第二句。', 'start': .32, 'end': 11.3}]})
            pp.save(p / 'score.json', {'duration': 12., 'shots': [{'id': 's1', 'start': 0., 'end': 12., 'events': {'contact': 2.}}],
                                      'cues': [{'start': 8., 'end': 11.3, 'text': '第一句。'}]})
            pp.save(p / 'audio/timing-receipt.json', {'voice_sha256': pp.sha(p / 'voice.wav'), 'caption_status': 'draft'})
            args = argparse.Namespace(project=p, workspace=p, reference_score=None)
            pp.retime(args)
            first = pp.read(p / 'score.json')
            self.assertTrue(caption_audit(pp.read(p / 'audio/narration_beats.json')['beats'], first['cues'])['text_complete'])
            self.assertEqual(first['shots'][0]['events'], {'contact': 2.})
            pp.retime(args)
            self.assertEqual(pp.read(p / 'score.json')['cues'], first['cues'])

    def test_timing_audit_reports_overlaps_and_late_opening_without_asr_claim(self):
        beats = [{'id': 'B01', 'start': .3, 'end': 8., 'text': '第一句。第二句。'}]
        cues = [{'start': 3., 'end': 5., 'text': '第一句。'}, {'start': 4., 'end': 7., 'text': '第二句。'}]
        report = caption_audit(beats, cues, 8.)
        self.assertTrue(report['text_complete'])
        self.assertIn('opening_caption_late_review_window', report['beats'][0]['issues'])
        self.assertEqual(report['timeline_issues'][0]['code'], 'overlap_or_out_of_order')
        self.assertFalse(report['audio_recognition_performed'])


if __name__ == '__main__':
    unittest.main()
