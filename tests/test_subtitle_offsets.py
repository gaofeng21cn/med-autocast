import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))

import pysubs2

from build_episode_video import (
    Canvas,
    build_ass_filter,
    build_subtitle_ass,
    build_subtitle_video,
    ffmpeg_supports_ass,
    parse_srt,
)
from qa_series_videos import parse_srt as qa_parse_srt
from workbench_config import resolve_font


class SubtitleOffsetsTests(unittest.TestCase):
    def render_ass(self, offsets=None, annotations=None, cues=None, canvas=Canvas()):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            ass_path = root / 'subtitles.ass'
            subs = build_subtitle_ass(
                cues or [(0.0, 1.0, 'first'), (1.0, 2.0, 'second')],
                root / 'font.ttc',
                2.0,
                ass_path,
                annotations=annotations,
                canvas=canvas,
                cue_offsets=offsets,
            )
            self.assertTrue(ass_path.is_file())
            reloaded = pysubs2.load(str(ass_path), encoding='utf-8')
            return subs, reloaded

    def test_existing_plans_keep_bottom_position(self):
        _, subs = self.render_ass()
        self.assertEqual(len(subs.events), 2)
        self.assertEqual(subs.styles['Default'].alignment, pysubs2.Alignment.BOTTOM_CENTER)
        self.assertEqual(subs.styles['Default'].marginv, 16)
        self.assertEqual([e.plaintext for e in subs.events], ['first', 'second'])
        self.assertFalse(any('\\pos(' in e.text for e in subs.events))

    def test_only_selected_cue_moves_without_changing_text(self):
        _, subs = self.render_ass({'2': '+0+72'})
        self.assertEqual([e.plaintext for e in subs.events], ['first', 'second'])
        self.assertNotIn('\\pos(', subs.events[0].text)
        self.assertIn('\\an2\\pos(304,280)', subs.events[1].text)

    def test_invalid_reference_or_position_is_rejected(self):
        for offsets in [{0: '+0+72'}, {3: '+0+72'}, {'1.5': '+0+72'}, {1: '72'}, {1: '+0+72', '1': '+0+72'}]:
            with self.subTest(offsets=offsets), self.assertRaises(ValueError):
                self.render_ass(offsets)

    def test_parse_srt_uses_pysubs2_consistently_across_builder_and_qa(self):
        with tempfile.TemporaryDirectory() as directory:
            srt = Path(directory) / 'ep.srt'
            srt.write_text(
                '\ufeff1\n00:00:00,250 --> 00:00:01,750\n第一行中文\n第二行术语HbA1c\n\n'
                '2\n00:00:02,000 --> 00:00:03,500\n稳步控制血糖\n',
                encoding='utf-8',
            )
            tuples = parse_srt(srt)
            self.assertEqual(
                tuples,
                [
                    (0.25, 1.75, '第一行中文\n第二行术语HbA1c'),
                    (2.0, 3.5, '稳步控制血糖'),
                ],
            )
            qa_cues = qa_parse_srt(srt)
            self.assertEqual(
                qa_cues,
                [
                    {'start': 0.25, 'end': 1.75, 'lines': ['第一行中文', '第二行术语HbA1c']},
                    {'start': 2.0, 'end': 3.5, 'lines': ['稳步控制血糖']},
                ],
            )

    def test_build_subtitle_video_invokes_single_libass_ffmpeg_pass_when_available(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            font_path = root / 'NotoSansCJK.ttc'
            font_path.write_bytes(b'')
            with patch('build_episode_video.ffmpeg_supports_ass', return_value=True), \
                 patch('build_episode_video.run') as mock_run:
                cues = build_subtitle_video(
                    [(0.0, 1.0, '血糖管理'), (1.0, 2.0, '餐后散步')],
                    font_path,
                    2.0,
                    root,
                    root / 'subtitles.mov',
                    annotations=[{'start': 0.2, 'end': 1.2, 'text': '重点提示'}],
                    cue_offsets={'2': '+0+72'},
                )
            self.assertEqual(len(cues), 2)
            self.assertEqual(mock_run.call_count, 1)
            cmd = mock_run.call_args.args[0]
            self.assertEqual(cmd[0], 'ffmpeg')
            vf = cmd[cmd.index('-vf') + 1]
            self.assertIn('ass=filename=', vf)
            self.assertIn('fontsdir=', vf)
            self.assertIn(build_ass_filter(root / 'subtitles.ass', font_path), vf)
            reloaded = pysubs2.load(str(root / 'subtitles.ass'), encoding='utf-8')
            self.assertEqual(len(reloaded.events), 3)
            self.assertEqual(reloaded.events[2].style, 'Annotation')

    @unittest.skipUnless(shutil.which('ffmpeg'), 'requires ffmpeg for real subtitle render smoke')
    def test_real_cjk_subtitle_render_smoke(self):
        try:
            font = resolve_font()
        except ValueError:
            self.skipTest('no CJK font available on host')
        try:
            from PIL import Image
        except ImportError:
            self.skipTest('requires Pillow for pixel verification')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / 'subtitles.mov'
            cues = [(0.0, 1.0, '医学科普中文测试\n血糖监测')]
            build_subtitle_video(cues, font, 1.0, root, target, canvas=Canvas(608, 352))
            self.assertTrue((root / 'subtitles.ass').is_file())
            self.assertTrue(target.is_file())
            frame = root / 'frame.png'
            subprocess.run(
                ['ffmpeg', '-v', 'error', '-y', '-ss', '0.5', '-i', str(target), '-frames:v', '1', str(frame)],
                check=True,
            )
            with Image.open(frame) as img:
                rgba = img.convert('RGBA')
                alpha_min, alpha_max = rgba.getchannel('A').getextrema()
                self.assertEqual(alpha_max, 255)
                # Verify rendered CJK pixels occupy the lower subtitle band when libass/Pillow draws them.
                lower = rgba.crop((0, 260, 608, 352))
                non_transparent = sum(1 for a in lower.getchannel('A').tobytes() if a > 0)
                self.assertGreater(non_transparent, 100, f'libass={ffmpeg_supports_ass()}')


if __name__ == '__main__':
    unittest.main()
