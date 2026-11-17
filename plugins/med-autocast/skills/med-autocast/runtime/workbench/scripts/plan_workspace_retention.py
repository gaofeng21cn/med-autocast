#!/usr/bin/env python3
"""Necessity-first lifecycle plan, verified pruning, and selective lossless retention.

No project/asset/publish directory is ever a deletion candidate. Plans contain
exact leaf files and preserved substitutes. Apply validates the whole selection
before its first mutation and refuses changed inputs or active media writers.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import subprocess
import shutil
import time
from collections import Counter, defaultdict
from pathlib import Path
import yaml

SCHEMA = 'medical_video_retention_plan/v2'
MEDIA = {'.png', '.webp', '.wav', '.flac', '.mp4', '.jpg', '.jpeg'}
FRAME = re.compile(r'^(?:clean-\d+-s\d+-|event-|strip-s\d+-\d+|\d+-s\d+-).*\.(?:png|webp)$')
NUMBERED = re.compile(r'^\d+-s\d+-.+\.(?:png|webp)$')
STRIP_SOURCE = re.compile(r'^strip-s\d+-\d+\.(?:png|webp)$')
EVENT_SIDE = re.compile(r'^event-.+-(?:before|after)\.(?:png|webp)$')
PATH_TOKEN = re.compile(r'[^\s\"\'`<>\[\](){};,，：]+\.(?:png|webp|wav|flac)')
DERIVED_AUDIO = {'foley', 'music-raw', 'music-prepared', 'music-ducked', 'premix'}
SKIP = {'.git', 'node_modules', '__pycache__', '.venv'}


def stamp():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def leaves(root):
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = [n for n in names if n not in SKIP and not (Path(directory) / n).is_symlink()]
        for name in files:
            path = Path(directory) / name
            if not path.is_symlink():
                yield path


def record(path, workspace, **fields):
    stat = path.stat()
    return dict(path=str(path), relative_path=str(path.relative_to(workspace)),
                size=stat.st_size, allocated_bytes=stat.st_blocks * 512,
                mtime_ns=stat.st_mtime_ns, sha256=sha(path), **fields)


def confined(path, workspace):
    if not path.is_relative_to(workspace) or path == workspace:
        raise ValueError(f'Path outside workspace: {path}')
    relative = path.relative_to(workspace)
    current = workspace
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ValueError(f'Symlink in action path: {current}')
    return path


def project_for(path, workspace):
    relative = path.relative_to(workspace).parts
    if len(relative) >= 4 and relative[0] == 'productions':
        candidate = workspace.joinpath(*relative[:4])
        if (candidate / 'project.json').is_file():
            return candidate
    return None


def active_projects(workspace, policy):
    config = yaml.safe_load((workspace / 'workbench.yaml').read_text()) or {}
    active = set()
    for series in (config.get('series') or {}).values():
        for episode in (series.get('episodes') or {}).values():
            path = episode.get('project')
            if path:
                active.add((workspace / path).resolve())
    wip = {(workspace / p).resolve() for p in policy.get('protected_projects', [])}
    return active, wip


def semantic_document(path):
    if path.suffix.lower() not in {'.md', '.json', '.yaml', '.yml', '.txt'}:
        return False
    # Inventories and producer receipts enumerate their own inputs. They are
    # provenance, not requests to retain every enumerated cache forever.
    if path.name in {'preview.json', 'storage-compaction.json', 'lifecycle-receipt.json', 'snapshot.json',
                     'project.json', 'revision.json', 'mix-receipt.json',
                     'timing-receipt.json', 'narration_beats.json',
                     'contact-frames.ffconcat', 'motion-audit.json'}:
        return False
    if path.suffix == '.json':
        if any(word in path.name.lower() for word in ('prune', 'cleanup', 'retention', 'compaction', 'inventory', 'checkpoint', 'queue', 'build-receipt')):
            return False
        if path.name.endswith(('.receipt.json', '.motion-audit.json')):
            return False
    if any(part.startswith(('disk-lifecycle-', 'disk-cleanup-')) for part in path.parts):
        return False
    return True


def references(files, candidates, workspace):
    aliases = defaultdict(set)
    for path in candidates:
        aliases[path.name].add(path)
        if path.suffix in {'.png', '.webp'}:
            aliases[path.with_suffix('.webp' if path.suffix == '.png' else '.png').name].add(path)
    refs = defaultdict(set)
    for doc in files:
        if not semantic_document(doc):
            continue
        try:
            text = doc.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            continue
        doc_project = project_for(doc, workspace)
        for token in set(PATH_TOKEN.findall(text)):
            token = token.rstrip('.:')
            name = Path(token).name
            possible = aliases.get(name, set())
            if not possible:
                continue
            resolved = set()
            for parent in (workspace, doc.parent, *(doc.parent.parents)):
                if not parent.is_relative_to(workspace):
                    continue
                p = Path(os.path.abspath(parent / token))
                for variant in (p, p.with_suffix('.png'), p.with_suffix('.webp')):
                    if variant in possible:
                        resolved.add(variant)
            if not resolved and '/' not in token:
                resolved = {p for p in possible if doc_project and project_for(p, workspace) == doc_project}
                # Bare names in a work report are scoped by a full project or
                # preview directory explicitly present in the same document.
                if not resolved:
                    resolved = {p for p in possible if str(p.parent) in text or str(p.parent.relative_to(workspace)) in text}
            for p in resolved:
                refs[p].add(str(doc.relative_to(workspace)))
    return refs


def preview_evidence(directory, report, workspace):
    contact = directory / Path(report.get('contact_sheet') or 'contact.jpg').name
    strips = [directory / s['sheet'] for s in report.get('motionStrips', []) if s.get('sheet')]
    available = contact.is_file() and bool(strips) and all(p.is_file() for p in strips)
    return dict(valid=available,
                substitutes=[record(p, workspace) for p in [contact, *strips] if p.is_file()],
                exact_rebuild=False)


def plan(workspace, policy):
    files = list(leaves(workspace))
    active, wip = active_projects(workspace, policy)
    frame_paths = {p for p in files if FRAME.fullmatch(p.name) and
                   ('qa' in p.relative_to(workspace).parts or p.relative_to(workspace).parts[0] in {'work', 'qa', 'out'})}
    audio_paths = {p for p in files if p.suffix.lower() in {'.wav', '.flac'} and
                   p.relative_to(workspace).parts[0] == 'productions'}
    render_paths = {p for p in files if any(x.startswith('.render-') for x in p.relative_to(workspace).parts)
                    and p.relative_to(workspace).parts[0] == 'productions'}
    refs = references(files, frame_paths | audio_paths | render_paths, workspace)
    decisions, groups = [], []
    handled = set()
    for preview in sorted(p for p in files if p.name == 'preview.json'):
        directory = preview.parent
        try:
            data = read(preview)
        except (OSError, ValueError):
            continue
        project = project_for(preview, workspace)
        report_project = Path(data.get('project') or '')
        if project is None and report_project.is_absolute() and report_project.is_relative_to(workspace):
            project = report_project
        evidence = preview_evidence(directory, data, workspace)
        frozen = False
        inputs = (data.get('runtime_receipt') or {}).get('inputs', {})
        if evidence['valid'] and inputs.get('score') and inputs.get('bundle'):
            frozen = all(Path(inputs[key].get('path', '')).is_file() and
                         sha(Path(inputs[key]['path'])) == inputs[key].get('sha256')
                         for key in ('score', 'bundle'))
        evidence['source_inputs_match'] = frozen
        evidence['rebuild_scope'] = 'seekable_source_replay_not_historical_png_bytes'
        evidence['source_inputs'] = [record(Path(inputs[key]['path']), workspace) for key in ('score','bundle')
                                     if frozen and Path(inputs[key]['path']).is_relative_to(workspace)]
        actions = []
        for path in sorted(p for p in directory.iterdir() if p in frame_paths):
            handled.add(path)
            cited = sorted(refs.get(path, []))
            if cited:
                action, reason = 'keep_operational', 'explicit_issue_reference_exact_container'
            elif project in wip:
                action, reason = 'keep_operational', 'active_independent_repair_evidence'
            elif not evidence['valid']:
                action, reason = 'keep_compressed', 'summary_incomplete_unique_evidence'
            elif STRIP_SOURCE.fullmatch(path.name):
                action, reason = 'delete_redundant', 'motion_strip_sheet_preserved'
            elif NUMBERED.fullmatch(path.name):
                action, reason = 'delete_redundant', 'contact_and_event_evidence_preserved'
            elif frozen:
                action, reason = 'delete_rebuildable', 'frozen_score_bundle_contact_and_strips_preserved'
            elif EVENT_SIDE.fullmatch(path.name):
                at = re.sub(r'-(?:before|after)\.(png|webp)$', r'-at.\1', path.name)
                if (directory / at).is_file():
                    action, reason = 'delete_redundant', 'historical_event_center_preserved_no_exact_rebuild_claim'
                else:
                    action, reason = 'keep_compressed', 'event_center_missing'
            elif path.name.startswith('clean-'):
                midpoint_files = {'clean-' + f['file'] for f in data.get('frames', [])
                                  if abs(float((f.get('state') or {}).get('progress', -1)) - .5) < .001}
                # Older reports expose local time, but the frame sequence is
                # six samples per scene and sample 3 is the midpoint.
                midpoint_files |= {'clean-' + f['file'] for i,f in enumerate(data.get('frames', [])) if i % 6 == 3}
                if path.name in midpoint_files:
                    action, reason = 'keep_compressed', 'historical_text_free_scene_anchor'
                else:
                    action, reason = 'delete_redundant', 'historical_scene_midpoint_and_contact_preserved'
            else:
                action, reason = 'keep_compressed', 'clean_or_event_anchor_for_review'
            row = record(path, workspace, category='review_frame', decision=action, reason=reason,
                         preview=str(preview), project=str(project) if project else None,
                         references=cited)
            if action == 'keep_compressed' and path.suffix == '.png':
                row['target'] = str(path.with_suffix('.webp'))
            decisions.append(row); actions.append(row)
        if actions:
            groups.append(dict(directory=str(directory), preview=record(preview, workspace),
                               project=str(project) if project else None, evidence=evidence,
                               files=len(actions)))
    for path in sorted(frame_paths - handled):
        decisions.append(record(path, workspace, category='unbound_review_frame',
                         decision='defer_review', reason='no_preview_binding'))
    # Only a validated final mix and available recipe inputs admit intermediate deletion.
    recipes = {}
    for receipt in (p for p in files if p.name == 'mix-receipt.json' and 'mix-history' not in p.parts):
        project = project_for(receipt, workspace)
        if project is None:
            continue
        try:
            data = read(receipt); config = read(project / 'project.json')
            final = project / config.get('audio', 'audio.wav')
            voice = Path(data.get('voice_source') or project / config.get('voice', 'audio/narration-normalized.wav'))
            if not voice.is_absolute(): voice = project / voice
            tracks = data.get('music_tracks') or []
            valid = final.is_file() and data.get('audio_sha256') == sha(final) and voice.is_file()
            if data.get('voice_sha256'): valid &= sha(voice) == data['voice_sha256']
            for track in tracks:
                source = Path(track.get('resolved_path') or track.get('path') or '')
                if not source.is_absolute(): source = project / source
                valid &= source.is_file()
                if source.is_file() and track.get('sha256'): valid &= sha(source) == track['sha256']
            if valid: recipes[project] = (receipt, final)
        except (ValueError, OSError, TypeError):
            pass
    for path in sorted(audio_paths):
        project = project_for(path, workspace)
        if project is None:
            continue
        cited = sorted(refs.get(path, []))
        if path.stem in DERIVED_AUDIO and path.parent == project / 'audio' and project in recipes and not cited:
            action, reason = 'delete_rebuildable', 'final_mix_and_recipe_sources_verified'
        elif path.suffix == '.flac':
            action, reason = 'keep_compressed', 'lossless_historical_or_source_audio'
        elif project in active or project in wip or cited:
            action, reason = 'keep_operational', 'active_audio_input_or_explicit_reference'
        else:
            action, reason = 'keep_compressed', 'frozen_revision_source_or_mix_for_restoration'
        row = record(path, workspace, category='audio', decision=action, reason=reason,
                     project=str(project), references=cited)
        if action == 'keep_compressed' and path.suffix == '.wav': row['target'] = str(path.with_suffix('.flac'))
        if project in recipes and action.startswith('delete'):
            row['substitutes'] = [record(p, workspace) for p in recipes[project]]
        decisions.append(row)
    for path in sorted(render_paths):
        decisions.append(record(path, workspace, category='render_temporary',
                         decision='keep_operational' if refs.get(path) else 'delete_rebuildable',
                         reason='explicit_reference' if refs.get(path) else 'renderer_scratch_not_a_source',
                         references=sorted(refs.get(path, []))))
    totals = defaultdict(lambda: {'files': 0, 'allocated_bytes': 0})
    for row in decisions:
        key = f"{row['category']}:{row['decision']}"
        totals[key]['files'] += 1; totals[key]['allocated_bytes'] += row['allocated_bytes']
    inventory = defaultdict(lambda: {'files': 0, 'size': 0, 'allocated_bytes': 0})
    for p in files:
        try:
            s=p.stat(); key=p.relative_to(workspace).parts[0]
            inventory[key]['files']+=1;inventory[key]['size']+=s.st_size;inventory[key]['allocated_bytes']+=s.st_blocks*512
        except OSError: pass
    return dict(schema=SCHEMA, created_at=stamp(), workspace=str(workspace), status='planned',
                policy=policy, protected_projects=sorted(map(str, active | wip)),
                groups=groups, decisions=decisions, summary=dict(totals), inventory=dict(inventory),
                disk_free_bytes=os.statvfs(workspace).f_bavail * os.statvfs(workspace).f_frsize)


def assert_idle(workspace):
    process = subprocess.run(['ps','-axo','pid=,command='],capture_output=True,text=True,check=True)
    for line in process.stdout.splitlines():
        if str(workspace) not in line or int(line.split(None,1)[0]) == os.getpid():
            continue
        if any(token in line for token in ('preview_local_animation.mjs', 'render_local_animation.mjs',
                                         'render_javascript_animation.py','ffmpeg ', 'render_narration.py')):
            raise RuntimeError(f'Active media writer: {line[:240]}')


def apply(plan_path, output, *, parts):
    data = read(plan_path)
    if data.get('schema') != SCHEMA: raise ValueError('Expected necessity-first v2 plan')
    workspace = Path(data['workspace']).resolve()
    selected = [r for r in data['decisions'] if r['category'] in parts and
                (r['decision'].startswith('delete') or r.get('target'))]
    assert_idle(workspace)
    if any(r.get("target", "").endswith(".webp") for r in selected) and not shutil.which("cwebp"):
        raise RuntimeError("Missing cwebp; no files changed")
    if any(r.get("target", "").endswith(".flac") for r in selected) and not shutil.which("flac"):
        raise RuntimeError("Missing flac; no files changed")
    # Prevalidate every selected file and every preserved substitute. A stale
    # plan never partially deletes an earlier entry before discovering an error.
    group_map = {g['preview']['path']:g for g in data['groups']}
    protected_evidence = {}
    for row in selected:
        path=confined(Path(row['path']),workspace)
        if row.get('target'): confined(Path(row['target']),workspace)
        if row['category'] == 'review_frame' and (not FRAME.fullmatch(path.name) or str(path.parent/'preview.json') != row.get('preview')):
            raise ValueError(f'Invalid review leaf: {path}')
        if row['category'] == 'render_temporary' and not any(p.startswith('.render-') for p in path.relative_to(workspace).parts):
            raise ValueError(f'Invalid renderer scratch leaf: {path}')
        if row['category'] == 'audio' and (path.suffix not in {'.wav','.flac'} or path.relative_to(workspace).parts[0] != 'productions'):
            raise ValueError(f'Invalid audio leaf: {path}')
        if row['category'] == 'audio' and row['decision'].startswith('delete'):
            project=project_for(path,workspace)
            if project is None or path.parent != project/'audio' or path.stem not in DERIVED_AUDIO:
                raise ValueError(f'Audio source cannot be deleted: {path}')
        if path.exists() and sha(path)!=row['sha256']: raise RuntimeError(f'Changed candidate: {path}')
        if row.get('preview'):
            group=group_map[row['preview']]
            if row['decision'].startswith('delete') and not group['evidence']['valid']:
                raise ValueError('Missing preserved evidence')
            for item in [group['preview'],*group['evidence']['substitutes'],*group['evidence'].get('source_inputs',[])]: protected_evidence[item['path']]=item
        for item in row.get('substitutes',[]): protected_evidence[item['path']]=item
    for item in protected_evidence.values():
        path=confined(Path(item['path']),workspace)
        if not path.is_file() or sha(path)!=item['sha256']: raise RuntimeError(f'Changed substitute: {path}')
    output.parent.mkdir(parents=True,exist_ok=True)
    journal=output.with_suffix('.jsonl')
    records=[]; group_actions=defaultdict(list)
    from compact_workspace_media import convert_png, convert_wav
    def emit(row, conversion=None):
        source=Path(row['path'])
        if conversion is None:
            source.unlink(); result={**row,'action':'deleted'}
        else:
            comp=source.parent/'storage-compaction.json'
            previous=read(comp) if comp.exists() else {'schema':'medical_video_storage_compaction_group/v1','records':[]}
            previous['records']=[r for r in previous['records'] if r.get('source')!=str(source)]+[conversion]
            previous['necessity_policy']='retained_after_necessity_decision'
            write(comp,previous)
            source.unlink()
            result={**row,**conversion,'action':'lossless_compressed'}
        records.append(result)
        if row.get('preview'):group_actions[row['preview']].append(result)
        stream.write(json.dumps(result,ensure_ascii=False)+'\n');stream.flush()
        if len(records)%250==0:print(json.dumps({'processed':len(records),'total':len(selected)}),flush=True)

    def convert(row):
        source=Path(row['path'])
        converter=convert_png if source.suffix=='.png' else convert_wav
        return converter(dict(source=str(source),target=row['target'],
            kind='qa_png' if source.suffix=='.png' else 'audio_retained',
            allocated_bytes=row['allocated_bytes'],size=row['size'],mtime_ns=row['mtime_ns']))

    from concurrent.futures import ThreadPoolExecutor, as_completed
    with journal.open('a',encoding='utf-8') as stream:
        for index,row in enumerate(r for r in selected if r['decision'].startswith('delete')):
            source=Path(row['path'])
            if not source.exists():
                records.append(dict(path=str(source),action='already_absent'));continue
            if index%250==0:assert_idle(workspace)
            emit(row)
        compression=[r for r in selected if r.get('target') and Path(r['path']).exists()]
        with ThreadPoolExecutor(max_workers=8) as pool:
            for offset in range(0,len(compression),64):
                assert_idle(workspace)
                futures={pool.submit(convert,r):r for r in compression[offset:offset+64]}
                for future in as_completed(futures):emit(futures[future],future.result())
    # Update generated metadata without modifying independent review conclusions.
    for preview,actions in group_actions.items():
        pp=Path(preview); report=read(pp)
        mappings={Path(r['path']).name:Path(r['target']).name for r in actions if r['action']=='lossless_compressed'}
        removed={Path(r['path']).name for r in actions if r['action']=='deleted'}
        def transform(value):
            if isinstance(value,list): return [transform(v) for v in value]
            if isinstance(value,dict):
                result={k:transform(v) for k,v in value.items()}
                for key in ('file','clean_file','evidence_ref'):
                    if result.get(key) in removed: result['file_state']='pruned';result['retention_receipt']=str(output)
                return result
            if isinstance(value,str): return mappings.get(value,value)
            return value
        report=transform(report)
        for strip in report.get('motionStrips',[]):
            strip['frames']=[mappings.get(f,f) for f in strip.get('frames',[]) if f not in removed]
            if not strip['frames']:strip['frames_retained']=False
        report.setdefault('storage_lifecycle',[]).append(dict(receipt=str(output),
              deleted_files=len(removed),compressed_files=len(mappings),
              exact_rebuild=group_map[preview]['evidence']['exact_rebuild'],
              summary_is_lossy=True,review_states_unchanged=True))
        write(pp,report)
        concat=pp.parent/'contact-frames.ffconcat'
        if concat.exists():
            concat.unlink()  # producer command input, never a viewing entry
        write(pp.parent/'lifecycle-receipt.json',dict(schema='medical_video_media_lifecycle/v1',
              plan=str(plan_path),receipt=str(output),actions=actions,
              substitutes=group_map[preview]['evidence']['substitutes']))
    deleted_by_directory=defaultdict(set)
    for result in records:
        if result['action']=='deleted':deleted_by_directory[Path(result['path']).parent].add(result['path'])
    for directory,deleted in deleted_by_directory.items():
        comp=directory/'storage-compaction.json'
        if comp.is_file():
            payload=read(comp)
            for entry in payload.get('records',[]):
                if entry.get('source') in deleted or entry.get('target') in deleted:
                    entry['retention_status']='deleted_by_necessity_decision'
                    entry['retention_receipt']=str(output)
            write(comp,payload)
    # Scratch directories are removed only when empty; never rmtree a project.
    if 'render_temporary' in parts:
        for directory in sorted({Path(r['path']).parent for r in selected if r['category']=='render_temporary'},key=lambda p:len(p.parts),reverse=True):
            if directory.exists():
                try:directory.rmdir()
                except OSError:pass
    saved=sum(r.get('allocated_bytes',0)-r.get('target_allocated_bytes',0) for r in records if r['action'] in {'deleted','lossless_compressed'})
    receipt=dict(schema='medical_video_retention_apply/v2',created_at=stamp(),plan=str(plan_path),
                 plan_sha256=sha(plan_path),parts=sorted(parts),records=records,
                 summary=dict(actions=dict(Counter(r['action'] for r in records)),allocated_bytes_reduced=saved),
                 disk_free_bytes=os.statvfs(workspace).f_bavail*os.statvfs(workspace).f_frsize)
    write(output,receipt);print(json.dumps(receipt['summary'],ensure_ascii=False))


def restore_file(requested):
    from compact_workspace_media import pixel_sha256, exact_wav_sha_from_flac
    receipt=requested.parent/'storage-compaction.json'
    data=read(receipt)
    row=next((r for r in data.get('records',[]) if str(requested) in {r.get('source'),r.get('target')}),None)
    if row is None:raise ValueError('File not found in the local lossless receipt')
    if row.get('retention_status')=='deleted_by_necessity_decision':
        raise ValueError('This rebuildable cache was intentionally retired; use its lifecycle receipt')
    source,target=Path(row['source']),Path(row['target'])
    if source.exists():
        if sha(source)!=row.get('source_sha256'):raise ValueError('Existing source differs; preserved')
        return {'source':str(source),'action':'already_restored'}
    if sha(target)!=row['target_sha256']:raise ValueError('Compressed bytes changed')
    temp=source.with_name('.'+source.name+'.restore-tmp')
    try:
        if target.suffix=='.flac':
            subprocess.run(['flac','-s','-d','--keep-foreign-metadata','-f',str(target),'-o',str(temp)],check=True)
            if sha(temp)!=row['source_sha256']:raise ValueError('Restored WAV hash mismatch')
        else:
            from PIL import Image
            with Image.open(target) as image:image.save(temp,format='PNG')
            if pixel_sha256(temp)!=row['pixel_sha256']:raise ValueError('Restored RGBA mismatch')
        os.link(temp,source)
    finally:temp.unlink(missing_ok=True)
    return {'source':str(source),'compressed':str(target),'sha256':sha(source),'action':'restored'}


def main():
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('plan');p.add_argument('--workspace',type=Path,required=True);p.add_argument('--policy',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    p=sub.add_parser('apply');p.add_argument('--plan',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--parts',nargs='+',choices=['review_frame','audio','render_temporary'],required=True)
    p=sub.add_parser('restore');p.add_argument('--path',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='plan':
        result=plan(args.workspace.resolve(),read(args.policy));write(args.output,result);print(json.dumps(result['summary'],ensure_ascii=False))
    elif args.command=='restore':
        result=restore_file(args.path.absolute());write(args.output,result);print(json.dumps(result,ensure_ascii=False))
    else:apply(args.plan,args.output,parts=set(args.parts))
if __name__=='__main__':main()
