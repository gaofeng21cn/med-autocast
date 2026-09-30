#!/usr/bin/env python3
"""Initialize an empty workspace without overwriting existing user data."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

SOURCE = Path(__file__).resolve().parents[1]


def initialize(target: Path) -> dict:
    target = target.resolve()
    if target.exists() and (not target.is_dir() or any(target.iterdir())):
        raise ValueError('只初始化空目录；已有工作区请运行其 setup_workbench.sh，不覆盖专用代码和档案')
    if target == SOURCE or SOURCE.is_relative_to(target) or target.is_relative_to(SOURCE):
        raise ValueError('制作工作区应位于随包 runtime/workbench 之外，避免混入插件文件')
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
    for name in ('content', 'profiles', 'assets', 'productions', 'publish',
                 'deliveries', 'archive', 'work', 'output', 'tmp'):
        (target / name).mkdir(exist_ok=True)
    (target / 'README.md').write_text('''# 医学动画工作台

先运行 `bash scripts/setup_workbench.sh --check`。告诉 Med Auto Cast 主题、受众和时长即可开始；首步先建立作者/医生形象、品牌识别和声音基线，再进入纸剧场分镜与素材准备。默认本机 JS 手绘拼贴；有授权参考声线时使用本机 IndexTTS，Edge TTS 只在没有专用声线或用户明确跳过时保底。

- content：医学事实、患者问题地图、系列和单集故事包。
- profiles：作者/医生、品牌、声线和部署档案。
- assets：已审、授权或生成的稳定可分层素材。
- productions：按系列/单集保存分镜、素材、JS、候选、QA 和 final。
- publish：当前审看/发布入口；不代表已获医学发布批准。
- deliveries：内部交接记录；archive：历史只读候选；work/output/tmp：运行态、批量输出和可重建临时文件。

新单集顺序是“患者问题地图 -> 系列故事圣经 -> episode_blueprint/beat grid -> 粗动态分镜 -> 透明分层素材准入 -> JS 实现 -> 连续预览 -> QA -> 编码”。角色、语气和医学审核从 pending 开始；不使用技术 smoke 代替质量样片。
''', encoding='utf-8')
    (target / '.gitignore').write_text('.venv/\nnode_modules/\n__pycache__/\noutputs/\n.env\n', encoding='utf-8')
    return {'status': 'initialized', 'workspace': str(target), 'author_baseline': 'pending',
            'next': '运行 scripts/setup_workbench.sh；首次创作先确定作者形象与声音基线'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', required=True, type=Path)
    args = parser.parse_args()
    try:
        print(json.dumps(initialize(args.workspace), ensure_ascii=False))
    except (OSError, ValueError) as exc:
        parser.exit(1, str(exc) + '\n')


if __name__ == '__main__':
    main()
