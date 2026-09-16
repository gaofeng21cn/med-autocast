import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
"""Focused checks for timing and readable offline review output."""
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from workbench_config import resolve_font

# Pillow, and therefore the timeline review helpers, ship in the optional
# `workbench` extra. Without it the module cannot import at all, which used to
# surface as an opaque loader error on every `scripts/verify.sh fast` run.
try:
    from PIL import ImageFont
    from build_timeline_review import checked_record, protect_outputs, sample_times, words, wrap
except ModuleNotFoundError as error:
    raise unittest.SkipTest(
        'timeline review checks need the optional workbench extra '
        f"(pip install -e '.[workbench]'): {error}",
    ) from error


class TimelineReviewTests(unittest.TestCase):
    def test_chinese_wrapping_preserves_text(self):
        font = ImageFont.load_default(size=18)
        text = '血压高不等于并发症已经发生，按计划测量并复诊。' * 6
        lines = wrap(text + '\n保留原换行', font, 240)
        self.assertEqual(''.join(lines), text + '保留原换行')
        self.assertEqual(lines[-1], '保留原换行')
        self.assertTrue(all(font.getlength(line) <= 240 for line in lines))

    def test_video_tail_uses_video_duration_and_fps(self):
        meta = {'streams': [{'codec_type': 'video', 'duration': '1', 'avg_frame_rate': '30/1'}],
                'format': {'duration': '1.5'}}
        times = sample_times(.8, 1, 8, meta)
        self.assertAlmostEqual(times[-1], 29/30)
        for start, end in [(1, .8), (.8, 1.2), (-1, .5)]:
            with self.assertRaises(ValueError):
                sample_times(start, end, 8, meta)

    def test_beat_offset_and_episode_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            alignment, beats = [Path(directory)/name for name in ('asr.json', 'beats.json')]
            alignment.write_text(json.dumps({'episode_id': '04', 'beats': [{'id': 'B03', 'segments': [
                {'words': [{'start': 1.12, 'end': 1.3, 'word': '脑'}]}]}]}))
            beats.write_text(json.dumps({'episode_id': '04', 'beats': [{'id': 'B03', 'start': 20.93161}]}))
            self.assertAlmostEqual(words(alignment, beats)[0][0], 22.05161)
            beats.write_text(json.dumps({'episode_id': '05', 'beats': []}))
            with self.assertRaises(ValueError):
                words(alignment, beats)

    def test_record_needs_only_source_and_valid_timing(self):
        with tempfile.TemporaryDirectory() as directory:
            record = Path(directory)/'record.json'
            (Path(directory)/'text.srt').write_text('')
            data = {'srt_source': 'text.srt', 'segments': [{'start': 0, 'end': 2}]}
            record.write_text(json.dumps(data))
            self.assertEqual(checked_record(record, 3)[1].name, 'text.srt')
            with self.assertRaises(ValueError):
                checked_record(record, 1)
            data['segments'].append({'start': 2.5, 'end': 3})
            record.write_text(json.dumps(data))
            with self.assertRaises(ValueError):
                checked_record(record, 3)

    def test_outputs_do_not_replace_source_or_previous_images(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)/'source.png'
            args = SimpleNamespace(video=source, srt=None, alignment=None, beats=None,
                                   review_record=None, font=None)
            with self.assertRaises(ValueError):
                protect_outputs(args, [source])
            old = Path(directory)/'old.png'
            old.write_bytes(b'existing')
            with self.assertRaises(ValueError):
                protect_outputs(args, [old])
            self.assertEqual(old.read_bytes(), b'existing')


if __name__ == '__main__':
    unittest.main()
