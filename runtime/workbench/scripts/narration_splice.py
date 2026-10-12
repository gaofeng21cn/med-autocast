#!/usr/bin/env python3
"""Join narration takes on their real speech boundaries.

TTS output routinely starts with a variable amount of silence and can end with a
long decay. Concatenating takes at fixed offsets stacked that silence on top of
the intended pause, so the first syllable of every segment after the first was
inaudible and the episode sounded like words were being dropped.

This module measures each take, trims head and tail silence, keeps a short
natural pause, and reports the measured gaps so review can verify them.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import wave
from pathlib import Path


def read_pcm(path: Path, rate: int):
    with wave.open(str(path)) as handle:
        channels = handle.getnchannels()
        samples = array.array("h")
        samples.frombytes(handle.readframes(handle.getnframes()))
    if channels == 2:
        samples = samples[0::2]
    return samples


def envelope(samples, rate: int, window_ms: int = 10):
    window = max(1, int(rate * window_ms / 1000))
    out = []
    for start in range(0, len(samples), window):
        chunk = samples[start:start + window]
        if not chunk:
            break
        out.append(math.sqrt(sum(x * x for x in chunk) / len(chunk)))
    return out


def _tail_index(env, threshold):
    for offset, value in enumerate(reversed(env)):
        if value > threshold:
            return offset
    return None


def trim_bounds(samples, rate: int, *, head_keep_ms: int = 40, tail_keep_ms: int = 90,
                threshold_ratio: float = 0.06, window_ms: int = 10):
    """Return [start, end) sample indices of real speech.

    A small amount of the original silence is kept so plosive consonants do not
    lose their transient; trimming to the exact energy edge clipped the first
    syllable, which is the same defect in the opposite direction.
    """
    env = envelope(samples, rate, window_ms)
    if not env:
        return 0, len(samples)
    peak = max(env)
    if peak <= 0:
        return 0, len(samples)
    threshold = peak * threshold_ratio
    first = None
    for index, value in enumerate(env):
        if value > threshold:
            first = index
            break
    if first is None:
        return 0, len(samples)
    tail = _tail_index(env, threshold)
    last = len(env) - 1 - tail if tail is not None else len(env) - 1
    step = int(rate * window_ms / 1000)
    start = max(0, first * step - int(rate * head_keep_ms / 1000))
    end = min(len(samples), (last + 1) * step + int(rate * tail_keep_ms / 1000))
    return start, end


def speech_report(path: Path, rate: int = 24000):
    samples = read_pcm(path, rate)
    start, end = trim_bounds(samples, rate)
    env = envelope(samples, rate)
    peak = max(env) if env else 0
    head_silence = 0.0
    if peak > 0:
        for value in env[:400]:
            if value <= peak * 0.05:
                head_silence += 0.01
            else:
                break
    return {
        "file": path.name,
        "duration": round(len(samples) / rate, 3),
        "head_silence": round(head_silence, 3),
        "trim_start": round(start / rate, 3),
        "trim_end": round(end / rate, 3),
        "speech_duration": round((end - start) / rate, 3),
    }


def join(takes, out_path: Path, rate: int = 24000, gap_ms: int = 260,
         lead_ms: int = 320, tail_ms: int = 420, total_seconds: float | None = None):
    """Concatenate takes using measured speech boundaries.

    `gap_ms` is the pause a listener hears between sentences. When
    `total_seconds` is given, the silence reclaimed from the takes is returned
    to the pauses so the joined track keeps the duration the edit already
    committed to. Shortening the narration would desynchronise captions and
    shots, which is worse than the original defect.
    """
    chunks = []
    reports = []
    cursor = lead_ms / 1000.0
    payloads = []
    for path in takes:
        samples = read_pcm(path, rate)
        start, end = trim_bounds(samples, rate)
        payloads.append((samples, start, end))

    speech_total = sum((end - start) for _, start, end in payloads) / rate
    if total_seconds is not None:
        overhead = lead_ms / 1000.0 + tail_ms / 1000.0
        available = total_seconds - speech_total - overhead
        count = max(1, len(takes) - 1)
        # Even when the speech alone is longer than the committed runtime, the
        # joined track must still land on it; otherwise captions and shots drift
        # away from the voice, which is the worse failure.
        gap_ms = max(0, int(available / count * 1000))

    gap = gap_ms / 1000.0
    cursor = lead_ms / 1000.0
    for path, (samples, start, end) in zip(takes, payloads):
        payload = samples[start:end]
        chunks.append((cursor, payload))
        reports.append({**speech_report(path, rate), "placed_at": round(cursor, 3),
                        "placed_end": round(cursor + len(payload) / rate, 3)})
        cursor += len(payload) / rate
        if path is not takes[-1]:
            cursor += gap_ms / 1000.0
    total = int((cursor + tail_ms / 1000.0) * rate)
    buffer = array.array("h", [0]) * total
    for offset, payload in chunks:
        index = int(offset * rate)
        buffer[index:index + len(payload)] = payload
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(out_path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(buffer.tobytes())
    return reports


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--takes", nargs="+", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path)
    parser.add_argument("--gap-ms", type=int, default=260)
    parser.add_argument("--lead-ms", type=int, default=320)
    args = parser.parse_args()
    reports = join(args.takes, args.out, gap_ms=args.gap_ms, lead_ms=args.lead_ms)
    for row in reports:
        print("%-16s speech=%5.2fs head_silence=%5.2fs placed=%6.2f-%6.2f" % (
            row["file"][:16], row["speech_duration"], row["head_silence"],
            row["placed_at"], row["placed_end"]))
    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps({"schema": "narration_splice/v1",
                                          "gap_ms": args.gap_ms, "takes": reports},
                                         ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
