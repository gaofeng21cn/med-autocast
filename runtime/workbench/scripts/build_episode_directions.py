#!/usr/bin/env python3
"""Write one episode director file from its own story and its own code.

Two series-wide mistakes are corrected here. The old director file was a
205-scene copy of the whole series, identical in every episode, so the director
never actually wrote anything; and the staging was a series factory. This
script does not invent staging: it reads the room each shot actually paints in
episodeshots.ts and pairs it with the beat this shot performs, taken from the
episode story. The result is per-episode, traceable to code and story, and
cannot be a copy of another episode unless the code and story are copies too.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def scene_of(shot_id: str) -> str:
    return shot_id.split('_', 1)[1] if '_' in shot_id else shot_id


def rooms_in_order(source: str):
    rooms = []
    for line in source.splitlines():
        if 'paperRoom(s,' in line:
            rooms.append(line.split(chr(39))[1])
    return rooms


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', type=Path, default=Path.cwd())
    ap.add_argument('--project', required=True)
    ap.add_argument('--story', required=True)
    ap.add_argument('--series', required=True)
    ap.add_argument('--episode', required=True)
    args = ap.parse_args()

    ws = args.workspace.resolve()
    project = (ws / args.project).resolve()
    shots_file = project / 'src/episodeshots.ts'
    score_file = project / 'score.json'
    if not shots_file.is_file():
        print(json.dumps({'status': 'missing_episodeshots', 'project': str(project)}, ensure_ascii=False))
        return 1
    rooms = rooms_in_order(shots_file.read_text())
    score = json.loads(score_file.read_text())
    story = yaml.safe_load(Path(args.story).read_text()) or {}
    beats = {}
    title = ''
    task = ''
    for ep in story.get('episodes') or []:
        if ep.get('id') == args.episode:
            for b in ep.get('beats') or []:
                beats[b['scene']] = b
            task = ep.get('patient_task', '')
            title = ep.get('title', '')
            break
    else:
        print(json.dumps({'status': 'episode_not_in_story', 'episode': args.episode}, ensure_ascii=False))
        return 1

    scenes = {}
    for i, shot in enumerate(score['shots']):
        name = scene_of(shot['id'])
        beat = beats.get(name, {})
        room = rooms[i] if i < len(rooms) else (rooms[-1] if rooms else 'consult')
        scenes[name] = {
            'space': room + ' 纸景房间（kit/rooms.ts paperRoom）',
            'text': beat.get('text', ''),
            'facts': beat.get('facts', []),
            'intent': beat.get('directing', ''),
            'events': shot.get('events', {}),
            'duration': round(float(shot['end']) - float(shot['start']), 2),
        }
    out = {
        'schema': 'episode_direction/v2',
        'series_id': args.series,
        'episode_id': args.episode,
        'title': title,
        'patient_task': task,
        'staging': 'src/episodeshots.ts（本集独立导演实现）',
        'scenes': scenes,
    }
    target = project / 'src/scene_directions.json'
    target.write_text(json.dumps(out, ensure_ascii=False, indent=2) + chr(10), encoding='utf-8')
    print(json.dumps({'status': 'written', 'path': str(target), 'scenes': len(scenes)}, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
