#!/usr/bin/env python3
"""Single-episode narration, exact segment selection, one registered voice baseline."""

import argparse, hashlib, json, os, subprocess, sys, tempfile, wave
from pathlib import Path
from workbench_config import (
    load_author_profile,
    load_backend_profile,
    select_audio_backend,
)
from media_backend import expand
from audio_baseline import normalize


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def synthesize(root, narration, output, series=None, selected=None, force=False):
    root = Path(root).resolve()
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    rows = json.loads(Path(narration).read_text())["beats"]
    ids = [b["id"] for b in rows]
    if (
        not rows
        or len(ids) != len(set(ids))
        or any(not str(b.get("text", "")).strip() for b in rows)
    ):
        raise ValueError("旁白声段缺失、重复或为空")
    if selected and set(selected) - set(ids):
        raise ValueError("指定声段不存在")
    profile, author = load_author_profile(root=root, series_id=series)
    _, backends = load_backend_profile(root=root)
    backend = select_audio_backend(author, backends)
    spec = expand(backends["audio"][backend])
    voice = author.get("voice", {})

    def locate(v):
        return str((root / Path(v).expanduser()).resolve())

    settings = {
        "backend": backend,
        "definition": spec["definition"],
        "direction": voice.get("direction", "平静、自然、清晰"),
        "language": voice.get("language", "zh"),
        "seed": 1601,
        "emotion_alpha": 0.6,
        "duration_factor": 1.05,
    }
    if spec["definition"] == "indextts_2_5":
        model = Path(locate(spec["model_root"]))
        runtime = Path(locate(spec["root"]))
        source = runtime / "src" if (runtime / "src/indextts").exists() else runtime
        settings.update(
            reference=locate(voice["reference_audio"]),
            model_root=str(model),
            runtime_root=str(source),
            device=spec.get("device", "mps" if sys.platform == "darwin" else "cpu"),
        )
        settings["reference_sha256"] = hashlib.sha256(
            Path(settings["reference"]).read_bytes()
        ).hexdigest()
        settings["model_config_sha256"] = hashlib.sha256(
            (model / "config.yaml").read_bytes()
        ).hexdigest()
        python = os.path.abspath(
            os.path.expanduser(spec.get("python", str(runtime / ".venv/bin/python")))
        )
    elif spec["definition"] == "edge_tts":
        settings.update(
            voice=spec.get("voice", "zh-CN-XiaoyiNeural"),
            rate=voice.get("rate", "-8%"),
            pitch=voice.get("pitch", "+0Hz"),
        )
        python = sys.executable
    else:
        raise ValueError(
            "当前统一旁白入口仅支持已登记的 IndexTTS 或 Edge；不会静默回退"
        )
    jobs = []
    records = []
    for b in rows:
        key = digest({"text": b["text"], "settings": settings})
        target = output / "segments" / f"{key}.wav"
        receipt = target.with_suffix(".json")
        valid = target.is_file() and receipt.is_file()
        if valid:
            meta = json.loads(receipt.read_text())
            valid = (
                meta.get("sha256") == hashlib.sha256(target.read_bytes()).hexdigest()
            )
        if selected and b["id"] not in selected and not valid:
            raise ValueError(
                f"未选择的声段 {b['id']} 没有与当前文本和声线匹配的缓存；请先完整配音"
            )
        if not valid or (force and (not selected or b["id"] in selected)):
            target.parent.mkdir(exist_ok=True)
            jobs.append({**b, "output": str(target), "key": key})
        records.append({**b, "audio": str(target), "cache_key": key})
    if jobs:
        # Synthesize into a private staging directory; failed retries preserve successful takes.
        staging = tempfile.TemporaryDirectory(prefix="mac-takes-", dir=output)
        try:
            originals = {b["key"]: Path(b["output"]) for b in jobs}
            for b in jobs:
                b["output"] = str(Path(staging.name) / (b["key"] + ".wav"))
            if spec["definition"] == "indextts_2_5":
                with tempfile.TemporaryDirectory(prefix="mac-narration-") as tmp:
                    job = Path(tmp) / "job.json"
                    save(job, {**settings, "beats": jobs})
                    subprocess.run(
                        [
                            python,
                            str(Path(__file__).with_name("narration_worker.py")),
                            "--job",
                            str(job),
                        ],
                        cwd=settings["runtime_root"],
                        check=True,
                    )
            else:
                import asyncio
                from render_edge_tts import synthesize as edge

                for b in jobs:
                    raw = Path(b["output"]).with_suffix(".mp3")
                    asyncio.run(
                        edge(
                            b["text"],
                            settings["voice"],
                            raw,
                            settings["rate"],
                            settings["pitch"],
                            "+0%",
                        )
                    )
                    subprocess.run(
                        [
                            "ffmpeg",
                            "-y",
                            "-v",
                            "error",
                            "-i",
                            str(raw),
                            "-ar",
                            "24000",
                            "-ac",
                            "1",
                            b["output"],
                        ],
                        check=True,
                    )
            for b in jobs:
                subprocess.run(
                    ["ffmpeg", "-v", "error", "-i", b["output"], "-f", "null", "-"],
                    check=True,
                )
            for b in jobs:
                candidate = Path(b["output"])
                target = originals[b["key"]]
                if target.exists():
                    history = (
                        output
                        / "takes"
                        / hashlib.sha256(target.read_bytes()).hexdigest()
                    )
                    history.mkdir(parents=True, exist_ok=True)
                    import shutil

                    shutil.copy2(target, history / "audio.wav")
                    if target.with_suffix(".json").exists():
                        shutil.copy2(
                            target.with_suffix(".json"), history / "receipt.json"
                        )
                candidate.replace(target)
                save(
                    target.with_suffix(".json"),
                    {
                        "cache_key": b["key"],
                        "sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
                        "text": b["text"],
                        "baseline": settings,
                        "full_listening": "pending",
                    },
                )
        finally:
            staging.cleanup()
    # Convert each source explicitly; never assume a model's sample rate.
    pcm = []
    cursor = 0.65
    rate = 24000
    for b in records:
        data = subprocess.check_output(
            [
                "ffmpeg",
                "-v",
                "error",
                "-i",
                b["audio"],
                "-ar",
                str(rate),
                "-ac",
                "1",
                "-f",
                "s16le",
                "-",
            ]
        )
        b["start"] = round(cursor, 6)
        b["end"] = round(cursor + len(data) / (rate * 2), 6)
        cursor = b["end"] + 0.65
        pcm.extend([data, b"\0" * round(rate * 0.65) * 2])
    with tempfile.TemporaryDirectory(prefix="mac-track-", dir=output) as tmp:
        raw = Path(tmp) / "narration.wav"
        with wave.open(str(raw), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(
                b"\0" * round(rate * 0.65) * 2
                + b"".join(pcm)
                + b"\0" * round(rate * 0.7) * 2
            )
        normalized = Path(tmp) / "narration-normalized.wav"
        normalize(raw, normalized)
        raw.replace(output / "narration.wav")
        normalized.replace(output / "narration-normalized.wav")
    normalized = output / "narration-normalized.wav"
    result = {
        "source": str(Path(narration).resolve()),
        "author_profile": str(profile),
        "backend": backend,
        "baseline": settings,
        "duration": round(cursor + 0.7, 6),
        "audio": str(normalized),
        "beats": records,
        "generated": [b["id"] for b in jobs],
        "reused": [b["id"] for b in records if b["id"] not in [j["id"] for j in jobs]],
        "full_listening": "pending",
        "tone_consistency": "pending",
    }
    save(output / "narration_beats.json", result)
    return result


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--workspace",
        type=Path,
        default=Path(os.environ.get("MED_AUTOCAST_WORKSPACE_ROOT", ".")),
    )
    p.add_argument("--narration", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--series")
    p.add_argument("--beat", action="append")
    p.add_argument("--force", action="store_true")
    a = p.parse_args()
    r = synthesize(a.workspace, a.narration, a.output, a.series, a.beat, a.force)
    print(
        json.dumps(
            {k: r[k] for k in ["backend", "duration", "generated", "reused", "audio"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
