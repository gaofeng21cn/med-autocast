#!/usr/bin/env python3
"""Focused tests for local multi-anchor narration lineage matching."""
import sys
import unittest

import numpy as np

sys.path.insert(0, str(__file__).rsplit("/", 1)[0])
from audit_narration_lineage import (  # noqa: E402
    RATE,
    build_anchors,
    locate_multianchor,
)


def segment(seed, seconds=.42):
    rng = np.random.default_rng(seed)
    return rng.normal(0, .25, round(RATE * seconds)).astype(np.float32)


class LocalMultiAnchorTests(unittest.TestCase):
    def test_expected_window_wins_over_repeated_phrase_elsewhere(self):
        # The complete source is repeated at 1s and 5s. A global search would
        # commonly return the first occurrence; the beat expects the latter.
        source = np.concatenate([segment(1), segment(2), segment(3)])
        target = np.zeros(RATE * 8, dtype=np.float32)
        for start in (RATE, RATE * 5):
            target[start:start + len(source)] = source
        anchors = [
            {"label": "head", "offset": 0.0, "samples": source[:round(.42 * RATE)]},
            {"label": "middle", "offset": .42, "samples": source[round(.42 * RATE):round(.84 * RATE)]},
            {"label": "tail", "offset": .84, "samples": source[round(.84 * RATE):]},
        ]
        result = locate_multianchor(target, anchors, expected_zero=5.0, radius_seconds=.5)
        self.assertIsNotNone(result)
        self.assertAlmostEqual(result["origin"], 5.0, delta=1 / RATE)
        self.assertGreater(result["score"], .99)

    def test_one_matching_anchor_does_not_hide_wrong_tail(self):
        source = np.concatenate([segment(11), segment(12), segment(13)])
        target = np.zeros(RATE * 4, dtype=np.float32)
        expected = RATE
        target[expected:expected + round(.42 * RATE)] = source[:round(.42 * RATE)]
        # A different tail is present at the expected location. The matcher
        # must not call this a complete preserved source segment.
        target[expected + round(.42 * RATE):expected + len(source)] = np.concatenate(
            [segment(21), segment(22)])
        anchors = build_anchors(source, 0.0)
        result = locate_multianchor(target, anchors, expected_zero=1.0, radius_seconds=.2)
        self.assertIsNotNone(result)
        self.assertLess(result["score"], .8)

    def test_missing_head_does_not_pass_when_middle_and_tail_survive(self):
        source = np.concatenate([segment(41), segment(42), segment(43)])
        target = np.zeros(RATE * 4, dtype=np.float32)
        expected = RATE
        # Simulate the first 0.42 s being removed while the rest is preserved.
        target[expected:expected + len(source) - round(.42 * RATE)] = source[round(.42 * RATE):]
        anchors = build_anchors(source, 0.0)
        result = locate_multianchor(target, anchors, expected_zero=1.0, radius_seconds=.2)
        # Refusing to locate an incomplete source is also a correct result.
        self.assertTrue(result is None or result["score"] < .8)

    def test_anchor_builder_keeps_head_middle_tail_offsets(self):
        source = np.zeros(RATE * 3, dtype=np.float32)
        source[RATE // 4:] = segment(31, 2.75)
        anchors = build_anchors(source, .25)
        self.assertGreaterEqual(len(anchors), 2)
        self.assertEqual([a["label"] for a in anchors], ["head", "middle", "tail"])
        self.assertLess(anchors[0]["offset"], anchors[-1]["offset"])

    def test_music_during_source_pauses_does_not_create_false_loss(self):
        source = np.zeros(RATE * 10, dtype=np.float32)
        for at, seed in ((.3, 51), (3.0, 52), (7.0, 53)):
            start = round(at * RATE)
            source[start:start + RATE] = segment(seed, 1.0)
        target = np.zeros(RATE * 12, dtype=np.float32)
        target[RATE:RATE + len(source)] = source
        # Continuous low music is louder than the long silent pauses, but
        # much quieter than actual speech. It must not look like a cut take.
        target += segment(99, 12.0) * .025
        anchors = build_anchors(source, .3)
        self.assertTrue(all(np.sqrt(np.mean(a["samples"] ** 2)) > .005 for a in anchors))
        result = locate_multianchor(target, anchors, 1.0, radius_seconds=.2)
        self.assertGreater(result["score"], .98)
        self.assertAlmostEqual(result["origin"], 1.0, delta=1 / RATE)


if __name__ == "__main__":
    unittest.main()
