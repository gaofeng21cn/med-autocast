#!/usr/bin/env python3
"""Create and render the original, brand-free MAC material/motion study."""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from html import escape

BUNDLE = Path(__file__).resolve().parents[1]
TEMPLATE = BUNDLE / 'templates/animation/paper_theatre'
STYLES = BUNDLE / 'templates/animation/styles'


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n')


def run(command, project):
    print(json.dumps({'running':command[0], 'operation':command[1] if len(command)>1 else ''}), flush=True)
    subprocess.run(command, cwd=project, check=True)


def create(project):
    if project.exists() and any(project.iterdir()):
        raise ValueError('样例只写入新空目录；不会覆盖现有作品')
    project.mkdir(parents=True, exist_ok=True)
    for name in ('src','scripts','tests','preproduction','index.html','score.json','asset_manifest.json','package.json','package-lock.json','tsconfig.json','README.md'):
        source=TEMPLATE/name
        if source.is_dir():
            shutil.copytree(source,project/name,ignore=shutil.ignore_patterns('node_modules','dist','__pycache__'))
        elif source.is_file():
            shutil.copy2(source,project/name)
    shutil.copy2(TEMPLATE/'examples/style_lab/main.ts',project/'src/main.ts')
    shutil.copy2(TEMPLATE/'examples/style_lab/score.json',project/'score.json')
    shutil.copy2(TEMPLATE/'examples/style_lab/TREATMENT.md',project/'TREATMENT.md')
    save(project/'asset_manifest.json',{'schema':'medical_animation_assets/v1','assets':[],'shots':[]})
    # Existing tests exercise the basic template; the lab still carries a neutral brand file.
    save(project/'brand.json',{'enabled':False,'text':'','ink':'#304c49','accent':'#b97153','paper':'#f3e7cc'})
    html=(project/'index.html').read_text().replace('纸剧场动作样本','MAC 媒介动作实验室')
    html=html.replace('<nav>', '<audio id="voice" src="audio/study.wav" preload="none"></audio><nav>')
    (project/'index.html').write_text(html)
    (project/'LAB.json').write_text(json.dumps({'kind':'mac-original-style-study','version':'1.0.0','medical_content':False,'renderer':'canvas2d','narration':None,'source':'bundled examples/style_lab','production_quality_approved':False},indent=2)+'\n')


def build(project):
    if not (project/'node_modules/.bin/tsc').is_file():
        run(['npm','ci','--ignore-scripts','--no-audit','--no-fund'],project)
    run(['npm','run','build'],project)


def audio(project):
    # Same score event resolution and mixer as production, with deliberate silence between accents.
    sys.path.insert(0,str(project/'scripts'))
    from mix_audio import foley
    out=project/'audio';out.mkdir(exist_ok=True)
    score=json.loads((project/'score.json').read_text())
    events=foley(project,score,out/'study.wav',48000)
    save(out/'study-receipt.json',{'score_sha256':hashlib.sha256((project/'score.json').read_bytes()).hexdigest(),
        'events':events,'narration':None,'music':None,'full_listening':'pending',
        'purpose':'procedural material accents; no TTS or author voice changed'})


def capture(project, command):
    score=json.loads((project/'score.json').read_text())
    output=project/'review' if command=='preview' else project/'out/style-study.mp4'
    if command=='render' and not (project/'audio/study.wav').is_file():audio(project)
    config={'project_root':str(project),'output':str(output),'entry':'index.html','width':1280,'height':720,
        'fps':score['fps'],'audio':str(project/'audio/study.wav')}
    config_path=project/f'{command}-config.json';save(config_path,config)
    runner='preview_local_animation.mjs' if command=='preview' else 'render_local_animation.mjs'
    result=subprocess.run(['node',str(BUNDLE/'scripts'/runner),str(config_path)],cwd=project,
        check=False,capture_output=True,text=True)
    print(result.stdout,end='',flush=True)
    if result.stderr:print(result.stderr,end='',file=sys.stderr)
    result.check_returncode()
    if command=='render':
        receipt=json.loads(result.stdout.strip().splitlines()[-1])
        receipt['video_sha256']=hashlib.sha256(output.read_bytes()).hexdigest()
        save(project/'out/render-receipt.json',receipt)
    if command=='preview':
        report=json.loads((output/'preview.json').read_text())
        cards=[]
        for i,beat in enumerate(score['shots'],1):
            candidates=[f for f in report['frames'] if f['scene']==i]
            frame=min(candidates,key=lambda f:abs(f['time']-(beat['start']+(beat['end']-beat['start'])*.75)))
            cards.append(f'<article><a href="index.html?shot={escape(beat["id"])}"><img src="review/{escape(frame["file"])}"><h2>{escape(beat["title"])}</h2></a><p>{escape(beat.get("styleId",beat["id"]))} · Canvas 2D</p><a href="review/strip-s{i}.jpg">动作 strip</a></article>')
        html='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>MAC 媒介动作实验室</title><style>body{margin:32px;background:#ece5d7;color:#304c49;font:16px system-ui}main{max-width:1280px;margin:auto}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:24px}article{background:#f8f3e8;padding:12px}img{width:100%}h2{font-size:20px}a{color:inherit}</style><main><h1>一粒种子，七种媒介</h1><p>独立原创技法研究。点击画面查看完整动作；它是可复用代码示例，不是医学成片或艺术批准。</p><p><a href="index.html">整片播放器</a> · <a href="out/style-study.mp4">52 秒 MP4</a> · <a href="TREATMENT.md">导演稿</a> · <a href="score.json">共用时间轴</a></p><div class="grid">'''+''.join(cards)+'</div></main></html>'
        (project/'gallery.html').write_text(html)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['list','create','build','audio','preview','render'])
    p.add_argument('--project',type=Path)
    p.add_argument('--complete',action='store_true',help='create 后构建、音效、预览和正式渲染')
    a=p.parse_args()
    if a.command=='list':
        print((STYLES/'index.json').read_text());return 0
    if a.project is None:p.error('需要 --project 绝对路径')
    project=a.project.resolve()
    try:
        if a.command=='create':
            create(project)
            if a.complete:
                build(project);audio(project);capture(project,'preview');capture(project,'render')
        elif not (project/'LAB.json').is_file():
            raise ValueError('只接受 animation_lab 创建的独立样例项目')
        elif a.command=='build':build(project)
        elif a.command=='audio':audio(project)
        else:capture(project,a.command)
        receipt={'status':'completed','completed_action':a.command,'project':str(project),'entry':str(project/'index.html'),
            'gallery':str(project/'gallery.html') if (project/'gallery.html').is_file() else None,
            'video':str(project/'out/style-study.mp4') if (project/'out/style-study.mp4').is_file() else None,
            'medical_content':False,'release_eligible':False}
        save(project/f'review/lab-result-{a.command}.json',receipt)
        print(json.dumps(receipt,ensure_ascii=False));return 0
    except (OSError,ValueError,subprocess.CalledProcessError) as exc:
        # Preserve consumable source / images on failure. Diagnostics are not style approval.
        diagnostic={'status':'incomplete','error':str(exc),'project':str(project),
            'quality_debt':[{'owner_stage':'media-production','blocks_stage_progress':False}],
            'next_action':'修复本机依赖或样例构建，再从失败动作继续；不要重建目录'}
        if (project/'LAB.json').is_file():save(project/f'review/lab-diagnostic-{a.command}.json',diagnostic)
        print(json.dumps(diagnostic,ensure_ascii=False));return 1

if __name__=='__main__':raise SystemExit(main())
