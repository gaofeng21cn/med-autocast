#!/usr/bin/env python3
"""Human-facing latest delivery navigation and explicit, recoverable layout migration."""
from __future__ import annotations

import argparse
import copy
from datetime import datetime, timezone
import hashlib
import html
import json
import os
from pathlib import Path
import re
import shutil
from urllib.parse import quote, unquote

import yaml
from delivery_layout import locations


def load_config(workspace):
    return yaml.safe_load((workspace / 'workbench.yaml').read_text(encoding='utf-8')) or {}


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def folder_name(value):
    # Only filesystem constraints; meaning and preferred titles belong to the director.
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '-', str(value)).strip(' .-_')
    if not name or name in ('.', '..'):
        raise ValueError('交付名称不能为空或越出目录')
    while len(name.encode('utf-8')) > 180:
        name = name[:-1]
    return name


def catalog_for(workspace, row):
    ref = row.get('release_catalog')
    if not ref or not (workspace / ref).is_file():
        return {}
    return yaml.safe_load((workspace / ref).read_text(encoding='utf-8')) or {}


def episode_folder(episode):
    number = episode.get('number', episode.get('id', '').split('_')[0])
    digits = re.sub(r'[^0-9]', '', str(number))
    prefix = f'{int(digits):02d}' if digits else folder_name(number)
    return prefix + '_' + folder_name(episode.get('title') or episode['id'])


def planned_names(workspace, config, series):
    row = config['series'][series]
    delivery = row.setdefault('delivery', {})
    catalog = catalog_for(workspace, row)
    delivery.setdefault('display_name', folder_name(catalog.get('series_title') or row.get('title') or series))
    names = delivery.setdefault('episode_dirs', {})
    for episode in catalog.get('episodes', []):
        names.setdefault(episode['id'], episode_folder(episode))
    publish = workspace / config.get('directories', {}).get('publish', 'publish')
    target = publish / folder_name(delivery['display_name'])
    if len(set(names.values())) != len(names):
        raise ValueError(f'{series}: 两个集号指向同一个用户目录')
    return target


def prepare_names(workspace, series):
    """Name a new delivery; existing media move only via explicit --migrate."""
    config = load_config(workspace)
    if config.get('delivery_policy', {}).get('naming') != 'localized_titles':
        return {'status': 'existing_layout'}
    before = copy.deepcopy(config)
    target = planned_names(workspace, config, series)
    row = config['series'][series]
    current = workspace / row.get('publish_root', f'publish/{series}')
    if current != target and current.is_dir() and any(current.iterdir()):
        return {'status': 'migration_needed', 'blocks_stage_progress': False,
                'note': '已有交付保留原路径；运行 publish_catalog --migrate 后切换中文目录'}
    row['publish_root'] = str(target.relative_to(workspace))
    if config != before:
        (workspace / 'workbench.yaml').write_text(yaml.safe_dump(config, allow_unicode=True, sort_keys=False), encoding='utf-8')
    return {'status': 'names_registered', 'publish_root': str(target)}


def href(path, base):
    return quote(os.path.relpath(path, base).replace(os.sep, '/'), safe='/._-')


STYLE = '''body{margin:0;background:#f7f4ed;color:#263a35;font:16px/1.65 system-ui,-apple-system,sans-serif}main{max-width:1180px;margin:auto;padding:36px 24px 70px}h1{font-size:32px;margin:16px 0 4px}h2{font-size:23px}a{color:#245d50;text-underline-offset:3px}button{font:inherit;color:#245d50;background:transparent;border:0;padding:0;cursor:pointer;text-decoration:underline;text-underline-offset:3px}nav{display:flex;gap:20px;flex-wrap:wrap}input{box-sizing:border-box;width:100%;padding:13px 16px;font:inherit;border:1px solid #d7d1c5;border-radius:8px;margin:22px 0}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,290px),1fr));gap:20px}.card{padding:22px;background:#fffdf7;border:1px solid #e2dccc;border-radius:12px}.card h2{margin:0 0 10px}.muted{color:#69746d;font-size:14px}.actions{display:flex;gap:14px;flex-wrap:wrap;margin-top:12px}.episode{padding:10px 0;border-bottom:1px solid #eee7dc}.poster{width:100%;aspect-ratio:16/9;object-fit:contain;background:#ede8dd;border-radius:6px}video{width:100%;background:#1b2422;border-radius:6px}.hidden{display:none!important}details{margin-top:16px}summary{cursor:pointer}footer{margin-top:32px;color:#69746d;font-size:14px}'''
SEARCH = '''<script>document.querySelector('#search').addEventListener('input',e=>{const q=e.target.value.toLowerCase().trim();document.querySelectorAll('[data-series]').forEach(s=>{let any=false;const title=s.dataset.series.toLowerCase();s.querySelectorAll('[data-episode]').forEach(x=>{const ok=!q||title.includes(q)||x.dataset.episode.toLowerCase().includes(q);x.classList.toggle('hidden',!ok);any||=ok});s.classList.toggle('hidden',!any);const d=s.querySelector('details');if(d&&q)d.open=true})});</script>'''


def page(title, body):
    return '<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><link rel="icon" href="data:,"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + html.escape(title) + '</title><style>' + STYLE + '</style></head><body><main>' + body + '</main>' + SEARCH + '</body></html>\n'


def selected_series(workspace, config):
    result, debt = [], []
    for sid, row in config.get('series', {}).items():
        if row.get('delivery', {}).get('active') is False:
            continue
        root = workspace / row.get('publish_root', f'publish/{sid}')
        if not root.is_dir():
            continue
        catalog = catalog_for(workspace, row)
        episodes = []
        for item in catalog.get('episodes', []):
            eid = item['id']; loc = locations(workspace, sid, eid)
            if not (loc['user'] / 'video.mp4').is_file():
                debt.append({'series': sid, 'episode': eid, 'issue': 'video_pending'})
                continue
            manifest = loc['record'] / 'manifest.json'
            receipt = json.loads(manifest.read_text()) if manifest.is_file() else {}
            episodes.append({'id': eid, 'title': item.get('title', eid), 'directory': loc['user'],
                             'receipt': receipt, 'number': re.sub(r'[^0-9]', '', str(item.get('number', 0))) or '0'})
        episodes.sort(key=lambda e: (int(e['number']), e['id']))
        if episodes:
            result.append({'id': sid, 'title': row.get('delivery', {}).get('display_name') or catalog.get('series_title') or row.get('title') or sid,
                           'root': root, 'episodes': episodes})
    return result, debt


def refresh(workspace, series=None):
    """Generate navigation from actual delivered files; never infer quality approval."""
    workspace = workspace.resolve(); config = load_config(workspace)
    publish = workspace / config.get('directories', {}).get('publish', 'publish')
    publish.mkdir(parents=True, exist_ok=True)
    seasons, debt = selected_series(workspace, config)
    total = sum(len(s['episodes']) for s in seasons)
    rows, cards = [], []
    for season in seasons:
        root = season['root']; title = html.escape(str(season['title']))
        rows.append(f"| {season['title']} | {len(season['episodes'])} | [观看与取用]({href(root / '观看入口.html', publish)}) |")
        ep_rows, ep_cards, summaries, list_items = [], [], [], []
        for ep in season['episodes']:
            directory = ep['directory']; label = f"{int(ep['number']):02d} · {ep['title']}"; safe = html.escape(label)
            url = href(directory / 'video.mp4', root)
            cover = directory / '封面.jpg'
            subtitle = next((directory / name for name in ('subtitles.srt', '字幕.srt') if (directory / name).is_file()), None)
            actions = [('观看视频', directory / 'video.mp4'), ('取用文件', directory), ('小红书文案', directory / '小红书文案.txt'), ('视频号文案', directory / '微信视频号文案.txt')]
            if subtitle: actions.append(('字幕', subtitle))
            action_links = ''.join(f'<a href="{href(path,root)}">{html.escape(name)}</a>' for name, path in actions if path.exists())
            poster = f' poster="{href(cover,root)}"' if cover.is_file() else ''
            ep_cards.append(f'<article class="card" id="{html.escape(ep["id"])}" data-episode="{safe}"><h2>{safe}</h2><video controls preload="none"{poster} src="{url}"></video><div class="actions">{action_links}</div></article>')
            ep_rows.append(f"| {int(ep['number']):02d} | {ep['title']} | [视频]({url}) · [整集文件]({href(directory,root)}/) |")
            list_items.append(f'<div class="episode" data-episode="{safe}"><a href="{href(root / "观看入口.html",publish)}#{quote(ep["id"])}">{safe}</a> · <a href="{href(directory / "video.mp4",publish)}">视频</a></div>')
            summaries.append(f"## {label}\n\n[视频]({url}) · [整集文件]({href(directory,root)}/)\n")
            for name in ('小红书文案.txt', '微信视频号文案.txt'):
                if (directory / name).is_file():
                    summaries.append(f"### {name.removesuffix('.txt')}\n\n" + (directory / name).read_text(encoding='utf-8') + '\n')
        count = len(season['episodes'])
        cards.append(f'<section class="card" data-series="{title}"><h2>{title}</h2><p class="muted">{count} 集 · 当前交付</p><nav><a href="{href(root / "观看入口.html",publish)}">观看与取用</a><a href="{href(root / "全季发布文案.md",publish)}">全季文案</a></nav><details><summary>查看本系列各集</summary>{"".join(list_items)}</details></section>')
        if series is None or season['id'] == series:
            body = f'<button type="button" onclick="history.back()">← 返回上一页</button><h1>{title}</h1><p class="muted">{count} 集 · 每集仅保留当前版本</p><nav><a href="全季发布文案.md">全季发布文案</a><a href="README.md">使用说明</a></nav><input id="search" aria-label="搜索本系列" placeholder="搜索集名"><section data-series="{title}"><div class="grid">{"".join(ep_cards)}</div></section><footer>取用 video.mp4、封面和对应平台文案；审核与上传状态保留原交付结论。</footer>'
            (root / '观看入口.html').write_text(page(str(season['title']), body), encoding='utf-8')
            (root / 'README.md').write_text(f"# {season['title']}\n\n[观看与取用](观看入口.html) · [全季发布文案](全季发布文案.md)\n\n本系列当前交付 {count} 集；各集只保留当前版本的视频、封面、字幕、两平台文案和简明说明。审核与上传状态沿用原记录，目录整理不改变结论。\n\n| 集号 | 内容 | 文件 |\n| --- | --- | --- |\n" + '\n'.join(ep_rows) + '\n', encoding='utf-8')
            (root / '全季发布文案.md').write_text(f"# {season['title']} · 全季发布文案\n\n文案汇总自各集当前 TXT；内容修改回到系列登记的 release_catalog。\n\n" + '\n'.join(summaries), encoding='utf-8')
    body = f'<h1>医学科普 · 观看与发布</h1><p class="muted">{len(seasons)} 个系列 · {total} 集当前交付</p><input id="search" aria-label="搜索主题或集名" placeholder="搜索主题或集名"><div class="grid">{"".join(cards)}</div><footer>观看从系列进入；发布取该集视频、封面和平台文案。过程与历史在工作台交付目录之外保存。</footer>'
    (publish / '观看与发布.html').write_text(page('医学科普 · 观看与发布', body), encoding='utf-8')
    (publish / 'README.md').write_text(f'# 医学科普交付入口\n\n[打开观看与发布首页](观看与发布.html)\n\n当前 {len(seasons)} 个系列、{total} 集；按主题和集名找视频。每集仅保留最新版，视频、封面、字幕和两平台文案在同一个文件夹中。过程与历史另存工作台，审核与上传状态沿用各集记录。\n\n| 系列 | 集数 | 入口 |\n| --- | --- | --- |\n' + '\n'.join(rows) + '\n', encoding='utf-8')
    return {'status': 'navigation_refreshed', 'series': len(seasons), 'episodes': total, 'quality_debt': debt, 'index': str(publish / '观看与发布.html')}


def replace_paths(text, replacements):
    for old, new in sorted(replacements.items(), key=lambda p: len(p[0]), reverse=True):
        text = text.replace(old, new)
    return text


def migrate(workspace, series_ids, archive_series=(), archive_entries=()):
    """Move registered deliveries with exact pointers, byte readback and rollback."""
    workspace = workspace.resolve(); config_path = workspace / 'workbench.yaml'
    before_config = config_path.read_bytes(); config = load_config(workspace)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    archive = workspace / config.get('directories', {}).get('archive','archive') / 'deliveries' / '_layout' / stamp
    archive.mkdir(parents=True)
    snapshots, moves, replacements, proofs = {}, [], {}, []
    config_written = False
    publish = workspace / config.get('directories',{}).get('publish','publish')
    try:
        plans = []
        for sid in series_ids:
            row = config['series'][sid]; old_root = workspace / row.get('publish_root', f'publish/{sid}')
            target_root = planned_names(workspace, config, sid)
            if target_root != old_root and target_root.exists():
                raise ValueError(f'目标主题目录已经存在，保留原件：{target_root}')
            catalog = catalog_for(workspace,row)
            for ep in catalog.get('episodes',[]):
                eid = ep['id']; old_loc = locations(workspace,sid,eid)
                pointer = json.loads(old_loc['pointer'].read_text())
                source = Path(pointer['current']); source = source if source.is_absolute() else workspace / source
                if not source.resolve().is_relative_to(publish.resolve()):
                    raise ValueError('当前用户交付指针越出 publish，拒绝猜测源版本')
                receipt_path = Path(pointer['manifest']); receipt_path = receipt_path if receipt_path.is_absolute() else workspace / receipt_path
                receipt = json.loads(receipt_path.read_text())
                video = source / 'video.mp4'; actual = hashlib.sha256(video.read_bytes()).hexdigest()
                if receipt.get('sha256') and receipt['sha256'] != actual:
                    raise ValueError(f'{sid}/{eid}: 当前交付字节与记录不一致')
                target = target_root / row['delivery']['episode_dirs'][eid]
                if target != source and target.exists():raise ValueError(f'交付目标冲突：{target}')
                plans.append((sid,eid,source,target,receipt,actual))
                proofs.append({'series_id':sid,'episode_id':eid,'from':str(source),'to':str(target),'sha256':actual,'reviews':receipt.get('reviews',{})})
                replacements[str(source)] = str(target)
                replacements[str(source.relative_to(workspace))] = str(target.relative_to(workspace))
            replacements[str(old_root)] = str(target_root)
            replacements[str(old_root.relative_to(workspace))] = str(target_root.relative_to(workspace))
            row['publish_root'] = str(target_root.relative_to(workspace)); row['delivery']['active'] = True
        for sid in archive_series:
            row=config['series'][sid]; source=workspace/row['publish_root']
            destination=archive/'legacy-series'/sid
            if source.exists():
                destination.parent.mkdir(parents=True,exist_ok=True);source.rename(destination);moves.append((source,destination))
            row.setdefault('delivery',{})['active']=False
            row['publish_root']=str(destination.relative_to(workspace))
            replacements[str(source)]=str(destination)
            replacements[str(source.relative_to(workspace))]=str(destination.relative_to(workspace))
        for sid,eid,source,target,receipt,actual in plans:
            if source != target:
                target.parent.mkdir(parents=True,exist_ok=True);source.rename(target);moves.append((source,target))
        # Current receipts keep internal English IDs; only user file references change.
        for sid in series_ids:
            internal=workspace/config.get('directories',{}).get('deliveries','deliveries')/sid
            for path in internal.rglob('*'):
                if path.is_file() and path.suffix in ('.json','.md','.txt'):
                    original=path.read_bytes(); text=original.decode('utf-8'); updated=replace_paths(text,replacements)
                    if updated!=text:
                        snapshots[path]=original
                        backup=archive/'metadata'/path.relative_to(workspace);backup.parent.mkdir(parents=True,exist_ok=True);backup.write_bytes(original)
                        path.write_text(updated,encoding='utf-8')
        for entry in archive_entries:
            source=publish/entry
            if not source.resolve().is_relative_to(publish.resolve()):raise ValueError('归档入口越出 publish')
            if source.exists():
                destination=archive/'navigation'/entry;destination.parent.mkdir(parents=True,exist_ok=True)
                source.rename(destination);moves.append((source,destination))
        for sid in series_ids:
            old_root=workspace/load_config(workspace)['series'][sid]['publish_root']
            new_root=workspace/config['series'][sid]['publish_root']
            if old_root!=new_root and old_root.exists():
                destination=archive/'previous-navigation'/sid;destination.parent.mkdir(parents=True,exist_ok=True)
                old_root.rename(destination);moves.append((old_root,destination))
        config['delivery_policy']={'naming':'localized_titles','layout':'latest_only','index':'观看与发布.html','batch_directories':False}
        if config_path.read_bytes()!=before_config:raise ValueError('配置被另一执行者修改，停止覆盖')
        (archive/'workbench.before.yaml').write_bytes(before_config)
        config_path.write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False),encoding='utf-8')
        config_written = True
        for proof in proofs:
            if hashlib.sha256((Path(proof['to'])/'video.mp4').read_bytes()).hexdigest()!=proof['sha256']:raise ValueError('迁移后视频字节不同')
            receipt=json.loads(locations(workspace,proof['series_id'],proof['episode_id'])['record'].joinpath('manifest.json').read_text())
            if receipt.get('reviews',{})!=proof['reviews']:raise ValueError('迁移不应改变审核状态')
        result={'status':'migrated_and_read_back','series':len(series_ids),'episodes':len(proofs),'archive':str(archive),'video_bytes_unchanged':True,'review_states_unchanged':True,'mapping':proofs,'moves':[{'from':str(a),'to':str(b)} for a,b in moves]}
        write_json(archive/'migration.json',result)
        try:
            result['navigation'] = refresh(workspace)
        except Exception as exc:
            result['navigation'] = {'status': 'diagnostic', 'error': str(exc),
                                    'blocks_stage_progress': False}
        return result
    except Exception:
        if config_written:
            config_path.write_bytes(before_config)
        for path,data in snapshots.items():path.write_bytes(data)
        for source,target in reversed(moves):
            if target.exists():
                # A prior navigation directory may need to return before episodes.
                source.parent.mkdir(parents=True,exist_ok=True)
                if source.is_dir() and not any(source.iterdir()):source.rmdir()
                target.rename(source)
        raise


def check(workspace):
    config=load_config(workspace);publish=workspace/config.get('directories',{}).get('publish','publish')
    errors=[];count=0
    for path in publish.rglob('*'):
        if not path.is_file() or path.suffix not in ('.md','.html'):continue
        text=path.read_text(encoding='utf-8')
        refs=re.findall(r'\]\(([^)]+)\)',text) if path.suffix=='.md' else re.findall(r'(?:href|src)=["\x27]([^"\x27]+)',text)
        for ref in refs:
            ref=unquote(ref).split('#')[0].split('?')[0]
            if not ref or '://' in ref or ref.startswith(('data:','mailto:','javascript:')):continue
            count+=1
            if not (path.parent/ref).exists():errors.append({'file':str(path.relative_to(publish)),'missing':ref})
    seasons,debt=selected_series(workspace,config)
    expected_dirs={s['root'].resolve() for s in seasons}
    for path in publish.iterdir():
        if path.is_dir() and path.resolve() not in expected_dirs:
            errors.append({'unexpected_directory':str(path),'issue':'history_or_batch_inside_publish'})
    if seasons and not (publish/'观看与发布.html').is_file():
        errors.append({'missing':'观看与发布.html'})
    for season in seasons:
        for name in ('README.md','观看入口.html','全季发布文案.md'):
            if not (season['root']/name).is_file():errors.append({'series':season['id'],'missing':name})
        for episode in season['episodes']:
            pointer=locations(workspace,season['id'],episode['id'])['pointer']
            if pointer.is_file():
                selected=Path(json.loads(pointer.read_text())['current'])
                selected=selected if selected.is_absolute() else workspace/selected
                if selected.resolve()!=episode['directory'].resolve():
                    errors.append({'series':season['id'],'episode':episode['id'],'issue':'pointer_directory_mismatch'})
    return {'status':'passed' if not errors else 'diagnostic','series':len(seasons),'episodes':sum(len(s['episodes']) for s in seasons),'links_checked':count,'errors':errors,'quality_debt':debt}


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--workspace',type=Path,default=Path(os.environ.get('MED_AUTOCAST_WORKSPACE_ROOT','.')))
    ap.add_argument('--series',action='append');ap.add_argument('--migrate',action='store_true');ap.add_argument('--check',action='store_true')
    ap.add_argument('--archive-series',action='append',default=[]);ap.add_argument('--archive-entry',action='append',default=[])
    args=ap.parse_args();workspace=args.workspace.resolve()
    if args.migrate:
        if not args.series:ap.error('--migrate 需要显式 --series；不按目录名猜当前作品')
        result=migrate(workspace,args.series,args.archive_series,args.archive_entry)
        print(json.dumps({k:v for k,v in result.items() if k not in ('mapping','moves')},ensure_ascii=False,indent=2))
    elif args.check:
        result=check(workspace);print(json.dumps(result,ensure_ascii=False,indent=2));return 0 if not result['errors'] else 2
    else:
        result=refresh(workspace,args.series[0] if args.series and len(args.series)==1 else None)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0


if __name__=='__main__':raise SystemExit(main())
