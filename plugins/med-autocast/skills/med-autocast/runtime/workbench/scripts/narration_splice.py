#!/usr/bin/env python3
"""Join original takes without cutting quiet consonants or relabeling sample rates.

An energy threshold is a locator for review, not proof of silence. The default
preserves every decoded source sample. An explicitly requested silence trim only
removes near-digital silence, and retains a guard at each edge.
"""
from __future__ import annotations

import argparse
import array
import json
import math
import subprocess
import wave
from pathlib import Path


def read_pcm(path: Path, rate: int):
    # IndexTTS sources are frequently 22050 Hz and VoxCPM sources 48000 Hz.
    # Writing their raw samples under a 24000 Hz header changes pitch and timing.
    payload = subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-ar", str(rate),
        "-ac", "1", "-c:a", "pcm_s16le", "-f", "s16le", "-"], stderr=subprocess.PIPE)
    samples = array.array("h")
    samples.frombytes(payload)
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


def leading_activity_frames(samples, rate: int, *, threshold_ratio: float = 0.03,
                             window_ms: int = 5, consecutive_windows: int = 4) -> int:
    """Locate the first stable speech activity without deleting any samples.

    TTS takes often contain a variable pre-roll.  The locator is deliberately
    conservative and is used only to place a complete take earlier in the
    joined track; it is never used as a cut boundary.  Requiring consecutive
    active windows avoids treating encoder noise as the first syllable.
    """
    env = envelope(samples, rate, window_ms)
    if not env:
        return 0
    peak = max(env)
    if peak <= 0:
        return 0
    threshold = max(8.0, peak * threshold_ratio)
    run = max(1, int(consecutive_windows))
    for index in range(max(0, len(env) - run + 1)):
        if all(value > threshold for value in env[index:index + run]):
            return index * max(1, int(rate * window_ms / 1000))
    return 0


def effective_gap_frames(gap_frames: int, next_activity_frames: int) -> int:
    """Return silence to insert before a complete next take.

    The take's leading pre-roll is retained.  Subtracting that pre-roll from
    the inserted silence keeps the *spoken* onset at the requested gap while
    preserving every source sample.
    """
    return max(0, int(gap_frames) - int(next_activity_frames))


def trim_bounds(samples, rate: int, *, head_keep_ms: int = 120, tail_keep_ms: int = 180,
                threshold_ratio: float = 0.0, window_ms: int = 5,
                trim_silence: bool = False):
    """Return a lossless range by default; optionally trim only digital silence.

Relative peak thresholds can mistake a quiet first word for silence. A request
for trimming does not permit a louder threshold than -72 dBFS (8 PCM LSB RMS).
    """
    if not trim_silence:
        return 0, len(samples)
    env = envelope(samples, rate, window_ms)
    if not env:
        return 0, len(samples)
    peak = max(env)
    if peak <= 0:
        return 0, len(samples)
    threshold = min(8.0, peak * threshold_ratio) if threshold_ratio > 0 else 8.0
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


def speech_report(path: Path, rate: int = 24000, samples=None):
    samples = read_pcm(path, rate) if samples is None else samples
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
        "source_sample_rate": _source_rate(path),
        "decoded_sample_rate": rate,
        "decoded_source_frames": len(samples),
        "preserved_frames": end - start,
        "trim_policy": "preserve_all_source_samples",
        "head_silence_note": "relative-energy activity locator; does not prove missing words",
        "leading_activity_seconds": round(leading_activity_frames(samples, rate) / rate, 3),
    }


def _source_rate(path):
    result = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
        "stream=sample_rate", "-of", "json", str(path)], text=True))
    return int(result["streams"][0]["sample_rate"])


def join(takes, out_path: Path, rate: int = 24000, gap_ms: int = 260,
         lead_ms: int = 320, tail_ms: int = 420, total_seconds: float | None = None):
    """Concatenate correctly decoded takes, preserving the complete voice.

    `gap_ms` is inserted silence between complete source takes; their own
    silence is preserved as well. `total_seconds` may allocate available time
    to gaps and padding, but never authorizes deleting or speeding speech.
    Placement addresses are integer PCM frames, shared by audio and receipts.
    """
    takes = list(takes)
    chunks = []
    reports = []
    payloads = []
    for path in takes:
        samples = read_pcm(path, rate)
        if not samples:
            raise ValueError(f"旁白声段解码为空，未输出拼接音轨: {path}")
        start, end = trim_bounds(samples, rate)
        payloads.append((samples, start, end, leading_activity_frames(samples, rate)))

    speech_total = sum((end - start) for _, start, end, _ in payloads) / rate
    if total_seconds is not None:
        overhead = lead_ms / 1000.0 + tail_ms / 1000.0
        available = total_seconds - speech_total - overhead
        count = max(1, len(takes) - 1)
        # A short old runtime cannot authorize cutting or speeding speech. In
        # that case extend the narration and let the caller retime the picture.
        gap_ms = max(0, int(available / count * 1000))

    # Placement is an integer PCM frame address. Floating second cursors plus
    # int(seconds * rate) can move later takes one sample earlier than their
    # receipt, and can silently drop one sample from the final tail.
    lead_frames = round(lead_ms * rate / 1000)
    gap_frames = round(gap_ms * rate / 1000)
    tail_frames = round(tail_ms * rate / 1000)
    cursor_frames = lead_frames
    for i, (path, (samples, start, end, activity)) in enumerate(zip(takes, payloads)):
        payload = samples[start:end]
        chunks.append((cursor_frames, payload))
        end_frame = cursor_frames + len(payload)
        reports.append({**speech_report(path, rate, samples),
                        "placed_start_frame": cursor_frames,
                        "placed_end_frame": end_frame,
                        "leading_activity_frames": activity,
                        "effective_gap_before_frames": (cursor_frames - (chunks[-2][0] + len(chunks[-2][1]))
                                                         if i else None),
                        "placed_at": round(cursor_frames / rate, 6),
                        "placed_end": round(end_frame / rate, 6)})
        cursor_frames = end_frame
        if i < len(takes) - 1:
            # Preserve the whole next take, but move its file start earlier by
            # its own pre-roll so the *spoken* onset lands after the intended
            # pause.  This avoids the audible impression that the first words
            # of a new segment were swallowed at the cut.
            next_activity = payloads[i + 1][3]
            cursor_frames += effective_gap_frames(gap_frames, next_activity)
    total = cursor_frames + tail_frames
    if total_seconds is not None:
        total = max(total, round(total_seconds * rate))
    buffer = array.array("h", [0]) * total
    for offset, payload in chunks:
        buffer[offset:offset + len(payload)] = payload
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
        args.report.write_text(json.dumps({"schema": "narration_splice/v2",
                                          "gap_ms": args.gap_ms, "takes": reports},
                                         ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
