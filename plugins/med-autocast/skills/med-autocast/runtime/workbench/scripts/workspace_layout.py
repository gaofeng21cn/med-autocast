#!/usr/bin/env python3
"""Shared, non-destructive workspace layout facts for Med Auto Cast."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


LAYOUT_SCHEMA = "medical_video_workspace_layout/v1"
LAYOUT_VERSION = "2026-10-latest-delivery"

# These roots describe ownership, not completion. Empty roots are created so a
# new workspace has predictable places for each kind of work.
DIRECTORIES: dict[str, str] = {
    "content": "医学事实、系列计划、旁白和故事包",
    "profiles/authors": "作者/医生、品牌与声线基线",
    "profiles/backends": "本机后端部署实例",
    "assets/keyframes": "已审关键帧与医学参考索引",
    "assets/paper-theatre": "跨集复用的透明纸件、环境、组件、动作和声音",
    "assets/audio": "已授权且可复用的音乐和拟音",
    "assets/references": "来源、许可和被否决素材的参考记录",
    "productions": "按系列和单集保存当前生产工程",
    "publish": "面向用户的唯一最新版：视频、封面、字幕、发布文案和简明首页",
    "deliveries": "内部 Stage 交接、审核材料与精确交付清单",
    "archive": "只读历史与被替换版本",
    "work/runs": "可恢复的运行状态和后端回执",
    "work/review": "联系表、切点和审片工作文件",
    "work/browser": "浏览器审片临时会话",
    "output/previews": "可重建预览和抽帧",
    "output/contact-sheets": "可重建联系表和动作 strip",
    "tmp/cache": "可删除的缓存",
    "tmp/pdfs": "可重建的 PDF 中间文件",
}


def manifest(root: Path) -> dict[str, Any]:
    return {
        "schema": LAYOUT_SCHEMA,
        "layout_version": LAYOUT_VERSION,
        "managed_by": "med-autocast",
        "authoritative_roots": {
            "content": "content",
            "profiles": "profiles",
            "assets": "assets",
            "productions": "productions",
            "publish": "publish",
            "deliveries": "deliveries",
        },
        "runtime_roots": {
            "work": "work",
            "output": "output",
            "tmp": "tmp",
            "archive": "archive",
        },
        "delivery_policy": {
            "layout": "latest_only",
            "user_episode": "publish/<series>/<episode>/",
            "internal_receipt": "deliveries/<series>/<episode>/manifest.json",
            "stage_handoff": "deliveries/<series>/stages/<stage_id>/",
            "history": "archive/deliveries/<series>/<episode>/<revision>/",
            "versions_inside_publish": False,
            "review_state_separate_from_location": True,
        },
        "compatibility": {
            "legacy_flat_productions": True,
            "existing_absolute_paths_unchanged": True,
        },
        "progress_first": {
            "missing_layout_is_repairable": True,
            "directory_presence_is_not_quality_approval": True,
        },
        "workspace_root": str(root.resolve()),
    }


def status(root: Path) -> dict[str, Any]:
    root = root.resolve()
    missing = [name for name in DIRECTORIES if not (root / name).is_dir()]
    marker = root / "workspace.manifest.json"
    return {
        "schema": LAYOUT_SCHEMA,
        "layout_version": LAYOUT_VERSION,
        "state": "ready" if not missing else "partial",
        "workspace_manifest": str(marker),
        "workspace_manifest_exists": marker.is_file(),
        "expected_directory_count": len(DIRECTORIES),
        "missing_directories": missing,
        "repairable": True,
    }


def _workspace_readme() -> str:
    return """# Med Auto Cast 工作区入口

`workbench.yaml` 是配置入口，`workspace.manifest.json` 是目录职责清单。本文件只说明放置边界，不代表任何内容、素材、动态、声音、医学复核或发布资格已经通过。

| 目录 | 用途 |
| --- | --- |
| `content/` | 医学事实、患者问题、系列计划、旁白和故事包 |
| `profiles/` | 作者/医生、品牌、声线和本机部署档案 |
| `assets/` | 可登记、可追溯、可复用的素材库 |
| `productions/` | `系列/单集/` 的前置、动画、音频、候选、QA 和 `final/` |
| `publish/` | 用户最新版成片、封面、字幕和发布文案；每集目录不含版本子目录 |
| `deliveries/` | 内部 Stage 交接、审核材料和精确 manifest；不是用户交付入口 |
| `archive/` | 只读历史与被替换版本 |
| `work/` | 可恢复运行态和审片工作文件 |
| `output/` | 可重建的预览、抽帧和联系表 |
| `tmp/` | 可删除缓存和中间文件 |

用户从 `publish/<series>/README.md` 或观看页进入，每集直接取 `video.mp4`；过程材料和历史版本不混入交付。Stage 输入输出保留精确引用，阶段记录放 `deliveries/<series>/stages/<stage_id>/`。

新系列使用 `content/<topic>/<series>/` 与 `productions/<series>/<episode>/`。旧作品可以继续使用已登记的扁平路径；升级布局不会搬动、重命名或删除它们。缺少某个目录是可修复的工作区问题，不是制作质量结论。
"""


def ensure(root: Path, *, write_markers: bool = True) -> dict[str, Any]:
    """Create only missing layout directories and markers; never overwrite data."""
    root = root.resolve()
    created: list[str] = []
    for name in DIRECTORIES:
        path = root / name
        if not path.is_dir():
            path.mkdir(parents=True, exist_ok=True)
            created.append(name)

    manifest_path = root / "workspace.manifest.json"
    if write_markers and not manifest_path.exists():
        manifest_path.write_text(
            json.dumps(manifest(root), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        created.append("workspace.manifest.json")

    if write_markers and manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding='utf-8'))
        policy = manifest(root)['delivery_policy']
        if existing.get('delivery_policy') != policy or existing.get('layout_version') != LAYOUT_VERSION:
            existing['delivery_policy'] = policy
            existing['layout_version'] = LAYOUT_VERSION
            manifest_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
            created.append('workspace.manifest.json:delivery_policy')

    readme_path = root / "WORKSPACE.md"
    if write_markers and not readme_path.exists():
        readme_path.write_text(_workspace_readme(), encoding="utf-8")
        created.append("WORKSPACE.md")

    result = status(root)
    result["created"] = created
    result["status"] = "initialized" if created else "already_present"
    return result

