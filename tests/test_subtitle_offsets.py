import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts'))
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from build_episode_video import build_subtitle_video


class SubtitleOffsetsTests(unittest.TestCase):
    def render_calls(self, offsets=None):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch('build_episode_video.run'), patch('build_episode_video.make_text_overlay') as raster:
                build_subtitle_video([(0, 1, 'first'), (1, 2, 'second')], root / 'font', 2,
                                     root, root / 'video.mov', cue_offsets=offsets)
                return raster.call_args_list

    def test_existing_plans_keep_bottom_position(self):
        self.assertEqual([c.args[5] for c in self.render_calls()], ['+0+16', '+0+16'])

    def test_only_selected_cue_moves_without_changing_text(self):
        calls = self.render_calls({'2': '+0+72'})
        self.assertEqual([(c.args[0], c.args[5]) for c in calls],
                         [('first', '+0+16'), ('second', '+0+72')])

    def test_invalid_reference_or_position_is_rejected(self):
        for offsets in [{0: '+0+72'}, {3: '+0+72'}, {'1.5': '+0+72'}, {1: '72'}, {1: '+0+72', '1': '+0+72'}]:
            with self.subTest(offsets=offsets), self.assertRaises(ValueError):
                self.render_calls(offsets)


if __name__ == '__main__':
    unittest.main()
