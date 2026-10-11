#!/usr/bin/env python3
"""One local project entry: existing creative code remains the director's source."""

from __future__ import annotations
import argparse, hashlib, html, json, os, re, shutil, subprocess, sys, tempfile, time
from pathlib import Path
import yaml
from workbench_config import load_author_profile
from delivery_layout import locations, install
from build_release_packages import platform_text
from render_javascript_animation import renderer_selection_report

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


def selected_visual_format(workspace, series_id):
    data = yaml.safe_load((workspace / "workbench.yaml").read_text()) or {}
    _, author = load_author_profile(
        root=workspace,
        series_id=series_id if series_id in data.get("series", {}) else None,
    )
    visual = author.get("visual_format", {})
    return visual if isinstance(visual, dict) else {}


def project_style_selection(project, config):
    score = read(project / config.get("score", "score.json"))
    style = score.get("style", {})
    style = style if isinstance(style, dict) else {}
    return {
        "style_id": style.get("styleId") or style.get("style_id") or config.get("style_id") or "paper_collage",
        "renderer_id": style.get("renderer") or config.get("renderer_id") or "canvas2d",
        "style_profile_ref": (
            style.get("styleProfileRef")
            or style.get("style_profile_ref")
            or config.get("style_profile_ref")
            or "templates/animation/animation_style_registry.json"
        ),
    }


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
    score_style = score.get("style", {})
    score_style = score_style if isinstance(score_style, dict) else {}
    visual = selected_visual_format(a.workspace, a.series)
    style_id = (
        getattr(a, "style_id", None)
        or score_style.get("styleId")
        or score_style.get("style_id")
        or visual.get("style_id")
        or "paper_collage"
    )
    renderer_id = getattr(a, "renderer", None) or score_style.get("renderer") or visual.get("renderer") or "canvas2d"
    style_profile_ref = (
        getattr(a, "style_profile_ref", None)
        or score_style.get("styleProfileRef")
        or score_style.get("style_profile_ref")
        or visual.get("style_profile_ref")
        or "templates/animation/animation_style_registry.json"
    )
    score["style"] = {
        **score_style,
        "styleId": style_id,
        "renderer": renderer_id,
        "styleProfileRef": style_profile_ref,
    }
    save(p / "score.json", score)
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
        "style_id": style_id,
        "renderer_id": renderer_id,
        "style_profile_ref": style_profile_ref,
        "beat_shots": {b["id"]: s["id"] for b, s in zip(beats, score["shots"])},
        "kit_version": read(p / "package.json").get("version", "1.0.0"),
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
    visual = author.get("visual_format", {})
    visual = visual if isinstance(visual, dict) else {}
    score = read(p / "score.json")
    score_style = score.get("style", {})
    score_style = score_style if isinstance(score_style, dict) else {}
    selected_style_id = (
        getattr(a, "style_id", None)
        or score_style.get("styleId")
        or visual.get("style_id")
        or "paper_collage"
    )
    applied_style_id = score_style.get("appliedStyleId") or score_style.get("applied_style_id")
    if not applied_style_id and selected_style_id == "paper_collage":
        applied_style_id = "paper_collage"
    score["style"] = {
        **score_style,
        "styleId": selected_style_id,
        "renderer": getattr(a, "renderer", None) or score_style.get("renderer") or visual.get("renderer") or "canvas2d",
        "styleProfileRef": (
            getattr(a, "style_profile_ref", None)
            or score_style.get("styleProfileRef")
            or visual.get("style_profile_ref")
            or "templates/animation/animation_style_registry.json"
        ),
    }
    if applied_style_id:
        score["style"]["appliedStyleId"] = applied_style_id
    else:
        score["style"].pop("appliedStyleId", None)
        score["style"].pop("applied_style_id", None)
    save(p / "score.json", score)
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
    style_selection = project_style_selection(p, c)
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
        **style_selection,
        "voice_exists": (p / c["voice"]).exists(),
        "mix_exists": (p / c["audio"]).exists(),
        "latest_render": read(p / "out/current.json")
        if (p / "out/current.json").exists()
        else None,
        "commands": [
            "revise",
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


def revise(a):
    """Create independent editable bytes; register a successor after it is rendered."""
    source = a.from_project.resolve()
    target = a.project.resolve()
    if not source.is_relative_to(a.workspace) or not target.is_relative_to(a.workspace):
        raise ValueError("修订源与目标须位于当前工作区")
    if target.exists():
        raise ValueError("修订目标已存在；请恢复现有修订或选择新的明确路径")
    config = read(source / "project.json")
    shutil.copytree(source, target, ignore=shutil.ignore_patterns(
        "out", "qa", "dist", "history", "node_modules", "__pycache__"))
    evidence = source / "qa/asset-reviews"
    if evidence.is_dir():
        shutil.copytree(evidence, target / "qa/asset-reviews")
    for name in ("project.json", config["narration"], config["score"]):
        if (target / name).is_file() and os.path.samefile(source / name, target / name):
            raise ValueError("修订文件没有隔离；未注册为当前版本")
    save(target / "revision.json", {
        "source_project": str(source), "source_score_sha256": sha(source / config["score"]),
        "source_narration_sha256": sha(source / config["narration"]),
        "copy_method": "independent_files", "registered_as_current": False,
        "review_inheritance": "unchanged_asset_evidence_only",
    })
    return {"status": "revision_created", "project": str(target), "source": str(source)}


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
    from render_narration import narration_signature, audio_rejected, indextts_text, tts_text, ANNOTATION
    receipt = p / "audio/narration_beats.json"
    if receipt.exists():
        beats = read(receipt)["beats"]
        if narration_signature(beats) != narration_signature(
            read(p / c["narration"])["beats"]
        ):
            raise ValueError("旁白正文或发音控制已变化，请重新配音改动声段")
        for beat in beats:
            baseline = read(receipt).get("baseline", {})
            vocab = Path(baseline.get("model_root", ".")) / "pinyin.vocab"
            spoken = tts_text(beat)
            if baseline.get("definition") == "indextts_2_5" and ANNOTATION.search(spoken):
                if not vocab.is_file():
                    raise ValueError("无法核对当前 IndexTTS 注音词表")
                if beat.get("model_text", spoken) != indextts_text(spoken, set(vocab.read_text().splitlines())):
                    raise ValueError(f"声段 {beat['id']} 原生注音未按当前词表转换，请重配该声段")
            take = Path(beat["audio"]).with_suffix(".json")
            if take.is_file() and audio_rejected(read(take)):
                raise ValueError(f"声段 {beat['id']} 已被明确拒用，请重新配音该声段")


def narrate(a):
    p, c = get_project(a)
    from render_narration import synthesize

    prior = p / "audio/narration_beats.json"
    if prior.is_file():
        save(p / "audio/previous-narration_beats.json", read(prior))
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
    reference = getattr(a, "reference_score", None)
    old_score = read(reference) if reference else read(p / c["score"])
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
    # Editorial line breaks survive voice edits. Retiming is only a time proposal.
    prior = p / "audio/previous-narration_beats.json"
    reference_narration = getattr(a, "reference_narration", None)
    if not reference_narration and reference and (reference.parent / "narration_beats.json").is_file():
        reference_narration = reference.parent / "narration_beats.json"
    source_receipt = reference_narration or (prior if prior.is_file() and not reference else None)
    prior_beats = {b["id"]: b for b in read(source_receipt).get("beats", [])} if source_receipt else {}
    old_shots = {s["id"]: s for s in old_score.get("shots", [])}
    # Repeating retime for an unchanged voice must not repeatedly remap beat
    # padding onto itself. Keep already adopted editorial cues when the exact
    # voice and actual shot cuts are unchanged; an explicit reference still wins.
    timing_path = p / "audio/timing-receipt.json"
    timing = read(timing_path) if timing_path.is_file() else {}
    same_voice = timing.get("voice_sha256") == sha(p / c["voice"])
    same_cuts = len(old_score.get("shots", [])) == len(score["shots"]) and all(
        abs(old["start"] - shot["start"]) < 1e-6 and abs(old["end"] - shot["end"]) < 1e-6
        for old, shot in zip(old_score.get("shots", []), score["shots"])
    )
    preserve_adopted_cues = not reference and same_voice and same_cuts
    cues = list(old_score.get("cues", [])) if preserve_adopted_cues else []
    for shot, beat in ([] if preserve_adopted_cues else zip(score["shots"], ordered)):
        old = old_shots.get(shot["id"])
        pieces = [q for q in old_score.get("cues", [])
                  if old and old["start"] <= (q["start"] + q["end"]) / 2 < old["end"]]
        previous = prior_beats.get(beat["id"])
        source_start, source_end = ((previous["start"], previous["end"])
                                    if previous and previous.get("text") == beat["text"]
                                    else (old["start"], old["end"]) if old else (0, 1))
        if pieces and source_end > source_start:
            scale = (beat["end"] - beat["start"]) / (source_end - source_start)
            for q in pieces:
                start = max(shot["start"], beat["start"] + (q["start"] - source_start) * scale)
                end = min(shot["end"], beat["start"] + (q["end"] - source_start) * scale)
                if end > start:
                    cues.append({**q, "start": start, "end": end})
        else:
            cues.append({"start": beat["start"], "end": beat["end"], "text": beat["text"]})
    score["cues"] = cues
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
            "caption_breaks": "preserved_when_available",
            "reference_score": str(reference) if reference else None,
            "reference_narration": str(source_receipt) if source_receipt else None,
            "score_sha256": sha(p / c["score"]),
        },
    )
    return {
        "status": "retimed",
        "duration": score["duration"],
        "caption_status": "draft",
        "caption_breaks": "preserved_when_available",
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
    from animation_library import run as library_run
    return library_run(a)


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
    style_selection = project_style_selection(p, c)
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
    entry = c["entry"] + ("?clean=1" if a.clean else "")
    command = [
        sys.executable,
        BUNDLE / "scripts/render_javascript_animation.py",
        "--project-root",
        p,
        "--html-entry",
        entry,
        "--preview",
        "--preview-output",
        out,
        "--width",
        str(a.width),
        "--height",
        str(a.height),
        "--start",
        str(start),
        "--end",
        str(end),
        "--asset-manifest",
        c["assets"],
        "--requested-style-id",
        style_selection["style_id"],
        "--requested-renderer-id",
        style_selection["renderer_id"],
        "--review-candidate",
    ]
    run(command, p, a.workspace)
    preview_report_path = out / "preview.json"
    renderer_selection = None
    quality_debt = []
    if preview_report_path.is_file():
        preview_report = read(preview_report_path)
        renderer_selection = renderer_selection_report(
            style_selection["style_id"],
            style_selection["renderer_id"],
            preview_report.get("renderer_runtime", {}),
        )
        quality_debt = list(preview_report.get("quality_debt", []))
        known_debt = {item.get("code") for item in quality_debt if isinstance(item, dict)}
        quality_debt.extend(
            item for item in renderer_selection["quality_debt"]
            if item.get("code") not in known_debt
        )
        preview_report["renderer_selection"] = renderer_selection
        preview_report["quality_debt"] = quality_debt
        save(preview_report_path, preview_report)
        preview_status = (
            preview_report.get("status")
            if preview_report.get("status") in {
                "not_rendered_with_quality_debt",
                "preview_attempted_with_quality_debt",
            }
            else "previewed"
        )
    else:
        renderer_selection = renderer_selection_report(
            style_selection["style_id"],
            style_selection["renderer_id"],
            {},
        )
        quality_debt = [
            *renderer_selection["quality_debt"],
            {
                "code": "preview_receipt_missing",
                "owner_stage": "visual-review",
                "blocks_stage_progress": False,
            },
        ]
        preview_status = "preview_attempted_with_quality_debt"
    return {
        "status": preview_status,
        "output": str(out),
        "range": [start, end],
        **style_selection,
        "renderer_selection": renderer_selection,
        "quality_debt": quality_debt,
        "preview_receipt": str(preview_report_path) if preview_report_path.is_file() else None,
        "full_listening": "pending",
    }


def mix(a):
    p, c = get_project(a)
    assert_narration(p, c)
    music = a.music
    music_plan = getattr(a, "music_plan", None)
    if music is None and music_plan is None:
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
        cmd += ["--music", Path(music).resolve()]
    if music_plan:
        cmd += ["--music-plan", music_plan.resolve()]
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
    style_selection = project_style_selection(p, c)
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
            "--requested-style-id",
            style_selection["style_id"],
            "--requested-renderer-id",
            style_selection["renderer_id"],
            "--review-candidate",
        ],
        p,
        a.workspace,
    )
    render_receipt_path = out.with_suffix(".receipt.json")
    render_receipt = read(render_receipt_path) if render_receipt_path.is_file() else {}
    if not out.is_file():
        return {
            "status": render_receipt.get("status", "render_not_completed_with_quality_debt"),
            "path": None,
            "output_target": str(out),
            "render_receipt": str(render_receipt_path) if render_receipt_path.is_file() else None,
            **style_selection,
            "renderer_selection": render_receipt.get("renderer_selection") or renderer_selection_report(
                style_selection["style_id"], style_selection["renderer_id"], {}
            ),
            "quality_debt": render_receipt.get("quality_debt", [{
                "code": "render_output_missing",
                "owner_stage": "media-production",
                "blocks_stage_progress": False,
                "blocks_quality_export": True,
            }]),
            "release_eligible": False,
        }
    renderer_selection = render_receipt.get("renderer_selection") or renderer_selection_report(
        style_selection["style_id"],
        style_selection["renderer_id"],
        {},
    )
    quality_debt = list(render_receipt.get("quality_debt", renderer_selection["quality_debt"]))
    if not render_receipt_path.is_file():
        quality_debt.append({
            "code": "render_receipt_missing",
            "owner_stage": "visual-review",
            "blocks_stage_progress": False,
        })
    result = {
        "status": render_receipt.get("status", "rendered"),
        "path": str(out),
        "sha256": sha(out),
        "score_sha256": sha(p / c["score"]),
        "bundle_sha256": sha(p / "dist/film.js"),
        "audio_sha256": sha(p / c["audio"]),
        **style_selection,
        "renderer_selection": renderer_selection,
        "quality_debt": quality_debt,
        "render_receipt": str(render_receipt_path) if render_receipt_path.is_file() else None,
        "release_eligible": False,
    }
    if result["status"] == "rendered":
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
    evidence = {}
    if a.review:
        evidence = read(a.review)
        if evidence.get("video_sha256") != r["sha256"]:
            raise ValueError("审看记录必须对应当前视频字节")
        review.update(evidence.get("reviews", {}))
    loc = locations(a.workspace, c['series_id'], c['episode_id'])
    target = a.output.resolve() if a.output else loc['user']
    # Explicit technical exports remain available outside the user delivery tree.
    internal_export = target != loc['user']
    if internal_export and target.is_relative_to(loc['user'].parent):
        raise ValueError("publish 只保留每集最新版；过程导出请放 work/ 或 productions/，不要建立版本子目录")
    if internal_export and target.exists():
        raise ValueError("过程导出已存在，请选择独立路径")
    score = read(p / c['score'])

    def tc(t):
        ms = round(t * 1000)
        return f"{ms // 3600000:02}:{ms // 60000 % 60:02}:{ms // 1000 % 60:02},{ms % 1000:03}"

    scratch = a.workspace / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='delivery-', dir=scratch) as folder:
        user = Path(folder) / 'publish'
        record = Path(folder) / 'record'
        user.mkdir(); record.mkdir()
        shutil.copy2(source, user / 'video.mp4')
        shutil.copy2(p / c['score'], record / 'score.json')
        shutil.copy2(p / c['narration'], record / 'narration.json')
        (user / 'subtitles.srt').write_text(
            "\n\n".join(f"{i + 1}\n{tc(q['start'])} --> {tc(q['end'])}\n{q['text']}"
                         for i, q in enumerate(score['cues'])) + "\n", encoding='utf-8')
        if sha(user / 'video.mp4') != r['sha256']:
            raise ValueError("交付复制不一致")
        config = yaml.safe_load((a.workspace / 'workbench.yaml').read_text()) or {}
        catalog_ref = config.get('series', {}).get(c['series_id'], {}).get('release_catalog')
        entry = None
        catalog = {}
        if catalog_ref and (a.workspace / catalog_ref).is_file():
            catalog = yaml.safe_load((a.workspace / catalog_ref).read_text()) or {}
            entries = [e for e in catalog.get('episodes', []) if e.get('id') == c['episode_id']]
            if len(entries) == 1:
                entry = entries[0]
        debt = list(r.get('quality_debt', []))
        if entry:
            for platform, name in [('xiaohongshu', '小红书文案.txt'), ('channels', '微信视频号文案.txt')]:
                (user / name).write_text(platform_text(entry, platform), encoding='utf-8')
        else:
            debt.append({'code': 'release_copy_pending', 'owner_stage': 'evidence-plan',
                         'blocks_stage_progress': False})
        try:
            subprocess.run(['ffmpeg', '-y', '-v', 'error', '-ss', str(min(3.5, float(score['duration']) / 2)),
                            '-i', str(source), '-frames:v', '1', str(user / '封面.jpg')], check=True,
                           stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        except (OSError, subprocess.CalledProcessError):
            debt.append({'code': 'cover_pending', 'owner_stage': 'review-handoff',
                         'blocks_stage_progress': False})
        attachments = {}
        for src, name, key in [
            ('audio/narration-normalized.wav', 'narration.wav', 'voice'),
            ('audio/narration_beats.json', 'narration_beats.json', 'narration_receipt'),
            ('audio/pronunciation-review.json', 'pronunciation-review.json', 'pronunciation_review'),
            ('audio/narration-foley-only.wav', 'narration-foley-only.wav', 'no_music'),
            ('audio/mix-receipt.json', 'mix-receipt.json', 'mix_receipt'),
            ('audio/narration-foley-only.receipt.json', 'no-music-receipt.json', 'no_music_receipt'),
            ('preproduction/music-plan.json', 'music-plan.json', 'music_plan'),
        ]:
            if (p / src).is_file():
                shutil.copy2(p / src, record / name)
                attachments[key] = name
        preview_ref = evidence.get('review_scope', {}).get('preview')
        if preview_ref and Path(preview_ref).is_file():
            preview = Path(preview_ref)
            shutil.copy2(preview, record / 'preview.json')
            attachments['preview'] = 'preview.json'
            if (preview.parent / 'contact.jpg').is_file():
                shutil.copy2(preview.parent / 'contact.jpg', record / 'contact.jpg')
                attachments['contact_sheet'] = 'contact.jpg'
        final_record = target if internal_export else loc['record']
        relative = lambda file: os.path.relpath(file, final_record)
        result = {**r, 'schema': 'paper_review_delivery/v1', 'series_id': c['series_id'],
                  'episode_id': c['episode_id'], 'project': str(p),
                  'production_version': p.name, 'video': relative(target / 'video.mp4'),
                  'delivery_layout': 'internal_export' if internal_export else 'latest_only',
                  'reviews': review, 'quality_debt': debt, 'release_eligible': False, 'uploaded': False,
                  'artifacts': {'video': relative(target / 'video.mp4'),
                                'subtitles': relative(target / 'subtitles.srt'),
                                'score': 'score.json', 'narration_script': 'narration.json',
                                'source_project': str(p), **attachments},
                  'review_scope': evidence.get('review_scope', {}),
                  'review_evidence': str(a.review.resolve()) if a.review else None}
        if entry:
            result['copy_revision'] = catalog.get('copy_revision')
            result['publication_copy'] = {
                'catalog': str(a.workspace / catalog_ref),
                'catalog_sha256': sha(a.workspace / catalog_ref),
                'artifacts': {platform: {'path': str(target / name), 'sha256': sha(user / name)}
                    for platform, name in [('xiaohongshu', '小红书文案.txt'), ('channels', '微信视频号文案.txt')]},
                'editorial_review': entry.get('copy_review', 'pending'),
            }
        save(record / 'manifest.json', result)
        (user / '发布交付包.md').write_text(
            f"# {c['title']}\n\n[观看视频](video.mp4) · [小红书文案](小红书文案.txt) · [视频号文案](微信视频号文案.txt)\n\n"
            "本目录只保留最新版。视频用于审看，完整动态、听感和医学审核按当前记录分别确认；尚未上传平台。\n",
            encoding='utf-8')
        if internal_export:
            target.mkdir(parents=True)
            for directory in (user, record):
                for file in directory.iterdir():
                    shutil.copy2(file, target / file.name)
            return {'status': 'packaged_internal_candidate', 'directory': str(target), 'release_eligible': False}
        pointer = install(a.workspace, c['series_id'], c['episode_id'], user, record)
    return {'status': 'packaged_and_read_back', 'directory': str(target),
            'manifest': pointer['manifest'], 'previous_delivery': pointer['previous_delivery'],
            'quality_debt': debt, 'release_eligible': False}


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
        s.add_argument("--style-id", help="单集风格选择；未知风格保留并交给导演/Review 判断")
        s.add_argument("--renderer", help="单集 renderer 选择；未激活后端不阻断前置工作")
        s.add_argument("--style-profile-ref")
    sub.add_parser("inspect")
    s = sub.add_parser("revise")
    s.add_argument("--from-project", type=Path, required=True, help="明确源工程；独立复制可编辑文件，不使用硬链接")
    sub.add_parser("build")
    s = sub.add_parser("retime")
    s.add_argument("--reference-score", type=Path, help="可选：用精确旧版Score恢复原字幕断句，不改变当前镜头动作")
    s.add_argument("--reference-narration", type=Path, help="可选：原声段回执，用真实声音区间映射字幕；优先读取参考Score同目录回执")
    s = sub.add_parser("library")
    s.add_argument("--query")
    s.add_argument("--kind", help="按已登记类型检索，不强制类型枚举")
    s.add_argument("--scope", help="按复用范围检索")
    s.add_argument("--refresh", action="store_true", help="重建完整看图库，不受查询过滤影响")
    library_action = s.add_mutually_exclusive_group()
    library_action.add_argument("--ingest-project", action="store_true", help="独立保存所选单集素材与现有来源证据")
    library_action.add_argument("--register", type=Path, help="登记代码、动作、声音或其他素材包")
    library_action.add_argument("--use", help="将素材库精确版本复制到当前项目")
    s.add_argument("--asset-id", action="append", help="归档时选择素材；复用图像时指定新 ID")
    s.add_argument("--revision", help="复用的精确版本；缺省取最新登记版本")
    s.add_argument("--notes", type=Path, help="可选策展说明：标题、用途、范围与标签")
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
    music_options = s.add_mutually_exclusive_group()
    music_options.add_argument("--music", type=Path)
    music_options.add_argument("--music-plan", type=Path)
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
