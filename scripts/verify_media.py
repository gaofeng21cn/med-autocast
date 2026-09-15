#!/usr/bin/env python3
"""Isolated four-second integration: original compositor -> native review package.

No model calls, production workspace writes, player or audio playback.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

import yaml

REPO = Path(__file__).resolve().parents[1]
TOOL = REPO/'runtime/native_helpers/workbench_tool.py'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--font',type=Path,required=True)
    a=p.parse_args();root=a.output.resolve()
    if root.exists():raise SystemExit('Output must be a new isolated directory')
    for binary in ('ffmpeg','ffprobe','magick'):
        if not shutil.which(binary):raise SystemExit(f'Missing {binary}')
    root.mkdir(parents=True)
    env=dict(os.environ, PYTHONDONTWRITEBYTECODE='1')
    def run(cmd):
        result=subprocess.run(cmd,cwd=root,env=env,capture_output=True,text=True)
        if result.returncode:
            raise RuntimeError(result.stderr[-4000:] or result.stdout[-4000:])
        return result.stdout
    def dump(rel,obj):
        path=root/rel;path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(yaml.safe_dump(obj,allow_unicode=True) if path.suffix=='.yaml' else json.dumps(obj,ensure_ascii=False,indent=2))
        return path
    def tool(name,*args):
        return run([sys.executable,'-B',str(TOOL),'--workspace',str(root),'--name',name,'--bundled','--',*map(str,args)])
    ep=root/'productions/s/01_smoke';candidates=ep/'candidates';candidates.mkdir(parents=True)
    voice=ep/'audio.wav';bgm=ep/'bgm.wav';source=candidates/'scene.mp4'
    run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=size=608x352:rate=24','-t','4','-c:v','libx264','-pix_fmt','yuv420p',str(source)])
    for frequency,dest in [(440,voice),(220,bgm)]:
        run(['ffmpeg','-v','error','-f','lavfi','-i',f'sine=frequency={frequency}:sample_rate=24000','-t','4','-c:a','pcm_s16le',str(dest)])
    srt=ep/'text.srt';srt.write_text('1\n00:00:00,000 --> 00:00:02,000\n字幕与画面\n\n2\n00:00:02,000 --> 00:00:04,000\n品牌与混音\n')
    author=dump('profiles/author.yaml',{'schema':'medical_video_author_profile/v1','profile_id':'smoke',
        'display_name':'Test Author','voice':{},'visual_identity':{'enabled':False},
        'brand':{'overlay_text':'TEST AUTHOR','avatar_usage':'disabled'},
        'audio_mix':{'background_music':str(bgm),'target_relative_level_db':[-24,-18],'fade_in_seconds':.2,'fade_out_seconds':.3}})
    dump('workbench.yaml',{'schema':'medical_video_workbench/v2','active_profiles':{'author':'profiles/author.yaml'},
        'series':{'s':{'content_root':'content/s','production_root':'productions/s','publish_root':'publish/s','release_catalog':'content/catalog.yaml'}}})
    catalog={'series_id':'s','episodes':[{'id':'01_smoke','title':'隔离技术验证',
        'xiaohongshu_title':'测试','xiaohongshu_copy':'不含医学判断','xiaohongshu_tags':['测试'],
        'channels_title':'测试','channels_copy':'不含医学判断','channels_tags':['测试'],'pinned_comment':'仅用于验证'}]}
    dump('content/catalog.yaml',catalog)
    plan_data={'schema':'video_production_plan/v3','episode_id':'01_smoke','version':'smoke',
        'delivery':{'author_profile':'smoke'},'format':{'width':608,'height':352,'fps':24},
        'audio':{'source':'audio.wav','duration_seconds':4},'subtitles':{'source':'text.srt','cue_offsets':{'2':'+0+32'}},
        'visual_timeline':[{'segment_id':'V01','start':0,'end':4,'source':str(source),'source_start':0,'source_end':4,'shot_type':'deterministic_animation','topic_relation':'synthetic integration fixture'}]}
    plan=dump('productions/s/01_smoke/review/production_plan.yaml',plan_data)
    master=ep/'review/video.mp4';build=ep/'qa/build'
    tool('build_episode_video','--candidates',candidates,'--audio',voice,'--srt',srt,'--font',a.font.resolve(),
         '--plan',plan,'--output',master,'--work-dir',build,'--author-profile',author,'--no-avatar')
    run(['ffmpeg','-v','error','-i',str(master),'-f','null','-'])
    probe=json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(master)]))
    video=next(s for s in probe['streams'] if s['codec_type']=='video')
    audio=next(s for s in probe['streams'] if s['codec_type']=='audio')
    assert (video['width'],video['height'])==(608,352)
    assert video['codec_name']=='h264' and audio['codec_name']=='aac'
    build_record=json.loads((build/'build-manifest.json').read_text())
    assert build_record['brand_text']=='TEST AUTHOR' and build_record['bgm']==str(bgm)
    assert build_record['subtitle_cue_offsets']=={'2':'+0+32'}
    assert len(build_record['normalized_subtitle_cues'])==2
    review=dump('productions/s/01_smoke/review/review.json',{'episode':'01_smoke','revision':'smoke',
        'production_plan':str(plan),'video_source':str(master),'audio_source':str(voice),'srt_source':str(srt),
        'segments':plan_data['visual_timeline'],'technical_qa':'passed','full_motion_review':'pending','full_listening':'pending','medical_review':'pending'})
    qa=dump('productions/s/01_smoke/qa/technical.json',{'status':'decoded','video':str(master),'probe':probe})
    result=json.loads(tool('package_review','--series','s','--episode','01_smoke','--plan',plan,'--master',master,'--review',review,'--technical-qa',qa))
    assert result['status']=='packaged_and_read_back' and result['video_bytes_equal'] and result['platform_copy_equal']
    assert result['review_claims']['medical_review']=='pending' and not result['uploaded']
    # A repeated revision keeps the former real delivery and the series manifest recoverable.
    again=json.loads(tool('package_review','--series','s','--episode','01_smoke','--plan',plan,'--master',master,'--review',review,'--technical-qa',qa))
    assert Path(again['previous_delivery']).is_dir()
    summary={'status':'passed','synthetic_fixture':True,'duration_seconds':float(probe['format']['duration']),
        'resolution':[608,352],'video_codec':video['codec_name'],'audio_codec':audio['codec_name'],
        'full_decode':True,'subtitle_cues':2,'brand_and_bgm_readback':True,
        'review_package_bytes_equal':True,'dual_platform_copy_equal':True,'previous_delivery_preserved':True,
        'model_calls':0,'production_workspace_writes':False,'medical_approval':False}
    (root/'result.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
