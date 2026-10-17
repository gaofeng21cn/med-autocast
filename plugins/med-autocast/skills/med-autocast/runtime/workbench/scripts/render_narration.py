#!/usr/bin/env python3
"""Single-episode narration, exact segment selection, one registered voice baseline."""

import argparse, hashlib, json, os, re, subprocess, sys, tempfile, wave
from pathlib import Path
from workbench_config import (
    load_author_profile,
    load_backend_profile,
    select_audio_backend,
)
from media_backend import expand
from audio_baseline import normalize
from narration_splice import join


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


ANNOTATION = re.compile(r"<([^<>|]+)\|([^<>|]+)>")
VOXCPM_PINYIN = re.compile(r"^[a-zA-ZüÜvV]+[1-5]$")
# Standard Mandarin syllables, independent of the retired model's vocabulary.
PINYIN_SYLLABLES = set("""
a ai an ang ao ba bai ban bang bao bei ben beng bi bian biao bie bin bing bo bu
ca cai can cang cao ce cen ceng cha chai chan chang chao che chen cheng chi chong chou chu chua chuai chuan chuang chui chun chuo ci cong cou cu cuan cui cun cuo
da dai dan dang dao de dei den deng di dia dian diao die ding diu dong dou du duan dui dun duo
e ei en eng er fa fan fang fei fen feng fo fou fu
ga gai gan gang gao ge gei gen geng gong gou gu gua guai guan guang gui gun guo
ha hai han hang hao he hei hen heng hm hng hong hou hu hua huai huan huang hui hun huo
ji jia jian jiang jiao jie jin jing jiong jiu ju juan jue jun
ka kai kan kang kao ke kei ken keng kong kou ku kua kuai kuan kuang kui kun kuo
la lai lan lang lao le lei leng li lia lian liang liao lie lin ling liu lo long lou lu luan lun luo lv lve
m ma mai man mang mao me mei men meng mi mian miao mie min ming miu mo mou mu
n na nai nan nang nao ne nei nen neng ng ni nian niang niao nie nin ning niu nong nou nu nuan nuo nv nve
o ou pa pai pan pang pao pei pen peng pi pian piao pie pin ping po pou pu
qi qia qian qiang qiao qie qin qing qiong qiu qu quan que qun
ran rang rao re ren reng ri rong rou ru ruan rui run ruo
sa sai san sang sao se sen seng sha shai shan shang shao she shei shen sheng shi shou shu shua shuai shuan shuang shui shun shuo si song sou su suan sui sun suo
ta tai tan tang tao te teng ti tian tiao tie ting tong tou tu tuan tui tun tuo
wa wai wan wang wei wen weng wo wu xi xia xian xiang xiao xie xin xing xiong xiu xu xuan xue xun
ya yan yang yao ye yi yin ying yo yong you yu yuan yue yun za zai zan zang zao ze zei zen zeng zha zhai zhan zhang zhao zhe zhei zhen zheng zhi zhong zhou zhu zhua zhuai zhuan zhuang zhui zhun zhuo zi zong zou zu zuan zui zun zuo
""".split())
CMU_VOWELS = set("AA AE AH AO AW AY EH ER EY IH IY OW OY UH UW".split())
CMU_CONSONANTS = set("B CH D DH F G HH JH K L M N NG P R S SH T TH V W Y Z ZH".split())


def validate_annotations(value):
    # Empty or unfinished editorial controls must never become literal speech.
    remainder = ANNOTATION.sub("", value)
    if re.search(r"<[^<>]*\||\|[^<>]*>", remainder):
        raise ValueError("配音注音标记缺失文字、读音或闭合符号")


def tts_text(beat):
    """Keep editorial text separate from backend-specific pronunciation input."""
    value = beat.get("tts_text", beat["text"])
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"声段 {beat['id']} 的配音专用文本为空")
    validate_annotations(value)
    if ANNOTATION.sub(lambda m: m[1], value) != beat["text"]:
        raise ValueError(f"声段 {beat['id']} 的注音还原后与正文不同；请保留同一正文")
    return value


def narration_signature(beats):
    return [(b["id"], b["text"], tts_text(b)) for b in beats]


def audio_rejected(meta):
    # Pending review is consumable; an explicit rejection is not a valid take.
    for field in ("pronunciation_review", "full_listening", "tone_consistency"):
        review = meta.get(field)
        status = review.get("status") if isinstance(review, dict) else review
        if status in ("rejected", "failed"):
            return True
    return False


def pronunciation_controls(value):
    """Return explicit pronunciation intent without allowing a backend to read markup."""
    return [
        {"text": match.group(1), "pronunciation": match.group(2)}
        for match in ANNOTATION.finditer(value)
    ]


def _voxcpm_pinyin_token(token, word):
    """Normalize one annotated syllable to VoxCPM's native brace syntax.

    VoxCPM's public demo documents lowercase numbered pinyin inside braces,
    for example ``{ni3}{hao3}``.  IndexTTS's ``V`` spelling for ``j/q/x``
    is accepted in old receipts, but VoxCPM should receive standard ``u``
    there (``xue4``), while ``v`` remains the ASCII spelling of ``ü`` in
    ``lü4``/``nü3``.
    """
    value = token.strip().replace("Ü", "ü").replace("V", "v")
    if not VOXCPM_PINYIN.fullmatch(value):
        raise ValueError(
            f"VoxCPM 原生拼音控制格式无效 {token!r}（{word}）；"
            "请使用带 1-5 声调的拼音，例如 HAI2"
        )
    value = value.lower().replace("ü", "v")
    if value.startswith(("j", "q", "x")):
        value = value.replace("v", "u")
    if value[:-1] not in PINYIN_SYLLABLES:
        raise ValueError(f"VoxCPM 原生拼音音节无效 {token!r}（{word}）")
    return value


def voxcpm_text(value):
    """Convert editorial ``<词|拼音>`` annotations to native VoxCPM input.

    The Chinese word is intentionally replaced by one brace-wrapped syllable
    per requested phone.  This is the syntax used by the upstream VoxCPM
    demo; the editorial annotation and the generated model input are kept
    separate in the receipt so subtitles remain the approved Chinese text.
    """
    def replace(match):
        word, phones = match.groups()
        tokens = phones.split()
        if not tokens:
            raise ValueError(f"VoxCPM 原生拼音控制缺少读音（{word}）")
        # Numbers and units may also carry an explicit Mandarin reading, while
        # the editorial text retains the original digits (e.g. <5mg|WU3 HAO2 KE4>).
        numbered = all(VOXCPM_PINYIN.fullmatch(token) for token in tokens)
        if re.search(r"[\u3400-\u9fff]", word) or numbered and all(
            re.sub(r"^([jqx])v", r"\1u", token.lower().replace("ü", "v"))[:-1] in PINYIN_SYLLABLES
            for token in tokens
        ):
            return "".join(f"{{{_voxcpm_pinyin_token(token, word)}}}" for token in tokens)
        tokens = [token.upper() for token in tokens]
        for token in tokens:
            if token not in CMU_CONSONANTS and not (
                token[-1:] in ("0", "1", "2") and token[:-1] in CMU_VOWELS
            ):
                raise ValueError(f"VoxCPM 英文 CMU 音素无效 {token!r}（{word}）")
        return "{" + " ".join(tokens) + "}"

    validate_annotations(value)
    return ANNOTATION.sub(replace, value)


def prepare_model_text(value, definition, model_root=None):
    """Resolve model input while keeping the original annotated text in the receipt.

    VoxCPM2's upstream demo documents native phoneme input as numbered pinyin
    inside braces (``{ni3}{hao3}``).  Editorial annotations stay in ``tts_text``;
    only the backend-specific ``model_text`` is converted to that syntax.
    """
    if definition == "voxcpm_2":
        return voxcpm_text(value)
    validate_annotations(value)
    if ANNOTATION.search(value):
        raise ValueError("当前后端不支持此原生发音控制；请使用 VoxCPM2，不会静默去掉注音")
    return value


def synthesize(
    root,
    narration,
    output,
    series=None,
    selected=None,
    force=False,
    direction_override=None,
    reference_override=None,
    language_override=None,
    author_profile_override=None,
    gap_seconds=0.26,
):
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
    profile, author = load_author_profile(
        root=root,
        series_id=series,
        profile_path=author_profile_override,
    )
    _, backends = load_backend_profile(root=root)
    backend = select_audio_backend(author, backends)
    spec = expand(backends["audio"][backend])
    voice = author.get("voice", {})

    def locate(v):
        return str((root / Path(v).expanduser()).resolve())

    settings = {
        "backend": backend,
        "definition": spec["definition"],
        "direction": direction_override or voice.get("direction", "平静、自然、清晰"),
        "language": language_override or voice.get("language", "zh"),
        "seed": 1601,
    }
    if spec["definition"] == "voxcpm_2":
        runtime = Path(locate(spec["root"]))
        model = Path(locate(spec["model_root"]))
        settings.update(
            reference=locate(reference_override or voice["reference_audio"]),
            model_root=str(model),
            runtime_root=str(runtime),
            device=spec.get("device", "mps" if sys.platform == "darwin" else "cpu"),
            runtime_profile=spec.get("runtime_profile", {}),
            pronunciation_control="voxcpm_native_pinyin_braces_with_required_listening",
        )
        settings["reference_sha256"] = hashlib.sha256(Path(settings["reference"]).read_bytes()).hexdigest()
        settings["model_config_sha256"] = hashlib.sha256((model / "config.json").read_bytes()).hexdigest()
        settings["worker_sha256"] = hashlib.sha256(Path(__file__).with_name("voxcpm_worker.py").read_bytes()).hexdigest()
        settings["model_files"] = {
            name: {"size": (model / name).stat().st_size, "mtime_ns": (model / name).stat().st_mtime_ns}
            for name in ("model.safetensors", "audiovae.pth") if (model / name).is_file()
        }
        settings["runtime_metadata"] = {
            str(p.relative_to(runtime)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(runtime.glob(".venv/lib/python*/site-packages/voxcpm-*.dist-info/METADATA"))
        }
        if settings["runtime_profile"].get("normalize", False):
            raise ValueError("VoxCPM2 使用审定配音输入，必须 normalize=false，避免破坏原生音素")
        python = os.path.abspath(os.path.expanduser(spec.get("python", str(runtime / ".venv/bin/python"))))
    elif spec["definition"] == "edge_tts":
        settings.update(
            voice=spec.get("voice", "zh-CN-XiaoyiNeural"),
            rate=voice.get("rate", "-8%"),
            pitch=voice.get("pitch", "+0Hz"),
        )
        python = sys.executable
    else:
        raise ValueError("当前统一旁白入口仅支持已登记的 VoxCPM2 或 Edge；不会静默回退")
    jobs = []
    records = []
    for b in rows:
        spoken = tts_text(b)
        actual = prepare_model_text(spoken, spec["definition"], locals().get("model"))
        controls = pronunciation_controls(spoken)
        cache_input = {"text": b["text"], "settings": settings}
        if spoken != b["text"]:
            cache_input["tts_text"] = spoken
        if actual != spoken:
            cache_input["model_text"] = actual
        if controls:
            cache_input["pronunciation_controls"] = controls
        key = digest(cache_input)
        target = output / "segments" / f"{key}.wav"
        receipt = target.with_suffix(".json")
        valid = target.is_file() and receipt.is_file()
        if valid:
            meta = json.loads(receipt.read_text())
            valid = (
                meta.get("sha256") == hashlib.sha256(target.read_bytes()).hexdigest()
                and meta.get("tts_text", meta.get("text")) == spoken
                and meta.get("model_text", meta.get("tts_text", meta.get("text"))) == actual
                and not audio_rejected(meta)
            )
        if selected and b["id"] not in selected and not valid:
            raise ValueError(
                f"未选择的声段 {b['id']} 没有与当前文本和声线匹配的缓存；请先完整配音"
            )
        if not valid or (force and (not selected or b["id"] in selected)):
            target.parent.mkdir(exist_ok=True)
            jobs.append({**b, "model_text": actual, "output": str(target), "key": key})
        records.append({
            **b,
            "model_text": actual,
            "audio": str(target),
            "cache_key": key,
            "pronunciation_controls": controls,
            "control_status": "manual_review_required" if controls else "none",
        })
    if jobs:
        # Synthesize into a private staging directory; failed retries preserve successful takes.
        staging = tempfile.TemporaryDirectory(prefix="mac-takes-", dir=output)
        try:
            originals = {b["key"]: Path(b["output"]) for b in jobs}
            for b in jobs:
                b["output"] = str(Path(staging.name) / (b["key"] + ".wav"))
            if spec["definition"] == "voxcpm_2":
                with tempfile.TemporaryDirectory(prefix="mac-narration-") as tmp:
                    job = Path(tmp) / "job.json"
                    save(job, {**settings, "beats": jobs})
                    subprocess.run(
                        [python, str(Path(__file__).with_name("voxcpm_worker.py")), "--job", str(job)],
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
                        "tts_text": tts_text(b),
                        "model_text": b["model_text"],
                        "pronunciation_review": {
                            "status": "pending",
                            "required": bool(pronunciation_controls(tts_text(b))),
                            "controls": pronunciation_controls(tts_text(b)),
                            "method": "manual_full_listening",
                        },
                        "pronunciation_controls": pronunciation_controls(tts_text(b)),
                        "control_status": (
                            "manual_review_required" if pronunciation_controls(tts_text(b))
                            else "none"
                        ),
                        "baseline": settings,
                        "full_listening": "pending",
                    },
                )
        finally:
            staging.cleanup()
    # Keep the tested splice implementation as the single source of truth.
    # A second inline implementation had drifted from narration_splice.join;
    # fixes made there therefore did not necessarily reach fresh synthesis.
    rate = 24000
    if not 0 <= gap_seconds <= 3:
        raise ValueError("声段停顿须在 0 到 3 秒之间")
    source_paths = [Path(b["audio"]) for b in records]
    for b, path in zip(records, source_paths):
        if not path.is_file():
            raise ValueError(f"声段 {b['id']} 音频不存在，未替换当前整轨: {path}")
    with tempfile.TemporaryDirectory(prefix="mac-track-", dir=output) as tmp:
        raw = Path(tmp) / "narration.wav"
        splice_report = join(source_paths, raw, rate=rate,
                             gap_ms=round(gap_seconds * 1000),
                             lead_ms=320, tail_ms=700)
        for b, row in zip(records, splice_report):
            b["start"] = row["placed_at"]
            b["end"] = row["placed_end"]
            b["trimmed_head_seconds"] = row["trim_start"]
            b["trimmed_tail_seconds"] = round(row["duration"] - row["trim_end"], 3)
            b["source_sample_rate"] = row["source_sample_rate"]
            b["source_sha256"] = hashlib.sha256(Path(b["audio"]).read_bytes()).hexdigest()
            row["id"] = b["id"]
            row["source_sha256"] = b["source_sha256"]
            row["decoded_sample_rate"] = rate
            row["preserved_frames"] = row["placed_end_frame"] - row["placed_start_frame"]
        with wave.open(str(raw), "rb") as w:
            if w.getnchannels() != 1 or w.getframerate() != rate:
                raise ValueError("旁白拼接输出不是 24 kHz 单声道 PCM")
            raw_duration = w.getnframes() / w.getframerate()
        normalized = Path(tmp) / "narration-normalized.wav"
        normalize(raw, normalized)
        with wave.open(str(normalized), "rb") as w:
            actual_duration = w.getnframes() / w.getframerate()
        if abs(actual_duration - raw_duration) > 1 / rate:
            raise ValueError("归一化改变音轨时长，未替换当前整轨")
        raw.replace(output / "narration.wav")
        normalized.replace(output / "narration-normalized.wav")
    normalized = output / "narration-normalized.wav"
    result = {
        "source": str(Path(narration).resolve()),
        "author_profile": str(profile),
        "backend": backend,
        "baseline": settings,
        "duration": round(actual_duration, 6),
        "audio": str(normalized),
        "beats": records,
        "generated": [b["id"] for b in jobs],
        "reused": [b["id"] for b in records if b["id"] not in [j["id"] for j in jobs]],
        "full_listening": "pending",
        "tone_consistency": "pending",
    }
    result["splice"] = {
        "schema": "narration_splice/v2",
        "policy": "resample_correctly_preserve_all_source_samples",
        "gap_seconds": round(gap_seconds, 6),
        "lead_seconds": 0.32,
        "tail_seconds": 0.7,
        "takes": splice_report,
        "raw_sha256": hashlib.sha256((output / "narration.wav").read_bytes()).hexdigest(),
        "normalized_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
        "review": "拼接处应可听到完整首字；实际听辨仍待审",
    }
    save(output / "narration_beats.json", result)
    save(output / "pronunciation-review.json", {
        "schema": "narration_pronunciation_review/v1",
        "source": result["source"],
        "voice": str(normalized),
        "voice_sha256": hashlib.sha256(normalized.read_bytes()).hexdigest(),
        "status": "pending",
        "method": "先审听各声段原音，再复核最终混音；注音输入与ASR同字转写均不证明实际读音",
        "beats": [{
            "id": b["id"], "text": b["text"], "tts_text": tts_text(b),
            "model_text": b["model_text"],
            "audio": b["audio"],
            "sha256": hashlib.sha256(Path(b["audio"]).read_bytes()).hexdigest(),
            "start": b["start"], "end": b["end"],
            "requested_pronunciations": pronunciation_controls(tts_text(b)),
            "control_status": "manual_review_required" if pronunciation_controls(tts_text(b)) else "none",
            "review": json.loads(Path(b["audio"]).with_suffix(".json").read_text()).get(
                "pronunciation_review", {"status": "pending"}
            ),
        } for b in records],
    })
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
