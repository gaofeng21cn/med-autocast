#!/usr/bin/env python3
"""Flatten selected paper-theatre deliveries without rendering or changing review states."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import tempfile
import yaml

from delivery_layout import locations, install, save


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def organize(workspace: Path, series: str, episode: str) -> dict:
    loc = locations(workspace, series, episode)
    pointer = json.loads(loc['pointer'].read_text())
    manifest_path = Path(pointer['manifest'])
    if not manifest_path.is_absolute():
        manifest_path = workspace / manifest_path
    data = json.loads(manifest_path.read_text())
    if data.get('schema') != 'paper_review_delivery/v1' or data.get('series_id') != series or data.get('episode_id') != episode:
        raise ValueError('整理需要精确的纸剧场当前交付记录；不猜目录最大版本')
    if pointer.get('layout') == 'latest_only' and manifest_path == loc['record'] / 'manifest.json':
        return {'episode': episode, 'status': 'already_latest_only'}
    video = (manifest_path.parent / data['video']).resolve()
    project = Path(data['project'])
    current = json.loads((project / 'out/current.json').read_text())
    if digest(video) != data['sha256'] or data['sha256'] != current['sha256']:
        raise ValueError('当前交付字节与制作母版不一致，请先修复当前指针')
    scratch = workspace / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='delivery-layout-', dir=scratch) as folder:
        user, record = Path(folder) / 'publish', Path(folder) / 'record'
        user.mkdir(); record.mkdir()
        shutil.copy2(video, user / 'video.mp4')
        subtitles = manifest_path.parent / data.get('artifacts', {}).get('subtitles', 'subtitles.srt')
        shutil.copy2(subtitles, user / 'subtitles.srt')
        for name in ('封面.jpg', '小红书文案.txt', '微信视频号文案.txt'):
            source = loc['user'] / name
            if source.is_file():
                shutil.copy2(source, user / name)
        for file in manifest_path.parent.iterdir():
            if file.is_file() and file.name not in ('video.mp4', 'subtitles.srt', 'manifest.json', '.DS_Store'):
                shutil.copy2(file, record / file.name)
        relative = lambda file: os.path.relpath(file, loc['record'])
        data['video'] = relative(loc['user'] / 'video.mp4')
        data['delivery_layout'] = 'latest_only'
        artifacts = data.setdefault('artifacts', {})
        artifacts['video'] = data['video']
        artifacts['subtitles'] = relative(loc['user'] / 'subtitles.srt')
        save(record / 'manifest.json', data)
        title = yaml.safe_load((project / 'project.json').read_text()).get('title', episode)
        (user / '发布交付包.md').write_text(
            f'# {title}\n\n[观看视频](video.mp4) · [小红书文案](小红书文案.txt) · [视频号文案](微信视频号文案.txt)\n\n'
            '本目录仅保留最新版。使用 video.mp4 上传、封面.jpg 设置封面，再复制对应平台文案。\n\n'
            '审核状态见交付首页；本次目录整理未改变审核结论，也未上传平台。\n', encoding='utf-8')
        result = install(workspace, series, episode, user, record)
    if digest(loc['user'] / 'video.mp4') != current['sha256']:
        raise ValueError('目录整理后的视频字节回读不一致')
    return {'episode': episode, 'status': 'organized_and_read_back', **result,
            'sha256': current['sha256'], 'review_states_unchanged': True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, required=True)
    parser.add_argument('--series', required=True)
    parser.add_argument('--episode')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    config = yaml.safe_load((workspace / 'workbench.yaml').read_text())
    ids = [args.episode] if args.episode else list(config['series'][args.series]['episodes'])
    results = [organize(workspace, args.series, episode) for episode in ids]
    print(json.dumps({'series': args.series, 'episodes': results}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
