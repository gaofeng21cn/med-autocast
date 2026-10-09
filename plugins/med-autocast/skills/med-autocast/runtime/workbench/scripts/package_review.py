#!/usr/bin/env python3
"""Deliver the selected review revision; keep process records outside user files."""
import argparse
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from build_release_packages import platform_text
from delivery_layout import locations, install, save
from workbench_config import ROOT, load_yaml, series_paths

sys.path.insert(0, os.environ.get('MED_AUTOCAST_HELPERS_ROOT', str(Path(__file__).resolve().parents[2] / 'native_helpers')))
from workbench_adapter import preflight_native


def package_review(series, episode, plan, master, review, source_review=None, technical_qa=None):
    paths = series_paths(series)
    loc = locations(ROOT, series, episode)
    catalog = load_yaml(paths['release_catalog'])
    entries = [e for e in catalog.get('episodes', []) if e.get('id') == episode]
    if len(entries) != 1:
        raise ValueError('文案目录缺少本集或集号重复')
    record = json.loads(review.read_text())
    if record.get('episode', record.get('episode_id')) != episode:
        raise ValueError('审看记录必须明确绑定当前集号')
    manifest_path = loc['record'].parent / 'manifest.json'
    legacy = paths['publish_root'] / 'manifest.json'
    selected = manifest_path if manifest_path.exists() else legacy
    before = selected.read_bytes() if selected.exists() else None
    manifest = json.loads(before) if before else {
        'schema': 'medical_video_review_package/v1', 'series_id': series,
        'status': 'review_delivery', 'public_upload': 'pending', 'episodes': []}
    if manifest.get('schema') != 'medical_video_review_package/v1' or manifest.get('series_id') != series:
        raise ValueError('现有清单不是审看包 v1；正式 final 合同使用原匹配包器，不能混写')
    if len([e for e in manifest['episodes'] if (e.get('id') or e.get('episode_id')) == episode]) > 1:
        raise ValueError('现有发布清单集号重复')
    if selected == legacy:
        for e in manifest['episodes']:
            e['video'] = str((legacy.parent / e.get('video', f"{e.get('id') or e.get('episode_id')}/video.mp4")).resolve())
    scratch = ROOT / 'tmp'; scratch.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='review-package-', dir=scratch) as folder:
        stage = Path(folder); target = stage / 'publish'; target.mkdir()
        process = stage / 'record'; process.mkdir()
        plan_data = load_yaml(plan)
        ep = paths['production_root'] / episode
        srt = (ep / plan_data['subtitles']['source']).resolve()
        shutil.copy2(master, target / 'video.mp4')
        shutil.copy2(srt, target / '字幕.srt')
        shutil.copy2(review, process / '审看记录.json')
        if technical_qa: shutil.copy2(technical_qa, process / '技术检查.json')
        for platform, name in [('xiaohongshu', '小红书文案.txt'), ('channels', '微信视频号文案.txt')]:
            (target / name).write_text(platform_text(entries[0], platform), encoding='utf-8')
        (target / '发布交付包.md').write_text(
            f'# {entries[0].get("title", episode)}\n\n[观看视频](video.mp4)。本目录仅保留最新版视频、字幕和双平台文案。\n\n'
            '本包用于审看；完整动态、听感、医学与上传状态以当前审看记录分别确认。\n', encoding='utf-8')
        entry = {'id': episode, 'title': entries[0].get('title', episode), 'source': str(master),
                 'video': str(loc['user'] / 'video.mp4'), 'review': str(loc['record'] / '审看记录.json'),
                 'video_status': 'review_video_delivered', 'copy_status': 'catalog_materialized',
                 'revision': record.get('revision', plan_data.get('version'))}
        probe_entry = {**entry, 'video': str(target / 'video.mp4'), 'review': str(process / '审看记录.json')}
        probe = {'schema': manifest['schema'], 'series_id': series, 'episodes': [probe_entry]}
        save(stage / 'probe.json', probe)
        preflight_native(ROOT, series, episode, str(plan), str(master), str(stage / 'probe.json'), str(source_review) if source_review else None)
        episode_manifest = {'schema': manifest['schema'], 'series_id': series, 'episodes': [entry], 'delivery_layout': 'latest_only'}
        save(process / 'manifest.json', episode_manifest)
        updated = [entry if (e.get('id') or e.get('episode_id')) == episode else e for e in manifest['episodes']]
        if not any((e.get('id') or e.get('episode_id')) == episode for e in manifest['episodes']):
            updated.append(entry)
        manifest['episodes'] = updated
        manifest['status'] = 'review_delivery_with_individual_review_states'
        manifest['delivery_layout'] = 'latest_only'
        for key in ('technical_qa', 'full_motion_review', 'full_listening', 'medical_review'):
            if key in manifest: manifest[key] = 'see_individual_review_records'
        if (selected.read_bytes() if selected.exists() else None) != before:
            raise ValueError('交付清单已被另一执行者修改，停止覆盖')
        result = install(ROOT, series, episode, target, process)
        save(manifest_path, manifest)
        if selected == legacy and legacy.exists():
            # The legacy index is preserved with the replaced episode, outside publish.
            backup = Path(result['previous_delivery']) if result['previous_delivery'] else loc['archive'] / 'legacy-index'
            backup.mkdir(parents=True, exist_ok=True)
            legacy.rename(backup / 'series-manifest.json')
        checked = preflight_native(ROOT, series, episode, str(plan), str(master), str(loc['record'] / 'manifest.json'), str(source_review) if source_review else None)
    return {'status': 'packaged_and_read_back', 'episode_id': episode, 'publish_directory': str(loc['user']),
            'manifest': str(loc['record'] / 'manifest.json'), 'previous_delivery': result['previous_delivery'],
            'video_bytes_equal': checked['video_bytes_equal'], 'platform_copy_equal': checked['platform_copy_equal'],
            'review_claims': checked['review_claims'], 'quality_debt': checked['quality_debt'],
            'publication_authorized': False, 'uploaded': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series', required=True); parser.add_argument('--episode', required=True)
    for name in ('plan', 'master', 'review'): parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--source-review', type=Path); parser.add_argument('--technical-qa', type=Path)
    a = parser.parse_args()
    print(json.dumps(package_review(a.series, a.episode, a.plan.resolve(), a.master.resolve(), a.review.resolve(),
                                  a.source_review.resolve() if a.source_review else None,
                                  a.technical_qa.resolve() if a.technical_qa else None), ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
