#!/usr/bin/env python3
"""Initialize or non-destructively upgrade a Med Auto Cast workspace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from workspace_layout import ensure

SOURCE = Path(__file__).resolve().parents[1]


def _ensure_first_draft_record(target: Path) -> dict:
    """Provide an editable guide, never a second production-state owner."""
    record = target / 'work/first-draft-review.md'
    created = not record.exists()
    if created:
        record.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / 'templates/series/08_first_draft_review.md', record)
    return {'path': str(record), 'created': created,
            'purpose': '初稿复核工作记录；引用真实系列产物，不代表审核通过'}


def _ensure_asset_library_config(target: Path) -> dict:
    """Add the optional external asset-repo pointer without rewriting existing YAML."""
    config = target / 'workbench.yaml'
    if not config.is_file():
        return {'path': str(config), 'created': False, 'status': 'missing_workbench'}
    text = config.read_text(encoding='utf-8')
    if any(line.strip() == 'asset_library:' for line in text.splitlines()):
        return {'path': str(config), 'created': False, 'status': 'present'}
    block = '''\nasset_library:\n  mode: optional_external_repo\n  root: ../mac-media-assets\n  catalog: ../mac-media-assets/catalog/assets.jsonl\n  query_tool: ../mac-media-assets/tools/query_assets.py\n  sync_tool: ../mac-media-assets/tools/sync_from_workbench.py\n  verify_tool: ../mac-media-assets/tools/verify_catalog.py\n  note: 外部资产库不可用时继续本地工作台流程并记录质量债，不阻断 Progress First\n'''
    config.write_text(text.rstrip() + block, encoding='utf-8')
    return {'path': str(config), 'created': True, 'status': 'added_optional_pointer'}


def _check_location(target: Path) -> Path:
    target = target.resolve()
    # A copied workbench owns its top-level scripts and may upgrade itself;
    # the packaged runtime/workbench tree has no workbench.yaml and remains
    # protected from accidental initialization.
    if target == SOURCE and (target / 'workbench.yaml').is_file():
        return target
    if target == SOURCE or SOURCE.is_relative_to(target) or target.is_relative_to(SOURCE):
        raise ValueError('制作工作区应位于随包 runtime/workbench 之外，避免混入插件文件')
    return target


def initialize(target: Path) -> dict:
    """Create a new isolated workspace and its explicit directory contract."""
    target = _check_location(target)
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('只初始化空目录；已有工作区请使用 --upgrade 或 setup_workbench.sh，不覆盖专用代码和档案')
    target.mkdir(parents=True, exist_ok=True)
    for name in ('scripts', 'backends', 'templates', 'docs'):
        shutil.copytree(SOURCE / name, target / name,
                        ignore=shutil.ignore_patterns('__pycache__', '.venv', 'node_modules', '*.pyc'))
    for name in ('requirements.txt', 'requirements-alignment.txt', 'package.json', 'package-lock.json'):
        if (SOURCE / name).is_file():
            shutil.copyfile(SOURCE / name, target / name)
    author = target / 'profiles/authors/example_author.yaml'
    author.parent.mkdir(parents=True)
    # An anonymous, no-presenter profile is a technical starting point, never an approved doctor identity.
    author.write_text('''schema: medical_video_author_profile/v1
profile_id: example_author
display_name: 医学科普作者（待设定）
language: zh-CN
baseline:
  version: null
  asset_authorization_refs: []
  review:
    identity: pending
    visual: pending
    voice: pending
    style: pending
    evidence_refs: []
persona:
  tone: [clear, calm, trustworthy]
voice:
  mode: edge
  preferred_backend_definition: edge_tts
  reference_audio: null
  direction: 自然、平静、清晰；全篇固定语速、音高和距离感
visual_identity:
  enabled: false
  character_reference: null
brand:
  enabled: false
  avatar_source: null
visual_format:
  requirement: hand_drawn_explainer_animation
  style: hand_drawn_collage
  style_id: paper_collage
  renderer: canvas2d
  style_profile_ref: templates/animation/animation_style_registry.json
  animation_mode: hand_drawn_patient_explainer_animation
  precise_medical_visuals: reviewed_insert_only
  default_shot_seconds: [5, 10]
  simple_single_action_max_seconds: 14
  width: 1280
  height: 720
  fps: 24
audio_mix:
  background_music: null
  lyric_free: true
''', encoding='utf-8')
    backend = target / 'profiles/backends/example_deployment.yaml'
    backend.parent.mkdir(parents=True)
    shutil.copyfile(SOURCE / 'templates/profiles/backend_profile.example.yaml', backend)
    shutil.copyfile(SOURCE / 'templates/workbench.example.yaml', target / 'workbench.yaml')
    layout = ensure(target)
    first_draft = _ensure_first_draft_record(target)
    asset_library = _ensure_asset_library_config(target)
    (target / 'README.md').write_text('''# 医学动画工作台

先运行 `bash scripts/setup_workbench.sh --check`。告诉 Med Auto Cast 主题、受众和时长即可开始；首步先建立作者/医生形象、品牌识别和声音基线，再进入纸剧场分镜与素材准备。默认本机 JS 手绘拼贴；有授权参考声线时使用本机 IndexTTS，Edge TTS 只在没有专用声线或用户明确跳过时保底。

- content：医学事实、患者问题地图、系列和单集故事包。
- profiles：作者/医生、品牌、声线和部署档案。
- assets：工作台本地缓存、兼容入口和已登记的稳定可分层素材；跨工作区统一资产库由 `workbench.yaml.asset_library` 指向。
- productions：按系列/单集保存分镜、素材、JS、候选、QA 和 final。
- publish：面向用户的唯一最新版；直接取视频、封面和平台文案，不放版本子目录。
- deliveries：内部 Stage 交接与机器清单；archive/deliveries：交付旧版；work/output/tmp：运行态、批量输出和可重建临时文件。

新单集顺序是“患者问题地图 -> 系列故事圣经 -> 资产库查询 -> episode_blueprint/beat grid -> 粗动态分镜 -> 透明分层素材准入 -> JS 实现 -> 连续预览 -> QA -> 编码”。角色、语气和医学审核从 pending 开始；不使用技术 smoke 代替质量样片。外部资产库由 `workbench.yaml.asset_library` 指向；库不可用时继续本地缓存或新创候选，不把同步失败当成启动门。

初稿复核入口是 `work/first-draft-review.md` 和 `docs/28_初版质量与高效返修流程.md`。先做代表镜头与完整代表集，检查真实 alpha、认知比例、去文字事件和首句/术语整段声音；源码更新后重新 build/preview，再 render 并回读实际媒体。欠项保留候选和可用成果，不作为表单启动门。
''', encoding='utf-8')
    (target / '.gitignore').write_text(
        '.venv/\nnode_modules/\n__pycache__/\n*.pyc\n.env\n.DS_Store\n'
        '# 可重建批量输出和临时文件；work/ 可能包含恢复回执，保留其可追踪性\n'
        'output/\ntmp/\n',
        encoding='utf-8',
    )
    return {'status': 'initialized', 'workspace': str(target), 'author_baseline': 'pending',
            'layout': layout,
            'first_draft_review': first_draft,
            'asset_library': asset_library,
            'next': '运行 scripts/setup_workbench.sh；首次创作先确定作者形象与声音基线，再查询资产库'}


def upgrade(target: Path) -> dict:
    """Add missing layout roots and markers without changing existing files."""
    target = _check_location(target)
    if not target.is_dir() or not (target / 'workbench.yaml').is_file():
        raise ValueError('升级需要包含 workbench.yaml 的已有工作区；不自动猜测目录身份')
    layout = ensure(target)
    first_draft = _ensure_first_draft_record(target)
    asset_library = _ensure_asset_library_config(target)
    return {
        'status': 'upgraded' if layout['created'] or first_draft['created'] or asset_library['created'] else 'already_present',
        'workspace': str(target),
        'layout': layout,
        'first_draft_review': first_draft,
        'asset_library': asset_library,
        'next': '运行 scripts/environment_check.py --workspace <目录> --pretty；缺项是可修复诊断，不代表内容或发布通过',
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    parser.add_argument('--upgrade', action='store_true', help='为已有工作区补齐缺失目录和入口标记，不复制或覆盖文件')
    args = parser.parse_args()
    try:
        result = upgrade(args.workspace) if args.upgrade else initialize(args.workspace)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
