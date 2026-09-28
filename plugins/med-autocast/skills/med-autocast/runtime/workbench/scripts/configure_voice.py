#!/usr/bin/env python3
"""显式选择作者声音模式，保留已登记参考音频与审核记录。"""
import argparse
import json
import os
from pathlib import Path
import tempfile
import yaml
from workbench_config import ROOT, load_author_profile, load_backend_profile, select_audio_backend


def configure(root: Path, mode: str, series: str | None = None) -> dict:
    path, author = load_author_profile(root=root, series_id=series)
    _, backends = load_backend_profile(root=root)
    voice = author.setdefault('voice', {})
    if mode == 'reference' and not voice.get('reference_audio'):
        raise ValueError('先登记授权 voice.reference_audio；也可选择 edge 跳过专用声线')
    if mode == 'reference' and voice.get('preferred_backend_definition') in (None, 'edge_tts'):
        voice['preferred_backend_definition'] = 'indextts_2_5'
    voice['mode'] = mode
    selected = select_audio_backend(author, backends)
    if mode == 'reference':
        reference = (root / voice['reference_audio']).expanduser()
        if not reference.is_file():
            raise ValueError(f'参考音频不存在：{reference}')
    # A changed voice selection invalidates voice approval, not the saved reference.
    author.setdefault('baseline', {}).setdefault('review', {})['voice'] = 'pending'
    fd, temporary = tempfile.mkstemp(prefix='.voice-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            yaml.safe_dump(author, stream, allow_unicode=True, sort_keys=False)
        os.replace(temporary, path)
    finally:
        if Path(temporary).exists(): Path(temporary).unlink()
    return {'status':'configured', 'author_profile':str(path), 'voice_mode':mode,
            'selected_backend':selected, 'reference_preserved':bool(voice.get('reference_audio')),
            'voice_review':'pending', 'network_required':mode=='edge'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace',type=Path,default=ROOT)
    parser.add_argument('--series')
    parser.add_argument('--mode',choices=['reference','edge'],required=True)
    args=parser.parse_args()
    try: print(json.dumps(configure(args.workspace.resolve(),args.mode,args.series),ensure_ascii=False))
    except (OSError,ValueError) as exc: parser.exit(1,str(exc)+'\n')


if __name__=='__main__': main()
