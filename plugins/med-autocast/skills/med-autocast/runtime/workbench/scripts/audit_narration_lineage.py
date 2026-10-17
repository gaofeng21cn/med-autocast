#!/usr/bin/env python3
"""Trace actual source take waveforms through narration, mix and delivered video.

This is signal evidence, never an approval of pronunciation or full listening.
Metadata that says `splice` is present is not evidence that shipped bytes match.
"""
from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import json
import subprocess
import wave
from pathlib import Path

import numpy as np
import yaml

from delivery_layout import locations

RATE = 8000


def decode(path):
    return np.frombuffer(subprocess.check_output([
        "ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ar", str(RATE),
        "-ac", "1", "-f", "f32le", "-"], stderr=subprocess.PIPE), dtype=np.float32)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def similarity(a, b):
    n = min(len(a), len(b))
    if n < 40:
        return None
    a, b = a[:n].astype(np.float64), b[:n].astype(np.float64)
    denom = np.sqrt(np.dot(a, a) * np.dot(b, b))
    return float(np.dot(a, b) / denom) if denom else None


def _correlations(target, probe, start, end):
    """Return normalized correlations for a bounded target range.

    This deliberately uses a local range instead of a full-track FFT.  A
    repeated phrase elsewhere in a long narration must not be able to satisfy
    a beat whose expected timestamp is known.
    """
    probe = np.asarray(probe, dtype=np.float64)
    if len(probe) == 0:
        return None
    start = max(0, int(start))
    end = min(len(target) - len(probe), int(end))
    if end < start:
        return None
    segment = np.asarray(target[start:end + len(probe)], dtype=np.float64)
    # FFT is important here: this helper runs for several anchors across
    # every beat and every output track in a season audit. The window is
    # local, but the convolution must still be sub-quadratic.
    size = 1 << (len(segment) + len(probe) - 1).bit_length()
    convolution = np.fft.irfft(
        np.fft.rfft(segment, size) * np.fft.rfft(probe[::-1], size), size
    )
    dots = convolution[len(probe) - 1:len(segment)]
    sq = np.concatenate(([0.0], np.cumsum(segment * segment)))
    energy = sq[len(probe):] - sq[:-len(probe)]
    probe_energy = float(np.dot(probe, probe))
    if probe_energy <= 1e-16:
        return None
    denominator = np.sqrt(np.maximum(energy, 1e-16) * probe_energy)
    corr = dots / np.maximum(denominator, 1e-15)
    corr[energy < probe_energy * .003] = -1
    return start, corr


def locate_top(target, probe, start, end, top_k=4, min_separation_seconds=.10):
    """Find the strongest local matches, returning absolute sample positions."""
    result = _correlations(target, probe, start, end)
    if result is None:
        return []
    offset, corr = result
    order = np.argsort(corr)[::-1]
    separation = max(1, round(min_separation_seconds * RATE))
    peaks = []
    for index in order:
        score = float(corr[index])
        if score < -0.5:
            break
        position = int(offset + index)
        if all(abs(position - row["position"]) >= separation for row in peaks):
            peaks.append({"position": position, "score": score})
            if len(peaks) >= top_k:
                break
    return peaks


def similarity_at(target, probe, position):
    position = int(position)
    if position < 0 or position + len(probe) > len(target):
        return None
    return similarity(target[position:position + len(probe)], probe)


def active_window_start(source, requested, low, high, length):
    """Keep a probe near its intended region, but outside quiet pauses.

    A quiet source pause cannot identify speech in a mixed track: the music
    naturally dominates it.  Use source-only energy to choose a nearby active
    window; this never changes or trims the source and never moves the head.
    """
    last = max(0, len(source) - length)
    low, high = max(0, int(low)), min(last, max(0, int(high)))
    requested = min(last, max(0, int(requested)))
    if high < low:
        return requested
    candidates = np.unique(np.concatenate((
        np.arange(low, high + 1, max(1, round(.01 * RATE))),
        [min(high, max(low, requested)), high],
    )))
    energy = np.concatenate(([0.0], np.cumsum(np.asarray(source, dtype=np.float64) ** 2)))
    scores = (energy[candidates + length] - energy[candidates]) / length
    # A -20 dB energy window relative to the region's peak still represents
    # speech. Low-energy model noise/breathing cannot become an identity probe.
    threshold = max(10 ** (-45 / 10), float(scores.max()) * .01)
    active = candidates[scores >= threshold]
    if len(active) == 0:
        return requested
    return int(active[np.argmin(np.abs(active - requested))])


def build_anchors(source, source_onset, window_seconds=.42):
    """Build distinct speech anchors while retaining their source offsets."""
    source = np.asarray(source, dtype=np.float32)
    if len(source) < round(.18 * RATE):
        return []
    duration = len(source) / RATE
    onset_seconds = max(0.0, float(source_onset or 0.0))
    # The first anchor catches a missing first word; later anchors make a
    # repeated phrase at another timestamp an insufficient match by itself.
    requested = [
        ("head", onset_seconds + .08),
        ("middle", max(onset_seconds + .15, duration * .42)),
        ("tail", max(onset_seconds + .15, duration - window_seconds - .12)),
    ]
    anchors = []
    minimum = round(.18 * RATE)
    length = round(window_seconds * RATE)
    seen = set()
    for label, requested_seconds in requested:
        start = min(max(0, round(requested_seconds * RATE)), max(0, len(source) - minimum))
        if len(source) >= length and label != "head":
            low_fraction, high_fraction = (.25, .65) if label == "middle" else (.65, 1.0)
            start = active_window_start(
                source, start, max(round(onset_seconds * RATE), round(len(source) * low_fraction)),
                round(len(source) * high_fraction) - length, length,
            )
        end = min(len(source), start + length)
        if end - start < minimum:
            continue
        key = (start, end)
        if key in seen:
            continue
        seen.add(key)
        anchors.append({"label": label, "offset": start / RATE,
                        "samples": source[start:end].copy()})
    return anchors


def locate_multianchor(target, anchors, expected_zero, radius_seconds=1.25,
                       top_k=4):
    """Locate source zero using several anchors in the expected local window.

    A candidate is proposed by each anchor, then all anchors are scored at the
    same source-zero hypothesis. This rejects a coincident short phrase and
    keeps the result tied to beat metadata rather than an unrelated global hit.
    """
    if not anchors:
        return None
    candidates = {round(float(expected_zero) * RATE)}
    expected_frame = round(float(expected_zero) * RATE)
    per_anchor = []
    for anchor in anchors:
        offset = round(anchor["offset"] * RATE)
        start = expected_frame + offset - round(radius_seconds * RATE)
        end = expected_frame + offset + round(radius_seconds * RATE)
        peaks = locate_top(target, anchor["samples"], start, end, top_k=top_k)
        per_anchor.append({"label": anchor["label"], "offset": anchor["offset"],
                           "peaks": peaks})
        for peak in peaks:
            candidates.add(peak["position"] - offset)
    if not candidates:
        return None
    best = None
    for origin in candidates:
        scores = []
        for anchor in anchors:
            score = similarity_at(target, anchor["samples"],
                                  origin + round(anchor["offset"] * RATE))
            if score is not None:
                scores.append(float(score))
        if not scores:
            continue
        coverage = len(scores) / len(anchors)
        median = float(np.median(scores))
        minimum = float(min(scores))
        # Median rewards broad agreement; the minimum prevents one repeated
        # anchor from hiding a missing or shifted head/tail.
        joint = .65 * median + .35 * minimum
        row = {"origin": origin / RATE, "score": joint,
               "median_score": median, "minimum_score": minimum,
               "coverage": coverage, "anchor_scores": scores}
        if best is None or row["score"] > best["score"]:
            best = row
    if best is None or best["coverage"] < .67:
        return None
    best["expected_zero"] = float(expected_zero)
    best["delta_seconds"] = best["origin"] - float(expected_zero)
    best["search_radius_seconds"] = radius_seconds
    best["anchors"] = per_anchor
    return best


def onset(audio):
    step = 80
    env = np.array([np.sqrt(np.mean(audio[i:i + step] ** 2))
                    for i in range(0, len(audio), step)])
    # Locating speech is only a review locator. It never authorizes trimming.
    threshold = max(10 ** (-55 / 20), float(env.max()) * .01) if len(env) else 0
    candidates = np.flatnonzero(env > threshold)
    return (float(candidates[0] * step / RATE) if len(candidates) else None)


def audit_project(workspace, series, episode, project, published=None):
    project = (workspace / project).resolve()
    receipt = project / "audio/narration_beats.json"
    data = json.loads(receipt.read_text())
    candidates = {
        "raw_narration": project / "audio/narration.wav",
        "normalized_narration": project / "audio/narration-normalized.wav",
        "mixed_audio": project / json.loads((project / "project.json").read_text()).get("audio", "audio.wav"),
    }
    current = project / "out/current.json"
    if current.exists():
        path = Path(json.loads(current.read_text()).get("path", ""))
        if path.is_file():
            candidates["rendered_mp4"] = path
    if published and published.is_file():
        candidates["published_mp4"] = published
    # If delivery and render contain identical bytes, one decode proves both.
    decoded, hashes, signatures = {}, {}, {}
    for name, path in candidates.items():
        if not path.is_file():
            continue
        digest = sha(path)
        hashes[name] = {"path": str(path), "sha256": digest}
        if digest not in signatures:
            signatures[digest] = decode(path)
        decoded[name] = signatures[digest]
        hashes[name]["duration"] = round(len(decoded[name]) / RATE, 6)
    rows, flags = [], []
    if published is not None and not published.is_file():
        flags.append({"track": "published_mp4", "reason": "expected_published_mp4_missing",
                      "path": str(published)})
    splices = data.get("splice", {}).get("takes", [])
    for i, beat in enumerate(data.get("beats", [])):
        source = Path(beat["audio"])
        if not source.is_absolute():
            source = project / source
        actual = decode(source)
        with wave.open(str(source)) as handle:
            source_rate = handle.getframerate()
        source_onset = onset(actual)
        anchors = build_anchors(actual, source_onset)
        expected_zero = float(beat["start"]) - float(beat.get("trimmed_head_seconds") or 0)
        entry = {"id": beat["id"], "text": beat["text"], "source": str(source),
                 "source_sha256": sha(source), "source_sample_rate": source_rate,
                 "source_duration": round(len(actual) / RATE, 6),
                 "source_activity_start": source_onset, "declared_start": beat["start"],
                 "declared_end": beat["end"], "expected_source_zero": expected_zero,
                 "anchor_count": len(anchors), "tracks": {}}
        if i < len(splices):
            entry["old_trim_start"] = splices[i].get("trim_start", splices[i].get("trimmed_head_seconds"))
        for name, target in decoded.items():
            match = locate_multianchor(target, anchors, expected_zero)
            if match is None:
                entry["tracks"][name] = {
                    "match_method": "local_multianchor",
                    "expected_source_zero": expected_zero,
                    "search_radius_seconds": 1.25,
                    "anchor_count": len(anchors),
                }
                if name in ("normalized_narration", "mixed_audio", "rendered_mp4", "published_mp4"):
                    flags.append({"beat": beat["id"], "track": name,
                                  "reason": "local_multianchor_not_found"})
                continue
            origin = match["origin"]
            first = max(0, round((source_onset or 0) * RATE) - 80)
            stop = min(len(actual), first + round(.75 * RATE))
            at = round(origin * RATE) + first
            prefix = similarity(actual[first:stop], target[max(0, at):max(0, at) + stop - first])
            info = {"match_method": "local_multianchor",
                    # Keep the old key for consumers that only know v1.
                    "native_waveform_match": round(match["score"], 6),
                    "multianchor_score": round(match["score"], 6),
                    "multianchor_median_score": round(match["median_score"], 6),
                    "multianchor_minimum_score": round(match["minimum_score"], 6),
                    "multianchor_coverage": round(match["coverage"], 6),
                    "anchor_scores": [round(value, 6) for value in match["anchor_scores"]],
                    "anchor_count": len(anchors),
                    "inferred_source_zero": round(origin, 6),
                    "actual_activity_start": round(origin + (source_onset or 0), 6),
                    "source_prefix_correlation": round(prefix, 6) if prefix is not None else None,
                    "metadata_offset_seconds": round(origin - beat["start"], 6)}
            if match["score"] < .8 and source_rate != 24000:
                # Reproduce the old rate-relabel bug without using it to mutate
                # a file. Correctly resampled speech should match the native
                # take. The diagnostic is local and multi-anchor as well.
                warped = np.interp(np.arange(round(len(actual) * source_rate / 24000)) * 24000 / source_rate,
                                   np.arange(len(actual)), actual).astype(np.float32)
                wrong = locate_multianchor(target,
                                           build_anchors(warped, onset(warped)),
                                           expected_zero)
                if wrong:
                    info["rate_relabel_match"] = round(wrong["score"], 6)
                    if wrong["score"] > .85:
                        info["sample_rate_relabel_detected"] = True
            entry["tracks"][name] = info
            if name in ("normalized_narration", "mixed_audio", "rendered_mp4", "published_mp4"):
                if match["score"] < .65:
                    flags.append({"beat": beat["id"], "track": name,
                                  "reason": "multianchor_low_confidence",
                                  "score": round(match["score"], 6)})
                elif prefix is None or prefix < .8:
                    flags.append({"beat": beat["id"], "track": name, "reason": "prefix_missing_or_changed"})
                if abs(origin - expected_zero) > .12:
                    flags.append({"beat": beat["id"], "track": name, "reason": "beat_metadata_not_on_actual_voice", "delta": round(origin - expected_zero, 4)})
        rows.append(entry)
    raw = decoded.get("raw_narration")
    norm = decoded.get("normalized_narration")
    if raw is not None and norm is not None and abs(len(raw) - len(norm)) > RATE * .02:
        flags.append({"reason": "raw_normalized_duration_disagree",
                      "delta_seconds": round((len(norm) - len(raw)) / RATE, 6)})
    return {"schema": "narration_lineage_audit/v2", "series": series, "episode": episode,
            "project": str(project), "backend": data.get("backend"), "tracks": hashes,
            "expected_published_path": str(published) if published is not None else None,
            "beats": rows, "flags": flags, "full_listening": "pending",
            "pronunciation_review": "pending",
            "method": "local expected-window multi-anchor waveform lineage, no ASR approval"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--series")
    parser.add_argument("--episode")
    parser.add_argument("--workers", type=int, default=2)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    config = yaml.safe_load((workspace / "workbench.yaml").read_text())
    jobs = []
    for series, spec in config.get("series", {}).items():
        if args.series and series != args.series:
            continue
        for episode, value in spec.get("episodes", {}).items():
            if args.episode and episode != args.episode:
                continue
            if value.get("project"):
                published = locations(workspace, series, episode)["user"] / "video.mp4"
                jobs.append((series, episode, value["project"], published))
    args.output.mkdir(parents=True, exist_ok=True)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        futures = {pool.submit(audit_project, workspace, *job): job for job in jobs}
        for future in concurrent.futures.as_completed(futures):
            series, episode, _, _ = futures[future]
            try:
                result = future.result()
                destination = args.output / series / f"{episode}.json"
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
                results.append({"series": series, "episode": episode, "flags": len(result["flags"]), "report": str(destination)})
            except Exception as exc:
                results.append({"series": series, "episode": episode, "error": str(exc)})
            print(json.dumps(results[-1], ensure_ascii=False), flush=True)
    summary = {"schema": "narration_lineage_audit_batch/v2", "episodes": len(results),
               "errors": sum("error" in row for row in results), "detail": sorted(results, key=lambda x: (x["series"], x["episode"]))}
    (args.output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
