#!/usr/bin/env python3
"""Generate an original, lyric-free gentle music bed for patient explainers.

The result is intentionally sparse: soft sustained chord tones plus a very
quiet repeating two-note figure.  It is a production asset, not a featured
song, and is mixed under narration by the final-video builder.
"""

from __future__ import annotations

import argparse
import math
import random
import wave
from pathlib import Path


SAMPLE_RATE = 44_100
CHORDS = [
    (261.63, 329.63, 392.00),  # C major
    (220.00, 261.63, 329.63),  # A minor
    (174.61, 220.00, 261.63),  # F major
    (196.00, 246.94, 293.66),  # G major
]


def envelope(position: float, duration: float) -> float:
    attack = min(2.2, duration * 0.18)
    release = min(3.0, duration * 0.24)
    if position < attack:
        return position / attack
    if position > duration - release:
        return max(0.0, (duration - position) / release)
    return 1.0


def tone(frequency: float, t: float, phase: float = 0.0) -> float:
    # A warm, muted pad: fundamental plus very restrained upper harmonics.
    return (
        math.sin(2 * math.pi * frequency * t + phase)
        + 0.22 * math.sin(2 * math.pi * frequency * 2 * t + phase * 0.7)
        + 0.08 * math.sin(2 * math.pi * frequency * 3 * t + phase * 1.3)
    ) / 1.30


def build(duration: float, target: Path) -> None:
    random.seed(20260904)
    total = int(duration * SAMPLE_RATE)
    chord_length = 8.0
    data = bytearray()
    for index in range(total):
        t = index / SAMPLE_RATE
        chord_position = t % (chord_length * len(CHORDS))
        chord_index = int(chord_position // chord_length)
        local = chord_position % chord_length
        chord = CHORDS[chord_index]

        pad = sum(tone(freq, local * 0.995 + t * 0.005, phase=i * 0.31) for i, freq in enumerate(chord))
        pad *= 0.075 * envelope(local, chord_length)

        # A barely audible two-note figure every four seconds gives motion
        # without creating an insistent melody beneath speech.
        beat = t % 4.0
        figure = 0.0
        if beat < 0.55:
            figure += tone(chord[0] * 2, beat, 0.4) * math.exp(-beat * 4.2) * 0.022
        if 1.65 <= beat < 2.15:
            figure += tone(chord[1] * 2, beat - 1.65, 0.8) * math.exp(-(beat - 1.65) * 4.2) * 0.018

        # Very low-level deterministic air prevents a sterile digital floor.
        air = (random.random() * 2.0 - 1.0) * 0.00045
        sample = max(-0.92, min(0.92, pad + figure + air))
        value = int(sample * 32767)
        data += value.to_bytes(2, byteorder="little", signed=True)

    target.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(target), "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(SAMPLE_RATE)
        output.writeframes(data)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--duration", type=float, default=180.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    build(args.duration, args.output)
    print(args.output)


if __name__ == "__main__":
    main()
