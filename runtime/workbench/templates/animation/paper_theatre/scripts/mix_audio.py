#!/usr/bin/env python3
"""Mix a frozen narration, optional music stems, and event-aligned foley locally."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import subprocess
import tempfile
from pathlib import Path

import numpy as np
import pyloudnorm as pyln
import soundfile as sf
from scipy.signal import lfilter, resample_poly

from sound_materials import material_sound


INTERMEDIATE_WAVS = (
    "foley.wav",
    "music-raw.wav",
    "music-prepared.wav",
    "music-ducked.wav",
    "premix.wav",
)


def run(args: list[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, check=True, capture_output=True, text=True)


def _read_audio(path: Path, target_rate: int | None = None) -> tuple[np.ndarray, int]:
    """Load audio as 2D float64 (frames, channels) via soundfile, with ffmpeg decode fallback for AAC/M4A."""
    try:
        data, sr = sf.read(str(path), dtype="float64", always_2d=True)
    except Exception:
        probe = json.loads(
            subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_streams", "-select_streams", "a:0", "-of", "json", str(path)],
                text=True,
            )
        )
        stream = probe["streams"][0]
        sr = int(target_rate or stream["sample_rate"])
        channels = int(stream.get("channels") or 2)
        decoded = subprocess.check_output(
            ["ffmpeg", "-v", "error", "-i", str(path), "-ar", str(sr), "-ac", str(channels), "-f", "f64le", "-"]
        )
        data = np.frombuffer(decoded, dtype=np.float64).reshape(-1, channels).copy()
    if target_rate is not None and sr != target_rate and len(data) > 0:
        divisor = math.gcd(int(sr), int(target_rate))
        up, down = int(target_rate) // divisor, int(sr) // divisor
        data = resample_poly(data, up, down, axis=0)
        sr = int(target_rate)
    return data, int(sr)


def _ensure_stereo(data: np.ndarray) -> np.ndarray:
    if data.ndim == 1:
        return np.stack([data, data], axis=1)
    if data.shape[1] == 1:
        return np.repeat(data, 2, axis=1)
    if data.shape[1] > 2:
        return data[:, :2]
    return data


def _write_audio(path: Path, data: np.ndarray, rate: int, subtype: str = "PCM_24") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    clipped = np.clip(data, -1.0, 1.0)
    suffix = path.suffix.lower()
    if suffix in (".wav", ".flac"):
        sf.write(str(path), clipped, rate, subtype=subtype)
        return
    # Containers not natively writable by libsndfile (e.g., .m4a/.aac) encode cleanly via FFmpeg.
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=path.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        sf.write(str(temporary), clipped, rate, subtype="PCM_24")
        run(["ffmpeg", "-y", "-v", "error", "-i", str(temporary), "-ar", str(rate), "-ac", "2",
             "-c:a", "aac", "-b:a", "256k", str(path)])
    finally:
        temporary.unlink(missing_ok=True)


def _meter_for(data: np.ndarray, rate: int) -> pyln.Meter:
    duration = len(data) / max(1, rate)
    block_size = 0.400 if duration >= 0.45 else max(0.05, duration * 0.8)
    return pyln.Meter(rate, block_size=block_size)


def measure(path: Path, target: float = -16, peak: float = -1.2) -> dict:
    data, sr = _read_audio(path)
    if len(data) == 0:
        return {
            "engine": "pyloudnorm",
            "input_i": "-inf",
            "input_tp": "-inf",
            "target_i": f"{float(target):.2f}",
            "target_tp": f"{float(peak):.2f}",
            "target_offset": "0.00",
        }
    loudness = float(_meter_for(data, sr).integrated_loudness(data))
    peak_amp = float(np.max(np.abs(data)))
    peak_db = 20.0 * math.log10(peak_amp) if peak_amp > 0.0 else -math.inf
    return {
        "engine": "pyloudnorm",
        "input_i": f"{loudness:.2f}" if math.isfinite(loudness) else "-inf",
        "input_tp": f"{peak_db:.2f}" if math.isfinite(peak_db) else "-inf",
        "target_i": f"{float(target):.2f}",
        "target_tp": f"{float(peak):.2f}",
        "target_offset": f"{float(target) - loudness:.2f}" if math.isfinite(loudness) else "0.00",
    }


def normalize(source: Path, output: Path, rate: int, target: float = -16, peak: float = -1.2) -> dict:
    data, sr = _read_audio(source, target_rate=rate)
    stereo = _ensure_stereo(data)
    loudness = float(_meter_for(stereo, sr).integrated_loudness(stereo)) if len(stereo) > 0 else -math.inf
    peak_amp = float(np.max(np.abs(stereo))) if len(stereo) > 0 else 0.0
    peak_db = 20.0 * math.log10(peak_amp) if peak_amp > 0.0 else -math.inf
    before = {
        "engine": "pyloudnorm",
        "input_i": f"{loudness:.2f}" if math.isfinite(loudness) else "-inf",
        "input_tp": f"{peak_db:.2f}" if math.isfinite(peak_db) else "-inf",
        "target_i": f"{float(target):.2f}",
        "target_tp": f"{float(peak):.2f}",
        "target_offset": f"{float(target) - loudness:.2f}" if math.isfinite(loudness) else "0.00",
    }
    if math.isfinite(loudness) and len(stereo) > 0:
        normalized = pyln.normalize.loudness(stereo, loudness, float(target))
        post_peak_amp = float(np.max(np.abs(normalized)))
        peak_ceiling = 10.0 ** (float(peak) / 20.0)
        if post_peak_amp > peak_ceiling:
            normalized = pyln.normalize.peak(normalized, float(peak))
    else:
        normalized = stereo
    _write_audio(output, normalized, rate, subtype="PCM_24")
    return before


def _procedural_paper_foley(kind: str, rate: int, seed: int) -> np.ndarray:
    duration = 0.17 if kind == "stamp" else 0.44
    count = round(duration * rate)
    if count <= 0:
        return np.zeros(0, dtype=np.float32)
    rng = np.random.default_rng(seed)
    noise = rng.uniform(-1.0, 1.0, size=count)
    lo = lfilter([0.28], [1.0, -0.72], noise)
    slow = lfilter([0.04], [1.0, -0.96], lo)
    band = lo - slow
    t = np.arange(count, dtype=np.float64) / rate
    if kind == "stamp":
        samples = (np.sin(t * 2.0 * math.pi * 155.0) * np.exp(-t * 43.0) + band * 0.16) * 0.026
    else:
        samples = band * (np.sin(math.pi * t / duration) ** 2) * 0.023
    return samples.astype(np.float32)


def foley(project: Path, score: dict, output: Path, rate: int, *, return_unresolved: bool = False):
    length = round(score["duration"] * rate)
    mix = np.zeros(length, dtype=np.float64)
    resolved = []
    unresolved = []
    assets = json.loads((project / "asset_manifest.json").read_text())["assets"]
    for i, event in enumerate(score.get("sounds", [])):
        shot = next((s for s in score["shots"] if s["id"] == event["shot"]), None)
        if shot is None:
            unresolved.append({**event, "reason": "shot_not_found"})
            continue
        event_name = event.get("event")
        if event_name not in shot.get("events", {}):
            # A stale/optional foley cue must not stop the narration and picture
            # pipeline. Keep the cue visible for review, but continue with a
            # valid voice-first mix. This is Progress First: unresolved foley is
            # a quality debt, never a silent crash or fabricated timestamp.
            unresolved.append({**event, "reason": "event_not_found", "shot_events": sorted(shot.get("events", {}))})
            continue
        time = shot["start"] + shot["events"][event_name] + event.get("offset", 0)
        resolved.append(dict(event, time=time))
        start = round(time * rate)
        if event.get("asset_id"):
            source = next(a for a in assets if a["asset_id"] == event["asset_id"])
            raw, _ = _read_audio(project / source["path"], target_rate=rate)
            samples = raw.mean(axis=1)
            resolved[-1].update(source=source["path"], source_type="registered_audio")
        elif (samples := material_sound(event["kind"], rate, 1701 + i)) is not None:
            resolved[-1]["source_type"] = "procedural_material_study"
        else:
            samples = _procedural_paper_foley(event["kind"], rate, 1701 + i)
            resolved[-1]["source_type"] = "procedural_paper_foley"
        src_start = max(0, -start)
        dst_start = max(0, start)
        dst_end = min(length, start + len(samples))
        if dst_end > dst_start:
            mix[dst_start:dst_end] += samples[src_start : src_start + (dst_end - dst_start)] * float(event.get("gain", 1))
    _write_audio(output, mix, rate, subtype="PCM_16")
    return (resolved, unresolved) if return_unresolved else resolved


def music_bus(project, score, audio, rate, music=None, gain=.085, plan_path=None):
    plan = json.loads(plan_path.read_text()) if plan_path else {}
    tracks = plan.get("tracks", []) if plan_path else ([{"id": "music", "path": str(music), "gain": gain, "loop": True}] if music else [])
    duration = score["duration"]
    command = ["ffmpeg", "-y", "-v", "error"]
    filters, receipt = [], []
    for i, track in enumerate(tracks):
        path = Path(track["path"])
        if not path.is_absolute():
            path = project / path
        if track.get("loop"):
            command += ["-stream_loop", "-1"]
        command += ["-i", str(path)]
        amount = float(track.get("gain", 1))
        filters.append(f"[{i}:a]aresample={rate},aformat=channel_layouts=stereo,volume={amount},apad=whole_dur={duration},atrim=end={duration}[t{i}]")
        receipt.append({**track, "resolved_path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
    raw, prepared = audio / "music-raw.flac", audio / "music-prepared.flac"
    if tracks:
        labels = "".join(f"[t{i}]" for i in range(len(tracks)))
        filters.append(labels + f"amix=inputs={len(tracks)}:normalize=0:duration=longest,highpass=f=80,lowpass=f=6500,equalizer=f=1900:t=q:w=1:g=-3.5,afade=t=in:d=1.1,afade=t=out:st={max(0, duration - 2.4)}:d=2.4[bus]")
        command += ["-filter_complex", ";".join(filters), "-map", "[bus]", "-t", str(duration), "-c:a", "flac", str(raw)]
        run(command)
        # A plan may request a bus level; legacy single-track gain remains compatible.
        if plan.get("bus_lufs") is not None:
            normalize(raw, prepared, rate, float(plan["bus_lufs"]), -6)
        else:
            run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-c:a", "flac", str(prepared)])
    else:
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"anullsrc=r={rate}:cl=stereo", "-t", str(duration), "-c:a", "flac", str(prepared)])
    return prepared, receipt, plan.get("ducking", {})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--voice", type=Path, required=True)
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--music", type=Path)
    source.add_argument("--music-plan", type=Path, help="Stem paths relative to project root; gain and optional bus loudness")
    parser.add_argument("--music-gain", type=float, default=.085)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--retain-intermediates", action="store_true", help="诊断需要时保留无损分轨；默认在最终混音及回执校验后清理")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    score = json.loads((project / "score.json").read_text())
    audio = project / "audio"
    audio.mkdir(exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rate, duration = args.sample_rate, score["duration"]
    events, unresolved_foley = foley(project, score, audio / "foley.flac", rate, return_unresolved=True)
    music, tracks, duck = music_bus(project, score, audio, rate, args.music, args.music_gain, args.music_plan)
    duck = {"threshold": .035, "ratio": 3., "attack_ms": 45, "release_ms": 480, **duck}
    compressor = f"threshold={float(duck['threshold'])}:ratio={float(duck['ratio'])}:attack={float(duck['attack_ms'])}:release={float(duck['release_ms'])}:detection=rms:link=average:makeup=1"
    filters = (
        f"[0:a]aresample={rate},aformat=channel_layouts=stereo,apad=whole_dur={duration},atrim=end={duration},asplit=2[v][key];"
        f"[1:a][key]sidechaincompress={compressor},asplit=2[m][evidence];"
        f"[2:a]aformat=channel_layouts=stereo[f];[v][m][f]amix=inputs=3:normalize=0:duration=first[out]"
    )
    premix = audio / "premix.flac"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(args.voice), "-i", str(music), "-i", str(audio / "foley.flac"),
         "-filter_complex", filters, "-map", "[out]", "-t", str(duration), "-c:a", "flac", str(premix),
         "-map", "[evidence]", "-t", str(duration), "-c:a", "flac", str(audio / "music-ducked.flac")])
    before = normalize(premix, args.output, rate)
    receipt = {
        "voice_source": str(args.voice.resolve()), "voice_resynthesized": False,
        "voice_sha256": hashlib.sha256(args.voice.read_bytes()).hexdigest(),
        "score": "score.json", "score_sha256": hashlib.sha256((project / "score.json").read_bytes()).hexdigest(),
        "events": events, "unresolved_foley": unresolved_foley, "music": str(args.music) if args.music else None,
        "music_plan": str(args.music_plan) if args.music_plan else None,
        "music_tracks": tracks, "ducking": duck, "sample_rate": rate, "channels": 2,
        "intermediate_audio_format": "flac_lossless",
        "intermediate_audio": {
            "foley": "audio/foley.flac",
            "music_raw": "audio/music-raw.flac" if (audio / "music-raw.flac").is_file() else None,
            "music_prepared": "audio/music-prepared.flac",
            "music_ducked": "audio/music-ducked.flac",
            "premix": "audio/premix.flac",
        },
        "premix_measurement": before, "output_measurement": measure(args.output),
        "audio_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "full_listening": "pending", "tone_consistency": "unchanged_source_not_reapproved"
    }
    (audio / "mix-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    if not args.retain_intermediates:
        receipt["intermediate_audio_retained"] = False
        receipt["storage_profile"] = {"policy": "necessity_first", "retained": "final_mix_and_recipe_sources", "intermediates": "rebuildable_pruned"}
        for legacy in INTERMEDIATE_WAVS:
            (audio / legacy).with_suffix(".flac").unlink(missing_ok=True)
        receipt["intermediate_audio"] = {}
        (audio / "mix-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "events": len(events), "unresolved_foley": len(unresolved_foley), "duration": duration,
                      "music_stems": len(tracks), "sample_rate": rate, "voice_resynthesized": False}))


if __name__ == "__main__":
    main()
