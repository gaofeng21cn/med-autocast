#!/usr/bin/env python3
"""One local project entry: existing creative code remains the director's source."""

from __future__ import annotations
import argparse, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import yaml
from workbench_config import load_author_profile

BUNDLE = Path(__file__).resolve().parents[1]


def read(p):
    return json.loads(Path(p).read_text())


def save(p, v):
    p = Path(p)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(v, ensure_ascii=False, indent=2) + "\n")


def sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def stamp():
    return time.strftime("%Y%m%dT%H%M%S") + "-" + str(time.time_ns() % 1000000)


def safe_id(s):
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]*", s):
        raise ValueError("ID 仅允许字母、数字、下划线和连字符")
    return s


def run(cmd, cwd, workspace):
    subprocess.run(
        [str(x) for x in cmd],
        cwd=cwd,
        check=True,
        env=dict(
            os.environ,
            MED_AUTOCAST_WORKSPACE_ROOT=str(workspace),
            PYTHONDONTWRITEBYTECODE="1",
        ),
    )


def get_project(a):
    if not a.project:
        raise ValueError("需要 --project 指向明确单集目录")
    p = a.project.resolve()
    config = read(p / "project.json")
    if config.get("schema") != "paper_project/v1":
        raise ValueError("不是已登记的纸剧场项目")
    return p, config


def register(workspace, p, c):
    path = workspace / "workbench.yaml"
    data = yaml.safe_load(path.read_text())
    series = data.setdefault("series", {})
    row = series.setdefault(
        c["series_id"],
        {
            "title": c["series_id"],
            "production_root": str(p.parent.relative_to(workspace)),
            "content_root": f"content/{c['series_id']}",
            "publish_root": f"publish/{c['series_id']}",
            "episode_count": 0,
            "status": "paper_theatre_in_progress",
        },
    )
    row.setdefault("episodes", {})[c["episode_id"]] = {
        "project": str(p.relative_to(workspace)),
        "entry": "project.json",
    }
    row["episode_count"] = max(row.get("episode_count", 0), len(row["episodes"]))
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False))


def adopt(a):
    p = a.project.resolve()
    safe_id(a.series)
    safe_id(a.episode)
    if not p.is_relative_to(a.workspace):
        raise ValueError("项目登记需位于工作区内")
    if (p / "project.json").exists():
        raise ValueError("项目已登记；使用 inspect，保留原描述")
    for f in ["score.json", "asset_manifest.json", "index.html", "package.json"]:
        if not (p / f).is_file():
            raise ValueError(f"缺少 {f}")
    score = read(p / "score.json")
    narration = p / "preproduction/narration.json"
    beats = read(narration).get("beats", []) if narration.exists() else []
    c = {
        "schema": "paper_project/v1",
        "series_id": a.series,
        "episode_id": a.episode,
        "title": a.title or a.episode,
        "score": "score.json",
        "assets": "asset_manifest.json",
        "narration": "preproduction/narration.json",
        "voice": "audio/narration-normalized.wav",
        "audio": "audio.wav",
        "entry": "index.html",
        "beat_shots": {b["id"]: s["id"] for b, s in zip(beats, score["shots"])},
        "kit_version": "1.0.0",
    }
    if beats and len(beats) != len(score["shots"]):
        c["beat_shots"] = {}
    save(p / "project.json", c)
    register(a.workspace, p, c)
    return {
        "project": str(p),
        "registered": True,
        "series": a.series,
        "episode": a.episode,
    }


def initialize(a):
    p = a.project.resolve()
    if not p.is_relative_to(a.workspace):
        raise ValueError("项目需要位于工作区内")
    safe_id(a.series)
    safe_id(a.episode)
    if p.exists() and any(p.iterdir()):
        raise ValueError("init 只接受空目录；已有作品使用 adopt")
    source = (
        a.from_project.resolve()
        if a.from_project
        else BUNDLE / "templates/animation/paper_theatre"
    )
    if a.from_project:
        from check_animation_assets import check_assets

        check_assets(source / "asset_manifest.json")
        for asset in read(source / "asset_manifest.json")["assets"]:
            for key in [
                "path",
                "prompt_ref",
                "generation_receipt",
                "license_evidence",
                "medical_reference",
            ]:
                if asset.get(key) and not (
                    source / asset[key]
                ).resolve().is_relative_to(source):
                    raise ValueError(
                        "复制模板需要自包含的素材与来源证据：" + asset[key]
                    )
    p.mkdir(parents=True, exist_ok=True)
    for name in [
        "src",
        "scripts",
        "tests",
        "compare.html",
        "kit-lock.json",
        "README.md",
        "package.json",
        "package-lock.json",
        "tsconfig.json",
        "index.html",
        "asset_manifest.json",
        "score.json",
        "brand.json",
        "assets",
        "preproduction",
    ]:
        f = source / name
        if f.is_dir():
            shutil.copytree(
                f,
                p / name,
                ignore=shutil.ignore_patterns("node_modules", "__pycache__"),
                dirs_exist_ok=True,
            )
        elif f.is_file():
            shutil.copy2(f, p / name)
    if not (p / "asset_manifest.json").exists():
        save(
            p / "asset_manifest.json",
            {"schema": "medical_animation_assets/v1", "assets": [], "shots": []},
        )
    if not (p / "score.json").exists():
        raise ValueError("模板缺少 score.json")
    (p / "preproduction").mkdir(exist_ok=True)
    if a.narration:
        shutil.copy2(a.narration, p / "preproduction/narration.json")
    else:
        (p / "preproduction").mkdir(exist_ok=True)
    config = yaml.safe_load((a.workspace / "workbench.yaml").read_text())
    profile, author = load_author_profile(
        root=a.workspace,
        series_id=a.series if a.series in config.get("series", {}) else None,
    )
    brand = author.get("brand", {})
    save(
        p / "brand.json",
        {
            "profile": str(profile),
            "text": brand.get("overlay_text", ""),
            "ink": "#254a48",
            "accent": "#b55243",
            "paper": "#f5eddc",
            "enabled": brand.get("enabled", bool(brand.get("overlay_text"))),
        },
    )
    return adopt(a)


def inspect(a):
    p, c = get_project(a)
    score = read(p / c["score"])
    manifest = read(p / c["assets"])
    return {
        "project": str(p),
        "series": c["series_id"],
        "episode": c["episode_id"],
        "shots": [s["id"] for s in score["shots"]],
        "assets": len(manifest["assets"]),
        "duration": score["duration"],
        "kit_version": c["kit_version"],
        "voice_exists": (p / c["voice"]).exists(),
        "mix_exists": (p / c["audio"]).exists(),
        "latest_render": read(p / "out/current.json")
        if (p / "out/current.json").exists()
        else None,
        "commands": [
            "assets",
            "library",
            "narrate",
            "retime",
            "align",
            "captions",
            "build",
            "preview",
            "mix",
            "render",
            "package",
        ],
    }


def build(a):
    p, c = get_project(a)
    if not (p / "node_modules/typescript").exists():
        run(["npm", "ci", "--no-audit", "--no-fund"], p, a.workspace)
    run(["npm", "run", "build"], p, a.workspace)
    inputs = {
        str(f.relative_to(p)): sha(f)
        for folder in ["src", "scripts"]
        for f in sorted((p / folder).rglob("*"))
        if f.is_file() and "__pycache__" not in f.parts
    }
    for item in read(p / c["assets"]).get("assets", []):
        asset = p / item["path"]
        if not asset.is_file():
            raise ValueError("素材不存在：" + item["path"])
        inputs[item["path"]] = sha(asset)
    for f in [
        "score.json",
        "asset_manifest.json",
        "brand.json",
        "package-lock.json",
        "index.html",
    ]:
        if (p / f).exists():
            inputs[f] = sha(p / f)
    save(
        p / "dist/build-receipt.json",
        {"inputs": inputs, "bundle_sha256": sha(p / "dist/film.js")},
    )
    return {"status": "built", "project": str(p), "entry": c["entry"]}


def assert_built(p):
    if not (p / "dist/build-receipt.json").exists():
        raise ValueError("请先 build，生成绑定当前源码的 JS")
    r = read(p / "dist/build-receipt.json")
    actual = {
        str(f.relative_to(p))
        for folder in ["src", "scripts"]
        for f in (p / folder).rglob("*")
        if f.is_file() and "__pycache__" not in f.parts
    }
    if actual != {k for k in r["inputs"] if k.startswith(("src/", "scripts/"))}:
        raise ValueError("源码文件列表已变，请重新 build")
    for name, value in r["inputs"].items():
        if not (p / name).exists() or sha(p / name) != value:
            raise ValueError(f"构建已过期：{name}；请重新 build")
    if sha(p / "dist/film.js") != r["bundle_sha256"]:
        raise ValueError("构建文件已变动，请重新 build")


def assert_narration(p, c):
    receipt = p / "audio/narration_beats.json"
    if receipt.exists():
        signature = lambda beats: [(b["id"], b["text"]) for b in beats]
        if signature(read(receipt)["beats"]) != signature(
            read(p / c["narration"])["beats"]
        ):
            raise ValueError("旁白文稿已变化，请重新配音改动声段")


def narrate(a):
    p, c = get_project(a)
    from render_narration import synthesize

    result = synthesize(
        a.workspace, p / c["narration"], p / "audio", c["series_id"], a.beat, a.force
    )
    if (p / "audio/mix-receipt.json").exists():
        save(p / "audio/needs-remix.json", {"reason": "narration_updated"})
    return {
        k: result[k] for k in ["audio", "duration", "backend", "generated", "reused"]
    }


def retime(a):
    p, c = get_project(a)
    score = read(p / c["score"])
    receipt = read(p / "audio/narration_beats.json")
    mapping = c["beat_shots"]
    byshot = {mapping.get(b["id"]): b for b in receipt["beats"]}
    if set(byshot) != set(s["id"] for s in score["shots"]):
        raise ValueError("请在 project.json 的 beat_shots 中明确声段与镜头关系")
    ordered = [byshot[s["id"]] for s in score["shots"]]
    cuts = (
        [0]
        + [
            (ordered[i - 1]["end"] + ordered[i]["start"]) / 2
            for i in range(1, len(ordered))
        ]
        + [receipt["duration"]]
    )
    for i, s in enumerate(score["shots"]):
        s.update(start=cuts[i], end=cuts[i + 1])
    score["duration"] = receipt["duration"]
    # Captions are editorial text; whole-utterance timing is only a review draft.
    score["cues"] = [
        {"start": b["start"], "end": b["end"], "text": b["text"]}
        for b in receipt["beats"]
    ]
    overflow = [
        s["id"]
        for s in score["shots"]
        if max(s["events"].values(), default=0) > s["end"] - s["start"]
    ]
    save(p / "score.proposed.json", score)
    if overflow:
        raise ValueError(
            "新声音短于镜头动作，请调整这些镜头的事件后再采用 score.proposed.json："
            + ",".join(overflow)
        )
    archive = p / "history" / stamp()
    archive.mkdir(parents=True)
    shutil.copy2(p / c["score"], archive / "score.json")
    save(p / c["score"], score)
    save(
        p / "audio/timing-receipt.json",
        {
            "voice_sha256": sha(p / c["voice"]),
            "caption_status": "draft",
            "score_sha256": sha(p / c["score"]),
        },
    )
    return {
        "status": "retimed",
        "duration": score["duration"],
        "caption_status": "draft",
        "note": "未拉伸动作，需校准句级字幕",
    }


def align(a):
    p, c = get_project(a)
    run(
        [
            a.python,
            BUNDLE / "scripts/align_narration.py",
            "--receipt",
            p / "audio/narration_beats.json",
            "--output",
            p / "audio/alignment",
            "--model",
            a.model,
            "--device",
            a.device,
        ],
        p,
        a.workspace,
    )
    return {
        "status": "proposed",
        "cues": str(p / "audio/alignment/cues.proposed.json"),
        "note": "核对识别差异并拆句；用 captions 采用校准稿，不将 ASR 改写为正文",
    }


def library(a):
    config = yaml.safe_load((a.workspace / "workbench.yaml").read_text())
    entries = []
    for sid, series in config.get("series", {}).items():
        for eid, row in series.get("episodes", {}).items():
            p = a.workspace / row["project"]
            manifest = p / "asset_manifest.json"
            if not manifest.exists():
                continue
            for item in read(manifest).get("assets", []):
                if (
                    a.query
                    and a.query.lower()
                    not in json.dumps(item, ensure_ascii=False).lower()
                ):
                    continue
                entries.append(
                    {
                        "series": sid,
                        "episode": eid,
                        "project": str(p),
                        **item,
                        "resolved_path": str((p / item["path"]).resolve()),
                    }
                )
    target = a.workspace / "assets/paper-theatre/index.json"
    save(
        target,
        {
            "assets": entries,
            "note": "检索投影不授予素材或动态批准；来源是各集 manifest",
        },
    )
    return {"count": len(entries), "index": str(target), "assets": entries}


def captions(a):
    p, c = get_project(a)
    score = read(p / c["score"])
    cues = read(a.cues)
    if isinstance(cues, dict):
        if cues.get("voice_sha256") and cues["voice_sha256"] != sha(p / c["voice"]):
            raise ValueError("字幕提案来自旧声音")
        cues = cues["cues"]
    previous = 0
    for row in cues:
        if not (previous <= row["start"] < row["end"] <= score["duration"] + 0.01):
            raise ValueError("字幕区间无效或重叠")
        previous = row["end"]
    score["cues"] = cues
    save(p / c["score"], score)
    save(
        p / "audio/timing-receipt.json",
        {
            "voice_sha256": sha(p / c["voice"]),
            "caption_status": "editorial_timing",
            "source": str(a.cues),
            "score_sha256": sha(p / c["score"]),
        },
    )
    return {"cues": len(cues), "status": "timing_applied", "medical_review": "pending"}


def preview(a):
    p, c = get_project(a)
    assert_built(p)
    score = read(p / c["score"])
    start, end = 0, score["duration"]
    if a.shot:
        i = next(i for i, s in enumerate(score["shots"]) if s["id"] == a.shot)
        start = score["shots"][max(0, i - 1) if a.neighbors else i]["start"]
        end = score["shots"][min(len(score["shots"]) - 1, i + 1) if a.neighbors else i][
            "end"
        ]
    if a.start is not None:
        start = a.start
    if a.end is not None:
        end = a.end
    if not 0 <= start < end <= score["duration"]:
        raise ValueError("审片窗口超出单集")
    out = a.output.resolve() if a.output else p / "qa" / ("preview-" + stamp())
    config = {
        "project_root": str(p),
        "entry": c["entry"] + ("?clean=1" if a.clean else ""),
        "output": str(out),
        "width": a.width,
        "height": a.height,
        "start": start,
        "end": end,
    }
    with tempfile.TemporaryDirectory() as d:
        cfg = Path(d) / "preview.json"
        save(cfg, config)
        run(
            ["node", BUNDLE / "scripts/preview_local_animation.mjs", cfg],
            p,
            a.workspace,
        )
    return {
        "status": "previewed",
        "output": str(out),
        "range": [start, end],
        "full_listening": "pending",
    }


def mix(a):
    p, c = get_project(a)
    assert_narration(p, c)
    music = a.music
    if music is None:
        _, profile = load_author_profile(root=a.workspace, series_id=c["series_id"])
        value = profile.get("audio_mix", {}).get("background_music")
        if value:
            music = a.workspace / value
    cmd = [
        sys.executable,
        BUNDLE / "templates/animation/paper_theatre/scripts/mix_audio.py",
        "--project",
        p,
        "--voice",
        p / c["voice"],
        "--output",
        p / c["audio"],
    ]
    timing = read(p / "audio/timing-receipt.json")
    if timing.get("voice_sha256") != sha(p / c["voice"]):
        raise ValueError("旁白已变化，请先 retime 并校准字幕")
    if music:
        cmd += ["--music", music]
    run(cmd, p, a.workspace)
    r = read(p / "audio/mix-receipt.json")
    r.update(
        voice_sha256=sha(p / c["voice"]),
        score_sha256=sha(p / c["score"]),
        audio_sha256=sha(p / c["audio"]),
    )
    save(p / "audio/mix-receipt.json", r)
    entry = p / c["entry"]
    markup = entry.read_text()
    if 'id="voice"' not in markup:
        entry.write_text(
            markup.replace(
                "<script ",
                '<audio id="voice" src="'
                + c["audio"]
                + '" preload="metadata"></audio><script ',
                1,
            )
        )
    (p / "audio/needs-remix.json").unlink(missing_ok=True)
    return {"status": "mixed", "audio": str(p / c["audio"])}


def render(a):
    p, c = get_project(a)
    assert_narration(p, c)
    assert_built(p)
    r = read(p / "audio/mix-receipt.json")
    if any(
        r.get(k) != sha(p / f)
        for k, f in [
            ("voice_sha256", c["voice"]),
            ("score_sha256", c["score"]),
            ("audio_sha256", c["audio"]),
        ]
    ):
        raise ValueError("声音或时间轴已变，请先 mix")
    out = a.output.resolve() if a.output else p / "out" / ("review-" + stamp() + ".mp4")
    run(
        [
            sys.executable,
            BUNDLE / "scripts/render_javascript_animation.py",
            "--project-root",
            p,
            "--html-entry",
            c["entry"],
            "--audio",
            p / c["audio"],
            "--output",
            out,
            "--fps",
            str(read(p / c["score"])["fps"]),
            "--review-candidate",
        ],
        p,
        a.workspace,
    )
    result = {
        "path": str(out),
        "sha256": sha(out),
        "score_sha256": sha(p / c["score"]),
        "bundle_sha256": sha(p / "dist/film.js"),
        "audio_sha256": sha(p / c["audio"]),
        "release_eligible": False,
    }
    save(p / "out/current.json", result)
    return result


def assets(a):
    p, c = get_project(a)
    data = read(p / c["assets"])
    if a.asset:
        safe_id(a.asset_id)
        if not a.source or not a.usage or not a.kind or not a.limits:
            raise ValueError("素材导入需要 --source 和 --usage 记录出处与使用边界")
        if any(r["asset_id"] == a.asset_id for r in data["assets"]):
            raise ValueError("素材 ID 已存在；新版本使用独立 ID，保留旧图")
        dest = p / "assets/imported" / (a.asset_id + a.asset.suffix.lower())
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(a.asset, dest)
        entry = {
            "asset_id": a.asset_id,
            "path": str(dest.relative_to(p)),
            "source_type": a.kind,
            "source": a.source,
            "visual_meaning": a.usage,
            "must_not_imply": a.limits,
            "status": "pending_review",
            "medical": False,
            "registration": {"pivot": {"x": 0.5, "y": 0.5}, "anchors": {}},
        }
        if a.metadata:
            meta = read(a.metadata)
            for k in [
                "source_url",
                "license",
                "prompt_ref",
                "generation_receipt",
                "license_evidence",
                "medical",
                "medical_reference",
            ]:
                if k in meta:
                    entry[k] = meta[k]
            for k in [
                "prompt_ref",
                "generation_receipt",
                "license_evidence",
                "medical_reference",
            ]:
                if entry.get(k):
                    evidence = (a.metadata.parent / entry[k]).resolve()
                    dst = (
                        p / "assets/evidence" / (a.asset_id + "-" + k + evidence.suffix)
                    )
                    dst.parent.mkdir(exist_ok=True)
                    shutil.copy2(evidence, dst)
                    entry[k] = str(dst.relative_to(p))
        data["assets"].append(entry)
        save(p / c["assets"], data)
    if a.registration:
        patch = read(a.registration)
        row = next(x for x in data["assets"] if x["asset_id"] == a.asset_id)
        for q in [
            patch.get("pivot", {"x": 0.5, "y": 0.5}),
            *patch.get("anchors", {}).values(),
        ]:
            if not all(
                isinstance(q.get(k), (int, float)) and 0 <= q[k] <= 1
                for k in ["x", "y"]
            ):
                raise ValueError("连接点须为图片内的归一化坐标")
        row["registration"] = patch
        save(p / c["assets"], data)
    from PIL import Image, ImageDraw

    dest = p / "qa/assets"
    dest.mkdir(parents=True, exist_ok=True)
    cards = []
    rows = []
    for item in data["assets"]:
        src = p / item["path"]
        if src.suffix.lower() not in [
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".tif",
            ".tiff",
        ]:
            rows.append(
                {
                    "id": item["asset_id"],
                    "kind": "procedural_or_vector",
                    "path": item["path"],
                }
            )
            cards.append(
                f"<p>{html.escape(item['asset_id'])}：程序或矢量素材，使用镜头预览查看。</p>"
            )
            continue
        im = Image.open(src).convert("RGBA")
        thumb = im.copy()
        thumb.thumbnail((280, 210))
        sheet = Image.new("RGB", (900, 260), "white")
        draw = ImageDraw.Draw(sheet)
        for i, color in enumerate(["#f5eddd", "#263b36", "#bd8cac"]):
            sheet.paste(color, (i * 300, 0, (i + 1) * 300, 225))
            sheet.paste(
                thumb,
                (i * 300 + (300 - thumb.width) // 2, (225 - thumb.height) // 2),
                thumb,
            )
        draw.text((10, 232), item["asset_id"], fill="black")
        file = dest / (safe_id(item["asset_id"]) + ".jpg")
        sheet.save(file)
        bbox = im.getchannel("A").getbbox()
        rows.append(
            {
                "id": item["asset_id"],
                "width": im.width,
                "height": im.height,
                "alpha_bounds": bbox,
                "registration": item.get("registration", {}),
            }
        )
        cards.append(
            f'<section><h2>{html.escape(item["asset_id"])}</h2><img src="{file.name}" width="900"><p>{html.escape(item.get("visual_meaning", item.get("usage", "")))}</p><pre>{html.escape(json.dumps(item.get("registration", {}), ensure_ascii=False, indent=2))}</pre></section>'
        )
    (dest / "index.html").write_text(
        '<!doctype html><meta charset="utf-8"><title>纸件素材台</title><style>body{font:16px system-ui;background:#eee;padding:24px}section{background:white;margin:20px;padding:20px}img{max-width:100%}</style><h1>纸件素材台</h1><p>浅、深、彩底与连接点记录；不自动批准视觉或医学质量。</p>'
        + "".join(cards)
    )
    save(dest / "inspection.json", rows)
    return {"count": len(rows), "board": str(dest / "index.html")}


def package(a):
    p, c = get_project(a)
    assert_narration(p, c)
    r = read(p / "out/current.json")
    source = Path(r["path"])
    assert_built(p)
    mix_record = read(p / "audio/mix-receipt.json")
    if mix_record.get("voice_sha256") != sha(p / c["voice"]):
        raise ValueError("旁白已变化，请重新对齐、混音并导出")
    if (
        sha(source) != r["sha256"]
        or sha(p / "dist/film.js") != r["bundle_sha256"]
        or sha(p / c["score"]) != r["score_sha256"]
        or sha(p / c["audio"]) != r["audio_sha256"]
    ):
        raise ValueError("成片与当前源码/声音不一致，不能交付旧版")
    review = {
        "technical": "decoded_by_renderer",
        "visual": "pending",
        "full_motion": "pending",
        "full_listening": "pending",
        "medical": "pending",
    }
    if a.review:
        evidence = read(a.review)
        if evidence.get("video_sha256") != r["sha256"]:
            raise ValueError("审看记录必须对应当前视频字节")
        review.update(evidence.get("reviews", {}))
    target = (
        a.output.resolve()
        if a.output
        else a.workspace / "publish" / c["series_id"] / c["episode_id"] / stamp()
    )
    if target.exists():
        raise ValueError("交付目录已存在，请使用新修订")
    target.mkdir(parents=True)
    shutil.copy2(source, target / "video.mp4")
    shutil.copy2(p / c["score"], target / "score.json")
    shutil.copy2(p / c["narration"], target / "narration.json")
    score = read(p / c["score"])

    def tc(t):
        ms = round(t * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    (target / "subtitles.srt").write_text(
        "\n\n".join(
            f"{i + 1}\n{tc(q['start'])} --> {tc(q['end'])}\n{q['text']}"
            for i, q in enumerate(score["cues"])
        )
        + "\n"
    )
    if sha(target / "video.mp4") != r["sha256"]:
        raise ValueError("交付复制不一致")
    result = {
        **r,
        "schema": "paper_review_delivery/v1",
        "series_id": c["series_id"],
        "episode_id": c["episode_id"],
        "project": str(p),
        "video": "video.mp4",
        "reviews": review,
        "release_eligible": False,
        "uploaded": False,
    }
    save(target / "manifest.json", result)
    (target / "README.md").write_text(
        f"# {c['title']}\n\n[观看审看片](video.mp4)。本目录为本地审看交付，不等于医学终审或公开发布。\n"
    )
    save(
        a.workspace / "deliveries" / c["series_id"] / (c["episode_id"] + ".json"),
        {"current": str(target), "manifest": str(target / "manifest.json")},
    )
    return {
        "status": "packaged_and_read_back",
        "directory": str(target),
        "release_eligible": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--workspace",
        type=Path,
        default=Path(os.environ.get("MED_AUTOCAST_WORKSPACE_ROOT", ".")),
    )
    p.add_argument("--project", type=Path)
    sub = p.add_subparsers(dest="command", required=True)
    for cmd in ["init", "adopt"]:
        s = sub.add_parser(cmd)
        s.add_argument("--series", required=True)
        s.add_argument("--episode", required=True)
        s.add_argument("--title")
        s.add_argument("--from-project", type=Path)
        s.add_argument("--narration", type=Path)
    sub.add_parser("inspect")
    sub.add_parser("build")
    sub.add_parser("retime")
    s = sub.add_parser("library")
    s.add_argument("--query")
    s = sub.add_parser("align")
    s.add_argument("--python", required=True)
    s.add_argument("--model", required=True)
    s.add_argument("--device", default="cpu")
    s = sub.add_parser("narrate")
    s.add_argument("--beat", action="append")
    s.add_argument("--force", action="store_true")
    s = sub.add_parser("captions")
    s.add_argument("--cues", type=Path, required=True)
    s = sub.add_parser("assets")
    s.add_argument("--asset", type=Path)
    s.add_argument("--asset-id")
    s.add_argument("--source")
    s.add_argument("--usage")
    s.add_argument("--limits")
    s.add_argument(
        "--kind",
        choices=["authored_graphic", "reviewed_library", "imagegen", "licensed_web"],
    )
    s.add_argument("--registration", type=Path)
    s.add_argument("--metadata", type=Path)
    s = sub.add_parser("preview")
    s.add_argument("--shot")
    s.add_argument("--neighbors", action="store_true")
    s.add_argument("--start", type=float)
    s.add_argument("--end", type=float)
    s.add_argument("--clean", action="store_true")
    s.add_argument("--output", type=Path)
    s.add_argument("--width", type=int, default=1280)
    s.add_argument("--height", type=int, default=720)
    s = sub.add_parser("mix")
    s.add_argument("--music", type=Path)
    s = sub.add_parser("render")
    s.add_argument("--output", type=Path)
    s = sub.add_parser("package")
    s.add_argument("--output", type=Path)
    s.add_argument("--review", type=Path)
    a = p.parse_args()
    a.workspace = a.workspace.resolve()
    if not a.project and a.command != "library":
        p.error("需要 --project")
    try:
        result = globals()[{"init": "initialize"}.get(a.command, a.command)](a)
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, KeyError, StopIteration) as e:
        p.exit(1, f"{e}\n")


if __name__ == "__main__":
    main()
