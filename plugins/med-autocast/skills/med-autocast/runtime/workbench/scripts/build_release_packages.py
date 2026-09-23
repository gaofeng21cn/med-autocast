#!/usr/bin/env python3
"""Build or verify standardized per-episode release packages."""

import argparse
import hashlib
import json
import os
import shutil
from pathlib import Path

import yaml

from delivery_contract import release_eligible
from workbench_config import ROOT, series_paths


def catalog_context(catalog: dict, catalog_path: Path, root: Path = ROOT) -> dict:
    paths = series_paths(catalog["series_id"], root)
    if catalog_path.resolve() != paths["release_catalog"].resolve():
        raise ValueError("Catalog path differs from the series registry")
    return {**catalog, "_paths": paths}


def source_links(catalog: dict, episode: dict) -> dict[str, str]:
    paths = catalog["_paths"]
    release = paths["publish_root"] / episode["id"]
    production = paths["production_root"] / episode["id"]
    content = paths["content_root"] / "episodes" / episode["id"]
    return {key: Path(os.path.relpath(value, release)).as_posix() for key, value in {
        "video": production / "final/video.mp4",
        "plan": production / "production_plan.yaml",
        "qa": production / "qa/final-review/technical-report.json",
        "series_qa": paths["technical_qa"],
        "narration": content / "01_narration.md",
        "story": content / "03_story_package.yaml",
        "catalog": paths["release_catalog"],
    }.items()}


DISCLAIMER = "本内容仅作一般健康科普，不能替代个体化诊断和治疗建议。"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def format_duration(seconds: float) -> str:
    rounded = int(round(seconds))
    minutes, remainder = divmod(rounded, 60)
    return f"{minutes} 分 {remainder} 秒" if minutes else f"{remainder} 秒"


def tags(values: list[str]) -> str:
    return " ".join(f"#{value.lstrip('#')}" for value in values)


def platform_text(episode: dict, platform: str) -> str:
    if platform == "xiaohongshu":
        title = episode["xiaohongshu_title"]
        copy = episode["xiaohongshu_copy"].strip()
        topic_tags = tags(episode["xiaohongshu_tags"])
    else:
        title = episode["channels_title"]
        copy = episode["channels_copy"].strip()
        topic_tags = tags(episode["channels_tags"])
    return f"""【标题】
{title}

【正文】
{copy}

{DISCLAIMER}

【话题】
{topic_tags}

【置顶评论】
{episode['pinned_comment']}
"""


def package_markdown(catalog: dict, episode: dict, qa: dict) -> str:
    links = source_links(catalog, episode)
    number = int(episode["number"])
    duration = format_duration(float(qa["duration_seconds"]))
    video = qa["video_stream"]
    audio = qa["audio_stream"]
    return f"""# 第 {number:02d} 篇发布交付包

系列：{catalog['series_title']}  
篇目：{episode['title']}  
状态：视频交付与技术 QA 完成；完整听感与医学终审待确认  
更新时间：{catalog['updated_at']}  
适用平台：小红书、微信视频号

## 1. 成片

交付视频：`video.mp4`

该文件是从制作母版 `{links['video']}` 复制出的真实文件，可随本目录直接压缩、转存或交给发布人员。

- 时长：{duration}
- 画面：{video['width']}x{video['height']}，{video['frame_rate']} fps
- 编码：{video['codec'].upper()}/{audio['codec'].upper()}
- SHA-256：`{qa['sha256']}`
- 动画交付门：已通过制作单要求的视觉形式、生成动画来源、逐镜运动证据和静态占比检查
- 技术 QA：已通过完整解码、媒体规格、字幕一致性、字幕排版和抽样黑帧检查
- 逐秒画面、ASR 和技术 QA 不代表完整试听；发布前须回读该篇视觉 manifest 的 `final_listening_review` 与复核记录

不要从 `candidates/`、`final/archive/`、`archive/early-prototypes/` 或 `work/` 中选择发布版本。它们不是当前交付成片。

## 2. 推荐标题

### 小红书

{episode['xiaohongshu_title']}

### 微信视频号

{episode['channels_title']}

## 3. 小红书发布文案

可直接复制文件：`小红书文案.txt`

## 4. 微信视频号发布文案

可直接复制文件：`微信视频号文案.txt`

## 5. 置顶评论建议

{episode['pinned_comment']}

## 6. 发布前检查

- [ ] 使用本目录真实文件 `video.mp4`
- [ ] 成片 SHA-256 与本说明及系列 `manifest.json` 一致
- [ ] 已完整试听旁白、BGM 与切镜，单篇复核记录中的听感待办已处理
- [ ] 医学终审已完成，或明确标注为技术原型/科普试发
- [ ] 标题没有把症状、化验或影像线索写成确定诊断
- [ ] 文案没有新增审定旁白和故事包之外的医学结论
- [ ] 文案没有给出个人用药、手术或复查方案
- [ ] 医学不确定性、条件和急症行动边界没有被删掉
- [ ] 发布页面没有额外自动生成的错误字幕、贴纸或医疗承诺
- [ ] 平台压缩后抽查开头、核心判断、行动边界和片尾字幕

## 7. 来源与制作关联

- 审定旁白：`{links['narration']}`
- 故事包：`{links['story']}`
- 制作母版：`{links['video']}`
- 制作单：`{links['plan']}`
- 技术 QA：`{links['qa']}`
- 系列 QA：`{links['series_qa']}`
- 发布文案来源：`{links['catalog']}`

发布文案只压缩审定旁白和故事包，不在发布阶段补充医学结论。技术 QA 不能替代医学终审。
"""


def blocked_package_markdown(catalog: dict, episode: dict, qa: dict | None) -> str:
    status = qa.get("status") if qa else "missing_qa_report"
    violations = (qa or {}).get("animation_gate", {}).get("violations", [])
    violation_text = "\n".join(f"- `{item}`" for item in violations) or "- 视频交付证据尚未形成"
    return f"""# 第 {int(episode['number']):02d} 篇发布准备包

系列：{catalog['series_title']}  
篇目：{episode['title']}  
状态：视频制作或验收尚未完成，不可发布  
当前机器状态：`{status}`

本目录只保留已准备好的两份平台文案。正式 `video.mp4` 缺失是有意的发布门禁，不是打包遗漏；符合制作单要求的视频完成、人工视觉审核及动画/技术 QA 全部通过后，打包器才会复制真实成片。

当前阻塞：

{violation_text}

可直接复制的文案：

- `小红书文案.txt`
- `微信视频号文案.txt`

不得把 animatic、失败候选、归档或临时目录中的文件改名为 `video.mp4` 后发布。
"""


def publish_index(catalog: dict, episodes: list[dict], reports: dict[str, dict]) -> str:
    rows = []
    ready_count = 0
    for episode in episodes:
        qa = reports.get(episode["id"])
        if qa and release_eligible(qa):
            ready_count += 1
            duration = format_duration(float(qa["duration_seconds"]))
            status = "技术 QA 通过；完整听感与医学终审待确认"
        else:
            duration = "-"
            status = "视频制作或验收未完成，不可发布"
        rows.append(
            f"| {int(episode['number']):02d} | {episode['title']} | "
            f"[{episode['id']}]({episode['id']}/) | {duration} | {status} |"
        )
    return f"""# {catalog['series_title']}发布工作台

状态：{ready_count}/{len(episodes)} 篇具备技术 QA 通过的成片；完整听感与医学终审须另行确认  
更新时间：{catalog['updated_at']}

本目录是发布准备工作台。只有视频交付与技术 QA 通过的篇目才包含真实 `video.mp4`；其他篇目保留两份平台文案 TXT，但没有视频，不能压缩后冒充成片交付。

| 集数 | 篇目 | 交付包 | 时长 | 状态 |
|---:|---|---|---:|---|
{chr(10).join(rows)}

## 发布顺序

按本系列发布目录的篇目编号排序；实际发布安排由系列内容计划决定。

## 使用规则

1. 先确认该篇视频交付与技术 QA 通过，再使用其中的真实 `video.mp4`。
2. 没有 `video.mp4` 表示动画尚未完成，禁止从 animatic、失败候选或归档目录补文件。
3. 正式发布前回读并完成该篇完整听感和医学终审；技术通过不等于可公开发布。
4. 上传后检查平台自动字幕、封面裁切、清晰度和文案完整性。
5. 发布平台上的修改若涉及医学含义，必须先回写上游权威并重新生成交付包。
"""


def publish_manifest(catalog: dict, episodes: list[dict], reports: dict[str, dict]) -> str:
    def episode_record(episode: dict) -> dict:
        qa = reports.get(episode["id"], {})
        ready = release_eligible(qa)
        return {
            "number": int(episode["number"]),
            "episode_id": episode["id"],
            "title": episode["title"],
            "release_directory": episode['id'],
            "video": f"{episode['id']}/video.mp4" if ready else None,
            "duration_seconds": qa.get("duration_seconds") if ready else None,
            "sha256": qa.get("sha256") if ready else None,
            "delivery_status": (
                "video_ready_clinical_review_required"
                if ready
                else "video_generation_or_review_required"
            ),
            "technical_qa": "passed" if ready else "not_passed",
            "clinical_review": "required" if ready else "blocked_by_animation",
        }

    payload = {
        "schema": "medical_video_series_delivery/v2",
        "path_base": "manifest_directory",
        "series_id": catalog["series_id"],
        "series_title": catalog["series_title"],
        "updated_at": str(catalog["updated_at"]),
        "status": catalog["release_status"],
        "platforms": catalog["platforms"],
        "episodes": [episode_record(episode) for episode in episodes],
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def ensure_file(path: Path, expected: str, check: bool, errors: list[str]) -> None:
    if check:
        if not path.is_file():
            errors.append(f"missing file: {path}")
        elif path.read_text(encoding="utf-8") != expected:
            errors.append(f"stale file: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(expected, encoding="utf-8")


def ensure_directory(path: Path, check: bool, errors: list[str]) -> None:
    if check:
        if not path.is_dir() or path.is_symlink():
            errors.append(f"missing real directory: {path}")
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.is_symlink():
        path.unlink()
    elif path.exists() and not path.is_dir():
        raise RuntimeError(f"refusing to replace non-directory path: {path}")
    path.mkdir(parents=True, exist_ok=True)


def ensure_copy(source: Path, target: Path, expected_sha256: str, check: bool, errors: list[str]) -> None:
    if check:
        if not target.is_file() or target.is_symlink():
            errors.append(f"missing real file: {target}")
        elif sha256(target) != expected_sha256:
            errors.append(f"copied video hash mismatch: {target}")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.is_symlink():
        target.unlink()
    if target.is_file() and sha256(target) == expected_sha256:
        return
    shutil.copy2(source, target)


def ensure_absent(path: Path, errors: list[str]) -> None:
    if path.exists() or path.is_symlink():
        errors.append(f"blocked release must not contain video: {path}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path)
    parser.add_argument("--series")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    project_root = __import__("workbench_config").ROOT
    if args.series:
        catalog_path = series_paths(args.series)["release_catalog"]
        if args.catalog and args.catalog.resolve() != catalog_path.resolve():
            raise ValueError("--catalog conflicts with --series")
    elif args.catalog:
        catalog_path = args.catalog if args.catalog.is_absolute() else project_root / args.catalog
    else:
        parser.error("Pass --series or --catalog")
    catalog = catalog_context(yaml.safe_load(catalog_path.read_text(encoding="utf-8")), catalog_path)
    if args.series and catalog["series_id"] != args.series:
        raise ValueError("Catalog series_id differs from --series")
    paths = catalog["_paths"]
    qa_path = paths["technical_qa"]
    reports = {
        report["episode_id"]: report
        for report in json.loads(qa_path.read_text(encoding="utf-8"))
    }
    episodes = sorted(catalog["episodes"], key=lambda item: int(item["number"]))
    errors: list[str] = []

    if len(episodes) != catalog["episode_count"]:
        errors.append("episode count does not match catalog")
    if len({episode["id"] for episode in episodes}) != len(episodes):
        errors.append("duplicate episode id in catalog")

    for episode in episodes:
        episode_id = episode["id"]
        production = paths["production_root"] / episode_id
        final_video = production / "final/video.mp4"
        narration = paths["content_root"] / "episodes" / episode_id / "01_narration.md"
        story = paths["content_root"] / "episodes" / episode_id / "03_story_package.yaml"
        qa = reports.get(episode_id)
        for required in (narration, story, production / "production_plan.yaml"):
            if not required.is_file():
                errors.append(f"missing source: {required}")

        release = paths["publish_root"] / episode_id
        ensure_directory(release, args.check, errors)
        if qa is not None and release_eligible(qa):
            if not final_video.is_file():
                errors.append(f"missing animation master: {final_video}")
            elif sha256(final_video) != qa["sha256"]:
                errors.append(f"video hash differs from QA: {episode_id}")
            else:
                ensure_copy(final_video, release / "video.mp4", qa["sha256"], args.check, errors)
            package_text = package_markdown(catalog, episode, qa)
        else:
            errors.append(f"animation delivery not eligible: {episode_id}")
            ensure_absent(release / "video.mp4", errors)
            package_text = blocked_package_markdown(catalog, episode, qa)
        ensure_file(
            release / "发布交付包.md",
            package_text,
            args.check,
            errors,
        )
        ensure_file(
            release / "小红书文案.txt",
            platform_text(episode, "xiaohongshu"),
            args.check,
            errors,
        )
        ensure_file(
            release / "微信视频号文案.txt",
            platform_text(episode, "channels"),
            args.check,
            errors,
        )

    publish_root = paths["publish_root"]
    ensure_file(
        publish_root / "README.md",
        publish_index(catalog, episodes, reports),
        args.check,
        errors,
    )
    ensure_file(
        publish_root / "manifest.json",
        publish_manifest(catalog, episodes, reports),
        args.check,
        errors,
    )
    if errors:
        print(json.dumps({"status": "failed", "errors": errors}, ensure_ascii=False, indent=2))
        raise SystemExit(1)
    print(
        json.dumps(
            {
                "status": "verified" if args.check else "built",
                "series_id": catalog["series_id"],
                "episodes": len(episodes),
                "publish_root": str(publish_root),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
