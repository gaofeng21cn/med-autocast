#!/usr/bin/env python3
"""Mix an unchanged voice with event-aligned paper sounds. No TTS or voice fallback."""

import argparse, array, json, math, random, subprocess, wave
from pathlib import Path


def run(args):
    return subprocess.run(args, check=True, capture_output=True, text=True)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--project", type=Path, required=True)
    p.add_argument("--voice", type=Path, required=True)
    p.add_argument("--music", type=Path)
    p.add_argument("--music-gain", type=float, default=0.085)
    p.add_argument("--output", type=Path, required=True)
    args = p.parse_args()
    score = json.loads((args.project / "score.json").read_text())
    rate = 24000
    length = round(score["duration"] * rate)
    mix = array.array("f", [0]) * length
    resolved = []
    for i, event in enumerate(score["sounds"]):
        shot = next(s for s in score["shots"] if s["id"] == event["shot"])
        time = shot["start"] + shot["events"][event["event"]] + event.get("offset", 0)
        resolved.append(dict(event, time=time))
        if event.get("asset_id"):
            manifest = json.loads((args.project / "asset_manifest.json").read_text())
            source = next(
                x for x in manifest["assets"] if x["asset_id"] == event["asset_id"]
            )
            decoded = subprocess.check_output(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(args.project / source["path"]),
                    "-ar",
                    str(rate),
                    "-ac",
                    "1",
                    "-f",
                    "f32le",
                    "-",
                ]
            )
            samples = array.array("f")
            samples.frombytes(decoded)
            start = round(time * rate)
            for k, value in enumerate(samples):
                if 0 <= start + k < length:
                    mix[start + k] += value * event.get("gain", 1)
            resolved[-1]["source"] = source["path"]
            continue
        duration = 0.17 if event["kind"] == "stamp" else 0.44
        rng = random.Random(1701 + i)
        lo = slow = 0.0
        start = round(time * rate)
        n = round(duration * rate)
        for k in range(n):
            noise = rng.uniform(-1, 1)
            lo += 0.45 * (noise - lo)
            slow += 0.08 * (lo - slow)
            band = lo - slow
            if event["kind"] == "stamp":
                v = (
                    math.sin(k / rate * 2 * math.pi * 155) * math.exp(-k / rate * 43)
                    + band * 0.16
                ) * 0.026
            else:
                v = band * math.sin(math.pi * k / n) ** 2 * 0.023
            pos = start + k
            if 0 <= pos < length:
                mix[pos] += v * event.get("gain", 1)
    pcm = array.array("h", (round(max(-1, min(1, v)) * 32767) for v in mix))
    audio = args.project / "audio"
    audio.mkdir(exist_ok=True)
    with wave.open(str(audio / "foley.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(pcm.tobytes())
    duration = score["duration"]
    premix = audio / "premix.wav"
    filters = f"[0:a]aresample={rate},aformat=channel_layouts=mono[v];[1:a]aresample={rate},aformat=channel_layouts=mono,volume={args.music_gain},afade=t=in:d=1.2,afade=t=out:st={max(0, duration - 2.5)}:d=2.5[m];[v][m][2:a]amix=inputs=3:normalize=0:duration=first[out]"
    music_input = (
        ["-stream_loop", "-1", "-i", str(args.music)]
        if args.music
        else ["-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono"]
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(args.voice),
            *music_input,
            "-i",
            str(audio / "foley.wav"),
            "-filter_complex",
            filters,
            "-map",
            "[out]",
            "-t",
            str(duration),
            str(premix),
        ]
    )
    probe = run(
        [
            "ffmpeg",
            "-hide_banner",
            "-i",
            str(premix),
            "-af",
            "loudnorm=I=-16:TP=-1:LRA=11:print_format=json",
            "-f",
            "null",
            "-",
        ]
    )
    loud = json.JSONDecoder().raw_decode(probe.stderr[probe.stderr.rfind("{") :])[0]
    normal = "loudnorm=I=-16:TP=-1:LRA=11:linear=true:measured_I={input_i}:measured_TP={input_tp}:measured_LRA={input_lra}:measured_thresh={input_thresh}:offset={target_offset}".format(
        **loud
    )
    run(
        [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-i",
            str(premix),
            "-af",
            normal,
            "-ar",
            str(rate),
            str(args.output),
        ]
    )
    (audio / "mix-receipt.json").write_text(
        json.dumps(
            {
                "voice_source": str(args.voice),
                "voice_resynthesized": False,
                "score": "score.json",
                "events": resolved,
                "music": str(args.music),
                "sample_rate": rate,
                "full_listening": "pending",
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    print(
        json.dumps(
            {"output": str(args.output), "events": len(resolved), "duration": duration}
        )
    )


if __name__ == "__main__":
    main()
