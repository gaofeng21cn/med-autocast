#!/usr/bin/env python3
"""Regression tests for the narration splice fix.

The defect being guarded against is inaudible first syllables at segment
boundaries, so the assertions are about measured speech onsets and preserved
runtime, not about loudness or file size.
"""
import array
import math
import sys
import tempfile
import unittest
import wave
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from narration_splice import effective_gap_frames, join, leading_activity_frames, read_pcm, trim_bounds  # noqa: E402

RATE = 24000


def tone(seconds, frequency=220.0, amplitude=8000):
    count = int(RATE * seconds)
    return array.array("h", [int(amplitude * math.sin(2 * math.pi * frequency * i / RATE))
                              for i in range(count)])


def silence(seconds):
    return array.array("h", [0] * int(RATE * seconds))


def write_wav(path: Path, samples):
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(RATE)
        handle.writeframes(samples.tobytes())


def read_wav(path: Path):
    with wave.open(str(path)) as handle:
        samples = array.array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
        return samples, handle.getframerate()


def speech_start(samples, rate=RATE, ratio=0.08):
    window = int(rate * 0.01)
    peak = 0.0
    env = []
    for index in range(0, len(samples), window):
        chunk = samples[index:index + window]
        if not chunk:
            break
        value = math.sqrt(sum(x * x for x in chunk) / len(chunk))
        env.append(value)
        peak = max(peak, value)
    for index, value in enumerate(env):
        if value > peak * ratio:
            return index * 0.01
    return None


class SpliceTests(unittest.TestCase):
    def test_effective_gap_accounts_for_next_take_preroll(self):
        gap = round(RATE * 0.26)
        preroll = round(RATE * 0.11)
        self.assertEqual(effective_gap_frames(gap, preroll), gap - preroll)
        self.assertEqual(effective_gap_frames(gap, gap * 2), 0)

    def test_default_preserves_complete_source_including_quiet_attack(self):
        samples = silence(0.5) + tone(1.0)
        start, end = trim_bounds(samples, RATE)
        self.assertEqual((start, end), (0, len(samples)))
        quiet = tone(.4, amplitude=45) + tone(1.0)
        self.assertEqual(trim_bounds(quiet, RATE), (0, len(quiet)))

    def test_optional_trim_only_removes_near_digital_silence(self):
        samples = silence(.5) + tone(1)
        start, end = trim_bounds(samples, RATE, trim_silence=True)
        self.assertAlmostEqual(start / RATE, .38, delta=.01)
        self.assertEqual(end, len(samples))

    def test_join_places_every_segment_at_its_speech_onset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            takes = []
            # Different leading silence per take, mirroring real TTS output.
            for index, lead in enumerate([0.02, 0.44, 0.31]):
                path = root / f"take{index}.wav"
                write_wav(path, silence(lead) + tone(1.0, frequency=200 + index * 60))
                takes.append(path)
            out = root / "joined.wav"
            reports = join(takes, out)
            joined, rate = read_wav(out)
            for report in reports:
                offset = int(report["placed_at"] * rate)
                source, _ = read_wav(root / report["file"])
                placed = joined[offset:offset + len(source)]
                self.assertEqual(placed.tolist(), source.tolist())

    def test_join_nominal_gap_is_measured_at_spoken_onset(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = root / "first.wav"
            second = root / "second.wav"
            write_wav(first, tone(1.0, frequency=210))
            preroll = 0.14
            write_wav(second, silence(preroll) + tone(1.0, frequency=330))
            out = root / "joined.wav"
            rows = join([first, second], out, gap_ms=260, lead_ms=0, tail_ms=0)
            joined, rate = read_wav(out)
            first_end = round(rows[0]["placed_end"] * rate)
            second_start = round(rows[1]["placed_at"] * rate)
            source = read_pcm(second, rate)
            second_onset = second_start + leading_activity_frames(source, rate)
            self.assertEqual(second_onset - first_end, round(0.26 * rate))
            self.assertEqual(joined[second_start:second_start + len(source)].tolist(), source.tolist())

    def test_nonstandard_source_rate_is_resampled_without_speedup(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "native-22050.wav"
            native_rate = 22050
            native = array.array("h", [int(8000 * math.sin(2 * math.pi * 220 * i / native_rate))
                                      for i in range(native_rate * 2)])
            with wave.open(str(source), "wb") as handle:
                handle.setnchannels(1)
                handle.setsampwidth(2)
                handle.setframerate(native_rate)
                handle.writeframes(native.tobytes())
            decoded = read_pcm(source, RATE)
            self.assertEqual(len(decoded), RATE * 2)
            crossings = sum(a <= 0 < b for a, b in zip(decoded, decoded[1:]))
            self.assertAlmostEqual(crossings / 2, 220, delta=1)

    def test_weak_first_word_survives_splice_bit_for_bit(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "quiet-first-word.wav"
            # The first word is much quieter than the following vowel. A peak
            # threshold of 2 percent used to discard this meaningful signal.
            samples = silence(.08) + tone(.42, amplitude=30) + tone(1, amplitude=12000)
            write_wav(path, samples)
            out = Path(tmp) / "joined.wav"
            rows = join([path], out)
            joined, rate = read_wav(out)
            index = round(rows[0]["placed_at"] * rate)
            self.assertEqual(joined[index:index + len(samples)].tolist(), samples.tolist())

    def test_join_preserves_the_committed_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            takes = []
            for index, lead in enumerate([0.05, 0.40, 0.36, 0.28]):
                path = root / f"take{index}.wav"
                write_wav(path, silence(lead) + tone(1.0, frequency=180 + index * 40))
                takes.append(path)
            target = 12.0
            out = root / "joined.wav"
            join(takes, out, total_seconds=target)
            joined, rate = read_wav(out)
            # Shortening the narration desynchronises captions and shots, so the
            # joined track must land on the runtime the edit already committed to.
            self.assertLess(abs(len(joined) / rate - target), 0.05)

    def test_gap_is_never_negative_when_speech_exceeds_runtime(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            takes = []
            for index in range(3):
                path = root / f"take{index}.wav"
                write_wav(path, tone(2.0, frequency=200 + index * 30))
                takes.append(path)
            out = root / "joined.wav"
            reports = join(takes, out, total_seconds=1.0)
            for earlier, later in zip(reports, reports[1:]):
                self.assertGreaterEqual(later["placed_at"] - earlier["placed_end"], -0.02)

    def test_many_fractional_takes_keep_exact_sample_addresses(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            takes = []
            original = []
            # These durations cannot be represented exactly in float seconds;
            # the former cursor/int implementation shifted several later takes.
            for i, frames in enumerate([1003, 12017, 3211, 7909, 11477, 809]):
                path = root / f"take{i}.wav"
                samples = array.array("h", [(j * 91 + i * 47) % 22001 - 11000 for j in range(frames)])
                write_wav(path, samples)
                takes.append(path)
                original.append(samples)
            out = root / "joined.wav"
            rows = join(takes, out, gap_ms=180, lead_ms=320, tail_ms=700)
            joined, rate = read_wav(out)
            expected_frame = round(.32 * rate)
            for row, samples in zip(rows, original):
                self.assertEqual(row["placed_start_frame"], expected_frame)
                self.assertEqual(row["placed_end_frame"], expected_frame + len(samples))
                self.assertEqual(round(row["placed_at"] * rate), expected_frame)
                self.assertEqual(joined[expected_frame:expected_frame + len(samples)], samples)
                expected_frame += len(samples) + round(.18 * rate)
            expected_total = expected_frame - round(.18 * rate) + round(.70 * rate)
            self.assertEqual(len(joined), expected_total)


if __name__ == "__main__":
    unittest.main()
