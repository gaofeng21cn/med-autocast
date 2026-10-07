#!/usr/bin/env python3
"""Mix a frozen narration, optional music stems, and event-aligned foley locally."""
import argparse
import array
import hashlib
import json
import math
import random
import subprocess
import wave
from pathlib import Path
from sound_materials import material_sound


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def measure(path, target=-16, peak=-1.2):
    result = run(["ffmpeg", "-hide_banner", "-i", str(path), "-af",
                  f"loudnorm=I={target}:TP={peak}:LRA=11:print_format=json", "-f", "null", "-"])
    return json.JSONDecoder().raw_decode(result.stderr[result.stderr.rfind("{"):])[0]


def normalize(source, output, rate, target=-16, peak=-1.2):
    data = measure(source, target, peak)
    if math.isfinite(float(data["input_i"])):
        filter_text = f"loudnorm=I={target}:TP={peak}:LRA=11:linear=true:" + (
            "measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:"
            "measured_thresh={input_thresh}:offset={target_offset}"
        ).format(**data)
    else:
        filter_text = "anull"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(source), "-af", filter_text,
         "-ar", str(rate), "-ac", "2", "-c:a", "pcm_s24le", str(output)])
    return data


def foley(project, score, output, rate):
    length = round(score["duration"] * rate)
    mix = array.array("f", [0]) * length
    resolved = []
    assets = json.loads((project / "asset_manifest.json").read_text())["assets"]
    for i, event in enumerate(score.get("sounds", [])):
        shot = next(s for s in score["shots"] if s["id"] == event["shot"])
        time = shot["start"] + shot["events"][event["event"]] + event.get("offset", 0)
        resolved.append(dict(event, time=time))
        start = round(time * rate)
        if event.get("asset_id"):
            source = next(a for a in assets if a["asset_id"] == event["asset_id"])
            decoded = subprocess.check_output(["ffmpeg", "-v", "error", "-i", str(project / source["path"]),
                                               "-ar", str(rate), "-ac", "1", "-f", "f32le", "-"])
            samples = array.array("f")
            samples.frombytes(decoded)
            resolved[-1].update(source=source["path"], source_type="registered_audio")
        elif (samples := material_sound(event["kind"], rate, 1701 + i)) is not None:
            resolved[-1]["source_type"] = "procedural_material_study"
        else:
            duration = .17 if event["kind"] == "stamp" else .44
            rng = random.Random(1701 + i)
            lo = slow = 0.
            samples = array.array("f")
            for k in range(round(duration * rate)):
                noise = rng.uniform(-1, 1)
                lo += .28 * (noise - lo)
                slow += .04 * (lo - slow)
                band = lo - slow
                if event["kind"] == "stamp":
                    value = (math.sin(k / rate * 2 * math.pi * 155) * math.exp(-k / rate * 43) + band * .16) * .026
                else:
                    value = band * math.sin(math.pi * k / (duration * rate)) ** 2 * .023
                samples.append(value)
            resolved[-1]["source_type"] = "procedural_paper_foley"
        for k, value in enumerate(samples):
            if 0 <= start + k < length:
                mix[start + k] += value * event.get("gain", 1)
    pcm = array.array("h", (round(max(-1, min(1, v)) * 32767) for v in mix))
    with wave.open(str(output), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm.tobytes())
    return resolved


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
    raw, prepared = audio / "music-raw.wav", audio / "music-prepared.wav"
    if tracks:
        labels = "".join(f"[t{i}]" for i in range(len(tracks)))
        filters.append(labels + f"amix=inputs={len(tracks)}:normalize=0:duration=longest,highpass=f=80,lowpass=f=6500,equalizer=f=1900:t=q:w=1:g=-3.5,afade=t=in:d=1.1,afade=t=out:st={max(0, duration - 2.4)}:d=2.4[bus]")
        command += ["-filter_complex", ";".join(filters), "-map", "[bus]", "-t", str(duration), "-c:a", "pcm_s24le", str(raw)]
        run(command)
        # A plan may request a bus level; legacy single-track gain remains compatible.
        if plan.get("bus_lufs") is not None:
            normalize(raw, prepared, rate, float(plan["bus_lufs"]), -6)
        else:
            run(["ffmpeg", "-y", "-v", "error", "-i", str(raw), "-c:a", "pcm_s24le", str(prepared)])
    else:
        run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", f"anullsrc=r={rate}:cl=stereo", "-t", str(duration), "-c:a", "pcm_s24le", str(prepared)])
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
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    project = args.project.resolve()
    score = json.loads((project / "score.json").read_text())
    audio = project / "audio"
    audio.mkdir(exist_ok=True)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    rate, duration = args.sample_rate, score["duration"]
    events = foley(project, score, audio / "foley.wav", rate)
    music, tracks, duck = music_bus(project, score, audio, rate, args.music, args.music_gain, args.music_plan)
    duck = {"threshold": .035, "ratio": 3., "attack_ms": 45, "release_ms": 480, **duck}
    compressor = f"threshold={float(duck['threshold'])}:ratio={float(duck['ratio'])}:attack={float(duck['attack_ms'])}:release={float(duck['release_ms'])}:detection=rms:link=average:makeup=1"
    filters = (
        f"[0:a]aresample={rate},aformat=channel_layouts=stereo,apad=whole_dur={duration},atrim=end={duration},asplit=2[v][key];"
        f"[1:a][key]sidechaincompress={compressor},asplit=2[m][evidence];"
        f"[2:a]aformat=channel_layouts=stereo[f];[v][m][f]amix=inputs=3:normalize=0:duration=first[out]"
    )
    premix = audio / "premix.wav"
    run(["ffmpeg", "-y", "-v", "error", "-i", str(args.voice), "-i", str(music), "-i", str(audio / "foley.wav"),
         "-filter_complex", filters, "-map", "[out]", "-t", str(duration), "-c:a", "pcm_s24le", str(premix),
         "-map", "[evidence]", "-t", str(duration), "-c:a", "pcm_s24le", str(audio / "music-ducked.wav")])
    before = normalize(premix, args.output, rate)
    receipt = {
        "voice_source": str(args.voice.resolve()), "voice_resynthesized": False,
        "voice_sha256": hashlib.sha256(args.voice.read_bytes()).hexdigest(),
        "score": "score.json", "score_sha256": hashlib.sha256((project / "score.json").read_bytes()).hexdigest(),
        "events": events, "music": str(args.music) if args.music else None,
        "music_plan": str(args.music_plan) if args.music_plan else None,
        "music_tracks": tracks, "ducking": duck, "sample_rate": rate, "channels": 2,
        "premix_measurement": before, "output_measurement": measure(args.output),
        "audio_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
        "full_listening": "pending", "tone_consistency": "unchanged_source_not_reapproved"
    }
    (audio / "mix-receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(args.output), "events": len(events), "duration": duration,
                      "music_stems": len(tracks), "sample_rate": rate, "voice_resynthesized": False}))


if __name__ == "__main__":
    main()
