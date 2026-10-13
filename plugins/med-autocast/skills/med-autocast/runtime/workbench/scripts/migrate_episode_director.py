#!/usr/bin/env python3
"""Wire one episode onto its own director and verify the wiring.

Per-episode independence is the rule, so the mechanical part is scripted once and
reused for every episode: install the current kit (paper rooms, paper tableware,
paper plates), point main.ts at this episode director instead of a series
factory, regenerate the director file from the episode own story plus the rooms
the code actually paints, and delete factory files that nothing imports any
more. The director itself is written by a human or a model; this script never
authors shots.
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

# Asset use can be direct (`s.image('id')`) or through the paper vocabulary
# helper (`img(s, 'id', ...)`). Both resolve at runtime against this episode's
# manifest, so both are checked here.
ASSET_USE_RES = [
    re.compile(r"\.image\('([^']+)'"),
    re.compile(r"\bimg\(s,\s*'([^']+)'"),
]
KIT_FILES = ['rooms.ts', 'tableware.ts', 'staging.ts', 'patterns.ts']
FACTORY_FILES = ['six_shots.ts', 'hypertension_shots.ts', 'story_shots.ts',
                 'living_shots.ts', 'lipid_shots.ts', 'episode-director.ts']


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument('--workspace', type=Path, default=Path.cwd())
    ap.add_argument('--project', required=True)
    ap.add_argument('--story', default='')
    ap.add_argument('--series', default='')
    ap.add_argument('--episode', default='')
    ap.add_argument('--no-build', action='store_true')
    args = ap.parse_args()

    ws = args.workspace.resolve()
    project = (ws / args.project).resolve()
    src = project / 'src'
    director = src / 'episodeshots.ts'
    problems = []

    if not director.is_file():
        print(json.dumps({'status': 'missing_director', 'expected': str(director)}, ensure_ascii=False))
        return 2

    template_kit = ws / 'templates/animation/paper_theatre/src/kit'
    kit = src / 'kit'
    kit.mkdir(parents=True, exist_ok=True)
    for name in KIT_FILES:
        source = template_kit / name
        if source.is_file():
            shutil.copy2(source, kit / name)

    main_file = src / 'main.ts'
    s = main_file.read_text()
    # Old factories are named differently across series (six_shots, story_shots,
    # field-director, lipid_shots...). Any local import that binds `shots` or
    # `makeShot` and does not come from ./episodeshots is a factory binding, so
    # drop it by shape instead of by file name.
    def _drop_factory_import(match):
        names, module = match.group(1), match.group(2)
        if module == './episodeshots':
            return match.group(0)
        if re.search(r'\b(shots|makeShot|makeShots)\b', names):
            return ''
        return match.group(0)

    s = re.sub(r"import \{([^}]*)\} from '(\./[A-Za-z0-9_./-]+)';" + chr(10),
               _drop_factory_import, s)
    if "./episodeshots" not in s:
        s = s.replace("import {mount}", "// This episode owns its staging; the series factory is gone." + chr(10) + "import {shots} from './episodeshots';" + chr(10) + "import {mount}", 1)
    s = re.sub(r'mount\(\{assets:.*?\}\);',
               'mount({assets:manifest.assets as unknown as Asset[],score:score as unknown as Score,brand,shots});',
               s, flags=re.S)
    main_file.write_text(s)

    removed = []
    if 'six_shots' not in s and 'story_shots' not in s and 'hypertension_shots' not in s:
        for name in FACTORY_FILES:
            f = src / name
            if f.is_file():
                importers = [g.name for g in src.glob('*.ts')
                             if g.name != name and (name[:-3] in g.read_text())]
                if not importers:
                    f.unlink()
                    removed.append(name)

    direction = {}
    if args.story and args.series and args.episode:
        proc = subprocess.run([sys.executable, str(ws / 'scripts/build_episode_directions.py'),
                               '--workspace', str(ws), '--project', str(project),
                               '--story', str(ws / args.story), '--series', args.series,
                               '--episode', args.episode],
                              capture_output=True, text=True)
        if proc.returncode == 0:
            direction = json.loads(proc.stdout.strip().splitlines()[-1])
        else:
            problems.append('direction_failed: ' + (proc.stderr.strip() or proc.stdout.strip())[-200:])

    # A duplicated append leaves two closing braces in a row. The director is
    # otherwise valid, so drop the repeat instead of failing the build on it.
    raw = director.read_text().splitlines()
    cleaned = []
    for ln in raw:
        if ln.strip() == '};' and cleaned and cleaned[-1].strip() == '};':
            continue
        cleaned.append(ln)
    if cleaned != raw:
        director.write_text(chr(10).join(cleaned) + chr(10))

    # A duplicated append leaves two closing braces in a row. The director is
    # otherwise valid, so drop the repeat instead of failing the build on it.
    raw = director.read_text().splitlines()
    cleaned = []
    for ln in raw:
        if ln.strip() == '};' and cleaned and cleaned[-1].strip() == '};':
            continue
        cleaned.append(ln)
    if cleaned != raw:
        director.write_text(chr(10).join(cleaned) + chr(10))

    # Old factories come in clusters, and two leftovers often import each other,
    # so "is anything referencing this file" never reaches them. Walk the import
    # graph from the real entry points instead and delete everything unreachable.
    roots = {"main.ts", "episodeshots.ts", "paper_objects.ts", "six_objects.ts",
             "episode-kit.ts", "meal_objects.ts", "series_grammar.ts"}
    files = [f for f in src.glob("*.ts") if f.is_file()]
    texts = {}
    for f in files:
        try:
            texts[f] = f.read_text()
        except OSError:
            texts[f] = ""
    reachable = set()
    queue = [f for f in files if f.name in roots]
    while queue:
        cur = queue.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        for target in re.findall(r"from '(\./[A-Za-z0-9_./-]+)'", texts[cur]):
            name = target.rsplit('/', 1)[-1] + '.ts'
            for f in files:
                if f.name == name and f not in reachable:
                    queue.append(f)
    for f in files:
        if f not in reachable:
            f.unlink()
            removed.append(f.name)

    # A director whose shot ids do not match score.json renders nothing, and the
    # failure surfaces only as a generic render error. Check it here instead.
    import json as _json
    score_path = project / 'score.json'
    if score_path.is_file():
        score_ids = [sh['id'] for sh in _json.loads(score_path.read_text())['shots']]
        mine = re.findall(r"id: '([^']+)'", director.read_text())
        if mine != score_ids:
            problems.append('shot ids differ: ' + str(mine) + ' vs ' + str(score_ids))

    # Referring to an asset this episode does not own fails at render time with
    # a generic playwright message. Compare the manifest while the intent is fresh.
    manifest = project / 'asset_manifest.json'
    if manifest.is_file():
        data = _json.loads(manifest.read_text())
        owned = set(a['asset_id'] for a in data['assets'])
        text = director.read_text()
        used = set()
        for pattern in ASSET_USE_RES:
            used.update(pattern.findall(text))
        missing = sorted(used - owned)
        if missing:
            problems.append('assets not in this episode manifest: ' + str(missing))


    built = None
    if not args.no_build:
        proc = subprocess.run(['npm', 'run', 'build'], cwd=project, capture_output=True, text=True)
        built = proc.returncode == 0
        if not built:
            problems.append('build_failed: ' + (proc.stdout + proc.stderr)[-500:])

    print(json.dumps({'status': 'wired' if not problems else 'wired_with_problems',
                      'project': str(project), 'factories_removed': removed,
                      'direction': direction, 'build_ok': built, 'problems': problems},
                     ensure_ascii=False, indent=2))
    return 0 if not problems else 1


if __name__ == '__main__':
    raise SystemExit(main())
