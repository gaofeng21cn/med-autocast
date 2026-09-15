#!/usr/bin/env python3
"""Package one explicitly selected review revision without rendering or approval."""
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import tempfile

from build_release_packages import platform_text
from workbench_config import ROOT, load_yaml, series_paths

sys.path.insert(0, os.environ.get('OPL_MEDCAST_HELPERS_ROOT', str(Path(__file__).resolve().parents[2] / 'native_helpers')))
from workbench_adapter import preflight_native


def package_review(series, episode, plan, master, review, source_review=None, technical_qa=None):
    paths = series_paths(series)
    if not episode or Path(episode).name != episode or episode in ('.', '..'):
        raise ValueError('无效集号')
    catalog = load_yaml(paths['release_catalog'])
    entries = [e for e in catalog.get('episodes', []) if e.get('id') == episode]
    if len(entries) != 1:
        raise ValueError('文案目录缺少本集或集号重复')
    record = json.loads(review.read_text())
    if record.get('episode', record.get('episode_id')) != episode:
        raise ValueError('审看记录必须明确绑定当前集号')
    pub = paths['publish_root'].resolve()
    pub.mkdir(parents=True, exist_ok=True)
    manifest_path = pub/'manifest.json'
    before = manifest_path.read_bytes() if manifest_path.exists() else None
    manifest = json.loads(before) if before else {
        'schema':'medical_video_review_package/v1', 'series_id':series,
        'status':'review_delivery', 'public_upload':'pending', 'episodes':[]}
    if manifest.get('schema') != 'medical_video_review_package/v1' or manifest.get('series_id') != series:
        raise ValueError('现有清单不是审看包 v1；正式 final 合同使用原匹配包器，不能混写')
    if len([e for e in manifest['episodes'] if (e.get('id') or e.get('episode_id')) == episode]) > 1:
        raise ValueError('现有发布清单集号重复')
    with tempfile.TemporaryDirectory(prefix='.medcast-review-', dir=pub) as folder:
        stage = Path(folder); target = stage/episode; target.mkdir()
        plan_data = load_yaml(plan)
        ep = paths['production_root']/episode
        srt = (ep/plan_data['subtitles']['source']).resolve()
        shutil.copy2(master, target/'video.mp4')
        shutil.copy2(srt, target/'字幕.srt')
        shutil.copy2(review, target/'审看记录.json')
        if technical_qa:shutil.copy2(technical_qa, target/'技术检查.json')
        for platform, name in [('xiaohongshu','小红书文案.txt'),('channels','微信视频号文案.txt')]:
            (target/name).write_text(platform_text(entries[0], platform), encoding='utf-8')
        (target/'发布交付包.md').write_text(
            f'# {entries[0].get("title", episode)}\n\n本包用于审看，复核结论以审看记录为准。\n\n'
            f'制作单：`{plan}`\n\n母版：`{master}`\n\n'
            '视频、字幕和双平台文案均为真实文件。打包不新增技术、动态、听感或医学批准，也不代表平台上传。\n', encoding='utf-8')
        entry = {'id':episode, 'title':entries[0].get('title',episode), 'source':str(master),
                 'video_status':'review_video_delivered','copy_status':'catalog_materialized',
                 'revision':record.get('revision', plan_data.get('version'))}
        probe_manifest={'schema':manifest['schema'],'series_id':series,'episodes':[entry]}
        stage_manifest=stage/'manifest.json'
        stage_manifest.write_text(json.dumps(probe_manifest,ensure_ascii=False,indent=2)+'\n')
        preflight_native(ROOT,series,episode,str(plan),str(master),str(stage_manifest),str(source_review) if source_review else None)
        updated = [entry if (e.get('id') or e.get('episode_id')) == episode else e for e in manifest['episodes']]
        if not any((e.get('id') or e.get('episode_id')) == episode for e in manifest['episodes']):
            updated.append(entry)
        manifest['episodes']=updated
        # A former all-series ready claim cannot survive a new pending review revision.
        manifest['status']='review_delivery_with_individual_review_states'
        for key in ('technical_qa','full_motion_review','full_listening','medical_review'):
            if key in manifest:manifest[key]='see_individual_review_records'
        staged_manifest=stage/'updated-manifest.json'
        staged_manifest.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
        if (manifest_path.read_bytes() if manifest_path.exists() else None) != before:
            raise ValueError('发布清单已被另一执行者修改，停止覆盖')
        destination=pub/episode
        backup=None
        if destination.exists():
            backup=pub/'archive'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')/episode
            backup.parent.mkdir(parents=True)
            if before is not None:(backup.parent/'manifest.json').write_bytes(before)
            destination.rename(backup)
        installed=False
        try:
            target.rename(destination);installed=True
            os.replace(staged_manifest,manifest_path)
            result=preflight_native(ROOT,series,episode,str(plan),str(master),str(manifest_path),str(source_review) if source_review else None)
        except Exception:
            if installed:shutil.rmtree(destination)
            if backup:backup.rename(destination)
            if before is not None:manifest_path.write_bytes(before)
            elif manifest_path.exists():manifest_path.unlink()
            raise
    return {'status':'packaged_and_read_back','episode_id':episode,'publish_directory':str(destination),
            'previous_delivery':str(backup) if backup else None,'video_bytes_equal':result['video_bytes_equal'],
            'platform_copy_equal':result['platform_copy_equal'],'review_claims':result['review_claims'],
            'quality_debt':result['quality_debt'],'publication_authorized':False,'uploaded':False}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--series',required=True);parser.add_argument('--episode',required=True)
    for name in ('plan','master','review'):parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--source-review',type=Path)
    parser.add_argument('--technical-qa',type=Path)
    a=parser.parse_args()
    result=package_review(a.series,a.episode,a.plan.resolve(),a.master.resolve(),a.review.resolve(),a.source_review.resolve() if a.source_review else None,a.technical_qa.resolve() if a.technical_qa else None)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
