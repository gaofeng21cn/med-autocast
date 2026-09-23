#!/usr/bin/env python3
"""Render the curated keyframe catalog as an offline gallery. Never edit originals.
Run with the project .venv; --check is read-only and verifies files and projections.
"""
import argparse
import csv
import html
import io
import json
import re
import os
from pathlib import Path
from urllib.parse import quote
from PIL import Image, ImageOps

ROOT = Path(os.environ.get("MED_AUTOCAST_WORKSPACE_ROOT", Path(__file__).resolve().parents[1])).resolve()
LIB = ROOT / 'assets/keyframes'


def local_file(value):
    path = (LIB / value).resolve()
    if not path.is_relative_to(LIB.resolve()) or not path.is_file():
        raise ValueError(f'Invalid library file: {value}')
    return path


def read_catalog():
    data = json.loads((LIB / 'catalog.json').read_text())
    if data['schema'] != 'medical_keyframe_library/v1':
        raise ValueError('Unsupported catalog schema')
    ids = set()
    files = set()
    for a in data['assets']:
        if not re.fullmatch(r'[a-zA-Z0-9_-]+', a['id']) or a['id'] in ids:
            raise ValueError(f'Invalid or duplicate asset ID: {a["id"]}')
        ids.add(a['id'])
        path = local_file(a['file'])
        if path in files:
            raise ValueError(f'Duplicate asset file: {path}')
        files.add(path)
        if a['category'] not in data['categories'] or a['series_id'] not in data['series']:
            raise ValueError(f'Unknown category/series: {a["id"]}')
        if path.stat().st_size != a['bytes']:
            raise ValueError(f'Size differs from catalog: {a["id"]}')
        with Image.open(path) as im:
            im.load()
            if list(im.size) != a['dimensions']:
                raise ValueError(f'Dimensions differ from catalog: {a["id"]}')
        for field in ('title', 'purpose', 'reuse_notes', 'admission', 'source'):
            if not a.get(field):
                raise ValueError(f'Missing {field}: {a["id"]}')
    return data


def csv_text(data):
    out = io.StringIO(newline='')
    writer = csv.writer(out)
    writer.writerow(['资产ID', '名称', '分类', '来源系列', '用途', '复用状态', '复用注意', '原图', '宽', '高', '字节数', '原始来源'])
    for a in data['assets']:
        row = [a['id'], a['title'], data['categories'][a['category']], a['series_name'], a['purpose'], a['reuse_status'], '；'.join(a['reuse_notes']), a['file'], *a['dimensions'], a['bytes'], a['source']['path']]
        writer.writerow(["'" + v if isinstance(v, str) and v.startswith(('=', '+', '-', '@')) else v for v in row])
    return out.getvalue()


def gallery_text(data):
    e = html.escape
    def options(items):
        return ''.join(f'<option value="{e(k, quote=True)}">{e(v)}</option>' for k, v in items.items())
    cards = []
    for a in data['assets']:
        terms = ' '.join([a['title'], a['purpose'], a['id'], a['series_name'], data['categories'][a['category']], *a['tags'], *a['reuse_notes']]).lower()
        cards.append(f'''<article class="card" data-id="{a['id']}" data-category="{a['category']}" data-series="{a['series_id']}" data-terms="{e(terms, quote=True)}">
<button class="picture" data-open="{a['id']}" aria-label="查看{e(a['title'])}"><img src="thumbnails/{a['id']}.jpg" alt="{e(a['title'])}" width="640" height="360" loading="lazy"></button>
<div class="body"><div class="eyebrow">{e(data['categories'][a['category']])} · {e(a['series_name'])}</div><h2>{e(a['title'])}</h2><p>{e(a['purpose'])}</p><div class="card-foot"><span>{e(a['reuse_status'])}</span><button class="text-button" data-open="{a['id']}">详情与原图 ↗</button></div></div></article>''')
    payload = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')
    template = '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>医学科普关键帧资产库</title><link rel="icon" href="data:,">
<style>
:root{color-scheme:light;--ink:#203e3a;--muted:#65746f;--line:#dce2da;--paper:#f7f6f0;--green:#245c4e}*{box-sizing:border-box}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.65 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif}header,main,footer{max-width:1520px;margin:auto;padding:32px 40px}header{padding-top:48px;padding-bottom:20px}.kicker{letter-spacing:.2em;font-size:11px;color:var(--green);font-weight:700}h1{font-size:clamp(28px,3vw,42px);line-height:1.3;margin:12px 0}header p{max-width:800px;margin:12px 0;color:var(--muted)}.stats{display:flex;gap:28px;margin:24px 0 0}.stats b{font-size:23px;margin-right:6px}.toolbar{display:grid;grid-template-columns:1fr 210px 190px auto;gap:12px;align-items:end;padding:20px 0;border-top:1px solid var(--line)}label{display:flex;flex-direction:column;font-size:12px;gap:5px;color:var(--muted)}input,select,.reset{height:43px;border:1px solid var(--line);border-radius:8px;background:white;color:var(--ink);padding:0 12px;font:inherit;max-width:100%;min-width:0}button{cursor:pointer}button:focus-visible,a:focus-visible,input:focus-visible,select:focus-visible{outline:3px solid #ca7b41;outline-offset:3px}.result{display:flex;justify-content:space-between;gap:16px;margin:2px 0 20px;color:var(--muted);font-size:13px}.result a,footer a{color:var(--green)}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:24px}.card{background:#fff;border:1px solid var(--line);border-radius:12px;overflow:hidden}.picture{display:block;width:100%;padding:0;border:0;background:#f0eee6}.picture img{display:block;width:100%;height:auto;aspect-ratio:16/9;object-fit:contain}.picture:hover{filter:brightness(.97)}.body{padding:17px 20px}.eyebrow{font-size:11px;color:var(--muted);letter-spacing:.025em}h2{font-size:19px;line-height:1.4;margin:7px 0}.body p{font-size:14px;color:var(--muted);margin:8px 0 18px}.card-foot{border-top:1px solid #edf0eb;padding-top:12px;display:flex;justify-content:space-between;gap:10px;align-items:center;font-size:11px;color:var(--green)}.text-button{border:0;background:none;color:var(--green);padding:3px;font:inherit}#empty{padding:60px;text-align:center;color:var(--muted)}[hidden]{display:none!important}footer{font-size:12px;color:var(--muted);padding-bottom:40px}dialog{width:min(1080px,94vw);max-height:92vh;border:0;padding:0;border-radius:14px;color:var(--ink);background:var(--paper)}dialog::backdrop{background:#122923aa}.modal-head{position:sticky;top:0;background:var(--paper);padding:14px 22px;display:flex;align-items:center;justify-content:space-between;gap:18px;z-index:1}.modal-head h2{margin:0}.close{border:1px solid var(--line);border-radius:8px;padding:7px 14px;background:#fff;color:var(--ink);font:inherit}#full{display:block;width:100%;height:auto;max-height:60vh;object-fit:contain;background:#efede4}.details{padding:20px 28px 30px}.details p{margin:9px 0}.details ul{padding-left:22px}.details .source{word-break:break-all;font-size:12px;color:var(--muted)}.download{display:inline-block;background:var(--green);color:#fff;text-decoration:none;border-radius:8px;padding:9px 16px;margin:8px 8px 8px 0}.boundary{padding-top:14px;border-top:1px solid var(--line);font-size:12px;color:var(--muted)}@media(min-width:1450px){.grid{grid-template-columns:repeat(4,minmax(0,1fr))}}@media(max-width:850px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.toolbar{grid-template-columns:1fr 1fr}.search-label{grid-column:1/-1}header,main,footer{padding-left:22px;padding-right:22px}}@media(max-width:540px){.grid{grid-template-columns:1fr}.toolbar{grid-template-columns:1fr 1fr}.reset{grid-column:1/-1}.stats{gap:15px}.stats b{font-size:20px}.result{flex-direction:column;gap:5px}.details{padding:18px}}
</style></head><body>
<header><div class="kicker">MEDICAL VISUAL LIBRARY</div><h1>医学科普关键帧资产库</h1><p>从真实制作中选出的场景、人物关系与物件构图。先找到适合当前解释的画面，再决定复用、派生或补充生成。</p><div class="stats"><span><b>__COUNT__</b>张关键帧</span><span><b>__CATS__</b>类用途</span><span><b>__SERIES__</b>个系列</span></div></header>
<main><div class="toolbar"><label class="search-label">搜索场景或物件<input id="search" type="search" placeholder="例如：俯拍、药盒、家属、日历" autocomplete="off"></label><label>按用途<select id="category"><option value="">全部用途</option>__CATEGORIES__</select></label><label>按系列<select id="series"><option value="">全部系列</option>__SERIES_OPTIONS__</select></label><button class="reset" id="reset">重置筛选</button></div><div class="result"><span id="count" role="status" aria-live="polite"></span><span><a href="catalog.csv" download>下载资产清单 CSV</a> · <a href="README.md">使用与维护说明</a></span></div><section class="grid" aria-label="关键帧目录">__CARDS__</section><p id="empty" hidden>没有匹配的关键帧。试试更短的词，或清除分类筛选。</p></main>
<footer>静态参考不等于生成动作、医学内容或成片已经通过审核。点击图片查看来源和复用注意事项。首批精选目录 · __DATE__</footer>
<dialog id="viewer" aria-labelledby="modal-title"><div class="modal-head"><h2 id="modal-title"></h2><button class="close" id="close">关闭 ×</button></div><img id="full" alt=""><div class="details"><p id="modal-purpose"></p><p id="modal-meta"></p><ul id="notes"></ul><a class="download" id="download" download>保存原图</a><a id="open-original" target="_blank" rel="noopener">单独查看原图 ↗</a><p class="source" id="source"></p><p class="source" id="review"></p><p class="boundary">复用前看原图，核对人物身份、画幅与当前旁白。数值、设备步骤和医学关系另审；跨集复用仍需避免整篇雷同。</p></div></dialog>
<script type="application/json" id="catalog-data">__DATA__</script><script>
const catalog=JSON.parse(document.getElementById('catalog-data').textContent), assets=new Map(catalog.assets.map(a=>[a.id,a]));
const q=document.getElementById('search'), cat=document.getElementById('category'), series=document.getElementById('series'), cards=[...document.querySelectorAll('.card')], viewer=document.getElementById('viewer');
function filter(){const terms=q.value.toLowerCase().trim().split(/\\s+/).filter(Boolean);let n=0;for(const c of cards){const match=(!cat.value||c.dataset.category===cat.value)&&(!series.value||c.dataset.series===series.value)&&terms.every(t=>c.dataset.terms.includes(t));c.hidden=!match;n+=Number(match)}document.getElementById('count').textContent=`显示 ${n} / ${cards.length} 张`;document.getElementById('empty').hidden=n!==0}
q.addEventListener('input',filter);cat.addEventListener('change',filter);series.addEventListener('change',filter);document.getElementById('reset').onclick=()=>{q.value='';cat.value='';series.value='';filter();q.focus()};
for(const b of document.querySelectorAll('[data-open]'))b.onclick=()=>{const a=assets.get(b.dataset.open),url=a.file.split('/').map(encodeURIComponent).join('/');document.getElementById('modal-title').textContent=a.title;const img=document.getElementById('full');img.src=url;img.alt=a.title;document.getElementById('modal-purpose').textContent=a.purpose;document.getElementById('modal-meta').textContent=`${catalog.categories[a.category]} · ${a.series_name} · ${a.dimensions.join(' × ')} · ${a.reuse_status}`;document.getElementById('notes').replaceChildren(...a.reuse_notes.map(t=>{const li=document.createElement('li');li.textContent=t;return li}));document.getElementById('download').href=url;document.getElementById('open-original').href=url;document.getElementById('source').textContent=`资产：${a.file} ｜ 原始来源：${a.source.path}`;document.getElementById('review').textContent=`入库查看：${a.admission.method}。${a.character_scope}。`;viewer.showModal()};
document.getElementById('close').onclick=()=>viewer.close();viewer.addEventListener('click',e=>{if(e.target===viewer){const r=viewer.getBoundingClientRect();if(e.clientX<r.left||e.clientX>r.right||e.clientY<r.top||e.clientY>r.bottom)viewer.close()}});filter();
</script></body></html>'''
    values = {'__COUNT__': str(len(data['assets'])), '__CATS__': str(len(data['categories'])), '__SERIES__': str(len({a['series_id'] for a in data['assets']})), '__CATEGORIES__': options(data['categories']), '__SERIES_OPTIONS__': options(data['series']), '__CARDS__': '\n'.join(cards), '__DATE__': e(data['updated_at']), '__DATA__': payload}
    # Substitute once so text inside catalog entries cannot be interpreted as a template token.
    return re.sub('|'.join(map(re.escape, values)), lambda m: values[m.group()], template)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='read-only verification of catalog and generated files')
    args = parser.parse_args()
    data = read_catalog()
    outputs = {'index.html': gallery_text(data).encode(), 'catalog.csv': ('\ufeff' + csv_text(data)).encode()}
    thumbs = LIB / 'thumbnails'
    if not args.check:
        thumbs.mkdir(exist_ok=True)
    for a in data['assets']:
        target = thumbs / (a['id'] + '.jpg')
        with Image.open(local_file(a['file'])) as im:
            preview = ImageOps.contain(im.convert('RGB'), (640, 360))
            buf = io.BytesIO()
            preview.save(buf, format='JPEG', quality=86)
        expected = buf.getvalue()
        if args.check:
            if not target.is_file() or target.read_bytes() != expected:
                raise ValueError(f'Missing/stale thumbnail: {a["id"]}')
        else:
            target.write_bytes(expected)
    for name, expected in outputs.items():
        path = LIB / name
        if args.check:
            if not path.is_file() or path.read_bytes() != expected:
                raise ValueError(f'Missing/stale generated file: {name}')
        else:
            path.write_bytes(expected)
    print(json.dumps({'status': 'passed', 'mode': 'check' if args.check else 'build', 'assets': len(data['assets']), 'categories': len(data['categories']), 'library': str(LIB)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
