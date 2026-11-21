#!/usr/bin/env python3
"""Necessity-first lifecycle plan, verified pruning, and selective lossless retention.

No project/asset/publish directory is ever a deletion candidate. Plans contain
exact leaf files (or lockfile-verified rebuildable project `node_modules`
directories) and preserved substitutes. Apply validates the whole selection before
its first mutation and refuses changed inputs or active media/build writers.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import time
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
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
SKIP = {'.git', 'node_modules', '__pycache__', '.venv', '.cache'}
ASSET_LIBRARY_MARKERS = {'assets', 'entries', 'payloads', 'library'}


def stamp():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')


def read(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    os.replace(temp, path)


def sha(path, cache=None):
    if cache is not None and path in cache:
        return cache[path]
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    value = digest.hexdigest()
    if cache is not None:
        cache[path] = value
    return value


def leaves(root):
    for directory, names, files in os.walk(root, followlinks=False):
        names[:] = [n for n in names if n not in SKIP and not (Path(directory) / n).is_symlink()]
        for name in files:
            path = Path(directory) / name
            if not path.is_symlink():
                yield path


def discover_project_node_modules(workspace, scan_roots=None):
    """Find non-root, non-cache project `node_modules` directories without descending into them."""
    workspace = workspace.resolve()
    roots = [Path(r).resolve() for r in scan_roots] if scan_roots else [workspace]
    found = []
    for root in roots:
        if not root.exists():
            continue
        for directory, names, _files in os.walk(root, followlinks=False):
            current = Path(directory)
            if 'node_modules' in names:
                nm = current / 'node_modules'
                names.remove('node_modules')
                if not nm.is_symlink() and nm.resolve() != (workspace / 'node_modules').resolve():
                    rel_parts = nm.relative_to(workspace).parts
                    if rel_parts and rel_parts[0] not in {'.cache', '.venv', '.git'}:
                        found.append(nm)
            names[:] = [
                n for n in names
                if n not in {'.git', '__pycache__', '.venv', '.cache'}
                and not (current / n).is_symlink()
            ]
    return sorted(set(found))


def directory_stats(directory):
    files_count = 0
    total_size = 0
    total_alloc = 0
    for dp, dns, fns in os.walk(directory, followlinks=False):
        for fn in fns:
            p = Path(dp) / fn
            try:
                st = p.lstat()
            except OSError:
                continue
            files_count += 1
            total_size += st.st_size
            total_alloc += st.st_blocks * 512
    return files_count, total_size, total_alloc


def record(path, workspace, sha_cache=None, **fields):
    stat = path.stat()
    return dict(
        path=str(path),
        relative_path=str(path.relative_to(workspace)),
        size=stat.st_size,
        allocated_bytes=stat.st_blocks * 512,
        mtime_ns=stat.st_mtime_ns,
        sha256=sha(path, sha_cache),
        **fields,
    )


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


def is_render_scratch(path, workspace):
    parts = path.relative_to(workspace).parts
    if not parts:
        return False
    if parts[0] not in {'productions', 'out', 'work'}:
        return False
    if any(marker in parts for marker in ASSET_LIBRARY_MARKERS):
        return False
    for idx, part in enumerate(parts):
        if part.startswith('.render-'):
            # Require it to sit inside an `out` directory (or project root for legacy renders).
            parent_part = parts[idx - 1] if idx > 0 else ''
            if parent_part == 'out' or (parts[0] == 'productions' and idx == 4):
                return True
    return False


def active_projects(workspace, policy):
    wb_path = workspace / 'workbench.yaml'
    config = yaml.safe_load(wb_path.read_text(encoding='utf-8')) if wb_path.is_file() else {}
    config = config or {}
    active = set()
    for series in (config.get('series') or {}).values():
        for episode in (series.get('episodes') or {}).values():
            path = episode.get('project')
            if path:
                active.add((workspace / path).resolve())
    wip = {(workspace / p).resolve() for p in policy.get('protected_projects', [])}
    return active, wip


def semantic_document(path, workspace=None):
    if path.suffix.lower() not in {'.md', '.json', '.yaml', '.yml', '.txt'}:
        return False
    # Inventories and producer receipts enumerate their own inputs. They are
    # provenance, not requests to retain every enumerated cache forever.
    if path.name in {
        'preview.json', 'storage-compaction.json', 'lifecycle-receipt.json', 'snapshot.json',
        'project.json', 'revision.json', 'mix-receipt.json',
        'timing-receipt.json', 'narration_beats.json', 'previous-narration_beats.json',
        'contact-frames.ffconcat', 'motion-audit.json', 'pipeline-progress.json',
        'package.json', 'package-lock.json', 'kit-lock.json',
    }:
        return False
    if path.suffix == '.json':
        lower = path.name.lower()
        if any(word in lower for word in (
            'prune', 'cleanup', 'retention', 'compaction', 'inventory',
            'checkpoint', 'queue', 'build-receipt', 'lifecycle',
            'audio-freshness', 'narration-samples', 'audio-source-samples',
            'audio-delivery-binding', 'dedup-plan',
        )):
            return False
        if lower.endswith(('.receipt.json', '.motion-audit.json', '.runtime.json')):
            return False
    parts = path.relative_to(workspace).parts if workspace and path.is_relative_to(workspace) else path.parts
    if any(part.startswith(('disk-lifecycle-', 'disk-cleanup-')) for part in parts):
        return False
    if 'segments' in parts and 'audio' in parts and path.suffix == '.json':
        return False
    if parts and parts[0] == 'archive':
        return False
    return True


def references(files, candidates, workspace):
    """Resolve semantic document references to candidates with indexed O(tokens) lookups."""
    if not candidates:
        return defaultdict(set)
    aliases = defaultdict(set)
    by_project = defaultdict(set)
    by_parent_rel = defaultdict(lambda: defaultdict(set))
    by_parent_abs = defaultdict(lambda: defaultdict(set))
    candidate_parents = set()
    for path in candidates:
        names = {path.name}
        if path.suffix in {'.png', '.webp'}:
            names.add(path.with_suffix('.webp' if path.suffix == '.png' else '.png').name)
        proj = project_for(path, workspace)
        parent_abs = str(path.parent)
        parent_rel = str(path.parent.relative_to(workspace))
        candidate_parents.add((parent_abs, parent_rel))
        for nm in names:
            aliases[nm].add(path)
            if proj is not None:
                by_project[(proj, nm)].add(path)
            by_parent_abs[nm][parent_abs].add(path)
            by_parent_rel[nm][parent_rel].add(path)

    refs = defaultdict(set)
    for doc in files:
        if not semantic_document(doc, workspace):
            continue
        try:
            text = doc.read_text(encoding='utf-8')
        except (OSError, UnicodeError):
            continue
        tokens = set(PATH_TOKEN.findall(text))
        if not tokens:
            continue
        doc_project = project_for(doc, workspace)
        doc_rel = str(doc.relative_to(workspace))
        doc_parents = [parent for parent in (workspace, doc.parent, *doc.parent.parents)
                       if parent.is_relative_to(workspace)]
        matched_bare_parents = None

        for raw_token in tokens:
            token = raw_token.rstrip('.:')
            name = Path(token).name
            possible = aliases.get(name)
            if not possible:
                continue
            resolved = set()
            for parent in doc_parents:
                p = Path(os.path.abspath(parent / token))
                for variant in (p, p.with_suffix('.png'), p.with_suffix('.webp')):
                    if variant in possible:
                        resolved.add(variant)
            if not resolved and '/' not in token:
                if doc_project is not None:
                    resolved = set(by_project.get((doc_project, name), ()))
                # Bare names in a work report are scoped by a full project or
                # preview directory explicitly present in the same document.
                if not resolved:
                    if matched_bare_parents is None:
                        matched_bare_parents = {
                            (p_abs, p_rel)
                            for (p_abs, p_rel) in candidate_parents
                            if p_rel in text or p_abs in text
                        }
                    if matched_bare_parents:
                        abs_map = by_parent_abs[name]
                        rel_map = by_parent_rel[name]
                        for p_abs, p_rel in matched_bare_parents:
                            resolved.update(abs_map.get(p_abs, ()))
                            resolved.update(rel_map.get(p_rel, ()))
            for p in resolved:
                refs[p].add(doc_rel)
    return refs


def preview_evidence(directory, report, workspace, sha_cache=None):
    contact = directory / Path(report.get('contact_sheet') or 'contact.jpg').name
    strips = [directory / s['sheet'] for s in report.get('motionStrips', []) if s.get('sheet')]
    available = contact.is_file() and bool(strips) and all(p.is_file() for p in strips)
    return dict(
        valid=available,
        substitutes=[record(p, workspace, sha_cache) for p in [contact, *strips] if p.is_file()],
        exact_rebuild=False,
    )


def plan(workspace, policy, *, project_filter=None):
    workspace = workspace.resolve()
    scoped_projects = [Path(p).resolve() for p in project_filter] if project_filter else None
    if scoped_projects:
        files = []
        for proj in scoped_projects:
            confined(proj, workspace)
            files.extend(leaves(proj))
        doc_files = list(files)
        for top in ('work', 'review', 'content', 'docs'):
            top_dir = workspace / top
            if top_dir.is_dir():
                for p in leaves(top_dir):
                    if semantic_document(p, workspace):
                        doc_files.append(p)
        nm_dirs = discover_project_node_modules(workspace, scan_roots=scoped_projects)
    else:
        files = list(leaves(workspace))
        doc_files = files
        nm_dirs = discover_project_node_modules(workspace)

    active, wip = active_projects(workspace, policy)
    sha_cache = {}

    frame_paths = {
        p for p in files
        if FRAME.fullmatch(p.name)
        and ('qa' in p.relative_to(workspace).parts or p.relative_to(workspace).parts[0] in {'work', 'qa', 'out'})
    }
    audio_paths = {
        p for p in files
        if p.suffix.lower() in {'.wav', '.flac'}
        and p.relative_to(workspace).parts[0] == 'productions'
    }
    render_paths = {p for p in files if is_render_scratch(p, workspace)}

    refs = references(doc_files, frame_paths | audio_paths | render_paths, workspace)

    to_hash = list(frame_paths | audio_paths | render_paths)
    if len(to_hash) > 32:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for path, digest in zip(to_hash, pool.map(sha, to_hash)):
                sha_cache[path] = digest

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
        evidence = preview_evidence(directory, data, workspace, sha_cache)
        frozen = False
        inputs = (data.get('runtime_receipt') or {}).get('inputs', {})
        if evidence['valid'] and inputs.get('score') and inputs.get('bundle'):
            frozen = all(
                Path(inputs[key].get('path', '')).is_file()
                and sha(Path(inputs[key]['path']), sha_cache) == inputs[key].get('sha256')
                for key in ('score', 'bundle')
            )
        evidence['source_inputs_match'] = frozen
        evidence['rebuild_scope'] = 'seekable_source_replay_not_historical_png_bytes'
        evidence['source_inputs'] = [
            record(Path(inputs[key]['path']), workspace, sha_cache)
            for key in ('score', 'bundle')
            if frozen and Path(inputs[key]['path']).is_relative_to(workspace)
        ]
        actions = []
        for path in sorted(p for p in directory.iterdir() if p in frame_paths):
            handled.add(path)
            cited = sorted(refs.get(path, []))
            if cited:
                action, reason = 'keep_operational', 'explicit_issue_reference_exact_container'
            elif not evidence['valid']:
                action, reason = 'keep_compressed', 'summary_incomplete_unique_evidence'
            elif STRIP_SOURCE.fullmatch(path.name):
                action, reason = 'delete_redundant', 'motion_strip_sheet_preserved'
            elif NUMBERED.fullmatch(path.name):
                action, reason = 'delete_redundant', 'contact_and_event_evidence_preserved'
            elif project in wip:
                action, reason = 'keep_compressed', 'active_independent_repair_evidence'
            elif frozen:
                action, reason = 'delete_rebuildable', 'frozen_score_bundle_contact_and_strips_preserved'
            elif EVENT_SIDE.fullmatch(path.name):
                at = re.sub(r'-(?:before|after)\.(png|webp)$', r'-at.\1', path.name)
                if (directory / at).is_file():
                    action, reason = 'delete_redundant', 'historical_event_center_preserved_no_exact_rebuild_claim'
                else:
                    action, reason = 'keep_compressed', 'event_center_missing'
            elif path.name.startswith('clean-'):
                midpoint_files = {
                    'clean-' + f['file']
                    for f in data.get('frames', [])
                    if abs(float((f.get('state') or {}).get('progress', -1)) - .5) < .001
                }
                midpoint_files |= {
                    'clean-' + f['file']
                    for i, f in enumerate(data.get('frames', []))
                    if i % 6 == 3
                }
                if path.name in midpoint_files:
                    action, reason = 'keep_compressed', 'historical_text_free_scene_anchor'
                else:
                    action, reason = 'delete_redundant', 'historical_scene_midpoint_and_contact_preserved'
            else:
                action, reason = 'keep_compressed', 'clean_or_event_anchor_for_review'
            row = record(
                path, workspace, sha_cache,
                category='review_frame', decision=action, reason=reason,
                preview=str(preview), project=str(project) if project else None,
                references=cited,
            )
            if action == 'keep_compressed' and path.suffix == '.png':
                row['target'] = str(path.with_suffix('.webp'))
            decisions.append(row)
            actions.append(row)
        if actions:
            groups.append(dict(
                directory=str(directory),
                preview=record(preview, workspace, sha_cache),
                project=str(project) if project else None,
                evidence=evidence,
                files=len(actions),
            ))
    for path in sorted(frame_paths - handled):
        decisions.append(record(
            path, workspace, sha_cache,
            category='unbound_review_frame',
            decision='defer_review', reason='no_preview_binding',
        ))

    recipes = {}
    for receipt in (p for p in files if p.name == 'mix-receipt.json' and 'mix-history' not in p.parts):
        project = project_for(receipt, workspace)
        if project is None:
            continue
        try:
            data = read(receipt)
            config = read(project / 'project.json')
            final = project / config.get('audio', 'audio.wav')
            voice = Path(data.get('voice_source') or project / config.get('voice', 'audio/narration-normalized.wav'))
            if not voice.is_absolute():
                voice = project / voice
            tracks = data.get('music_tracks') or []
            valid = final.is_file() and data.get('audio_sha256') == sha(final, sha_cache) and voice.is_file()
            if data.get('voice_sha256'):
                valid &= sha(voice, sha_cache) == data['voice_sha256']
            for track in tracks:
                source = Path(track.get('resolved_path') or track.get('path') or '')
                if not source.is_absolute():
                    source = project / source
                valid &= source.is_file()
                if source.is_file() and track.get('sha256'):
                    valid &= sha(source, sha_cache) == track['sha256']
            if valid:
                recipes[project] = (receipt, final)
        except (ValueError, OSError, TypeError):
            pass

    for path in sorted(audio_paths):
        project = project_for(path, workspace)
        if project is None:
            continue
        cited = sorted(refs.get(path, []))
        in_mix_history = 'mix-history' in path.relative_to(project).parts
        if path.stem in DERIVED_AUDIO and path.parent == project / 'audio' and project in recipes and not cited:
            action, reason = 'delete_rebuildable', 'final_mix_and_recipe_sources_verified'
        elif path.suffix == '.flac':
            action, reason = 'keep_compressed', 'lossless_historical_or_source_audio'
        elif in_mix_history and not cited:
            action, reason = 'keep_compressed', 'prior_mix_history_lossless_flac_restorable'
        elif project in active or project in wip or cited:
            action, reason = 'keep_operational', 'active_audio_input_or_explicit_reference'
        else:
            action, reason = 'keep_compressed', 'frozen_revision_source_or_mix_for_restoration'
        row = record(
            path, workspace, sha_cache,
            category='audio', decision=action, reason=reason,
            project=str(project), references=cited,
        )
        if action == 'keep_compressed' and path.suffix == '.wav':
            row['target'] = str(path.with_suffix('.flac'))
        if project in recipes and action.startswith('delete'):
            row['substitutes'] = [record(p, workspace, sha_cache) for p in recipes[project]]
        decisions.append(row)

    for path in sorted(render_paths):
        decisions.append(record(
            path, workspace, sha_cache,
            category='render_temporary',
            decision='keep_operational' if refs.get(path) else 'delete_rebuildable',
            reason='explicit_reference' if refs.get(path) else 'renderer_scratch_not_a_source',
            references=sorted(refs.get(path, [])),
        ))

    for nm in nm_dirs:
        parent = nm.parent
        lockfile = parent / 'package-lock.json'
        pkgfile = parent / 'package.json'
        files_count, total_size, total_alloc = directory_stats(nm)
        proj = project_for(nm, workspace)
        if lockfile.is_file() and pkgfile.is_file():
            row = dict(
                path=str(nm),
                relative_path=str(nm.relative_to(workspace)),
                entry_type='directory',
                files_count=files_count,
                size=total_size,
                allocated_bytes=total_alloc,
                mtime_ns=nm.stat().st_mtime_ns,
                category='node_modules',
                decision='delete_rebuildable',
                reason='lockfile_present_shared_deps_or_npm_ci_rebuildable',
                project=str(proj) if proj else str(parent),
                substitutes=[record(lockfile, workspace, sha_cache), record(pkgfile, workspace, sha_cache)],
                rebuild_command='paper_project build (shared_node_deps) or npm ci --no-audit --no-fund',
            )
        else:
            row = dict(
                path=str(nm),
                relative_path=str(nm.relative_to(workspace)),
                entry_type='directory',
                files_count=files_count,
                size=total_size,
                allocated_bytes=total_alloc,
                mtime_ns=nm.stat().st_mtime_ns,
                category='node_modules',
                decision='defer_review',
                reason='missing_package_lockfile',
                project=str(proj) if proj else str(parent),
            )
        decisions.append(row)

    totals = defaultdict(lambda: {'files': 0, 'allocated_bytes': 0})
    for row in decisions:
        key = f"{row['category']}:{row['decision']}"
        totals[key]['files'] += 1
        totals[key]['allocated_bytes'] += row['allocated_bytes']

    inventory = defaultdict(lambda: {'files': 0, 'size': 0, 'allocated_bytes': 0})
    for p in files:
        try:
            s = p.stat()
            key = p.relative_to(workspace).parts[0]
            inventory[key]['files'] += 1
            inventory[key]['size'] += s.st_size
            inventory[key]['allocated_bytes'] += s.st_blocks * 512
        except OSError:
            pass
    if nm_dirs:
        inventory['project_node_modules'] = {
            'directories': len(nm_dirs),
            'files': sum(r.get('files_count', 0) for r in decisions if r['category'] == 'node_modules'),
            'size': sum(r['size'] for r in decisions if r['category'] == 'node_modules'),
            'allocated_bytes': sum(r['allocated_bytes'] for r in decisions if r['category'] == 'node_modules'),
        }

    vfs = os.statvfs(workspace)
    return dict(
        schema=SCHEMA,
        created_at=stamp(),
        workspace=str(workspace),
        status='planned',
        policy=policy,
        scoped_projects=[str(p) for p in scoped_projects] if scoped_projects else None,
        protected_projects=sorted(map(str, active | wip)),
        groups=groups,
        decisions=decisions,
        summary=dict(totals),
        inventory=dict(inventory),
        disk_free_bytes=vfs.f_bavail * vfs.f_frsize,
    )


def assert_idle(workspace):
    process = subprocess.run(['ps', '-axo', 'pid=,command='], capture_output=True, text=True, check=True)
    for line in process.stdout.splitlines():
        if str(workspace) not in line:
            continue
        try:
            pid = int(line.split(None, 1)[0])
        except ValueError:
            continue
        if pid == os.getpid():
            continue
        if any(token in line for token in (
            'preview_local_animation.mjs',
            'render_local_animation.mjs',
            'render_javascript_animation.py',
            'ffmpeg ',
            'render_narration.py',
            'npm ci',
            'npm install',
            'npm run build',
            'scripts/build.mjs',
        )):
            raise RuntimeError(f'Active media/build writer: {line[:240]}')


def apply(plan_path, output, *, parts):
    data = read(plan_path)
    if data.get('schema') != SCHEMA:
        raise ValueError('Expected necessity-first v2 plan')
    workspace = Path(data['workspace']).resolve()
    selected = [
        r for r in data['decisions']
        if r['category'] in parts and (r['decision'].startswith('delete') or r.get('target'))
    ]
    assert_idle(workspace)
    if any(r.get('target', '').endswith('.webp') for r in selected) and not shutil.which('cwebp'):
        raise RuntimeError('Missing cwebp; no files changed')
    if any(r.get('target', '').endswith('.flac') for r in selected) and not shutil.which('flac'):
        raise RuntimeError('Missing flac; no files changed')

    group_map = {g['preview']['path']: g for g in data['groups']}
    protected_evidence = {}
    root_nm = (workspace / 'node_modules').resolve()
    cache_root = (workspace / '.cache').resolve()
    for row in selected:
        path = confined(Path(row['path']), workspace)
        if row.get('target'):
            confined(Path(row['target']), workspace)
        if row['category'] == 'node_modules':
            if path.name != 'node_modules' or path.resolve() == root_nm or path.resolve().is_relative_to(cache_root):
                raise ValueError(f'Invalid node_modules candidate: {path}')
            if not row.get('substitutes'):
                raise ValueError(f'Missing lockfile substitute for node_modules: {path}')
            if path.exists() and not path.is_dir():
                raise ValueError(f'Expected directory for node_modules: {path}')
        else:
            if row['category'] == 'review_frame' and (
                not FRAME.fullmatch(path.name) or str(path.parent / 'preview.json') != row.get('preview')
            ):
                raise ValueError(f'Invalid review leaf: {path}')
            if row['category'] == 'render_temporary' and not is_render_scratch(path, workspace):
                raise ValueError(f'Invalid renderer scratch leaf: {path}')
            if row['category'] == 'audio' and (
                path.suffix not in {'.wav', '.flac'} or path.relative_to(workspace).parts[0] != 'productions'
            ):
                raise ValueError(f'Invalid audio leaf: {path}')
            if row['category'] == 'audio' and row['decision'].startswith('delete'):
                project = project_for(path, workspace)
                if project is None or path.parent != project / 'audio' or path.stem not in DERIVED_AUDIO:
                    raise ValueError(f'Audio source cannot be deleted: {path}')
            if path.exists() and sha(path) != row['sha256']:
                raise RuntimeError(f'Changed candidate: {path}')
        if row.get('preview'):
            group = group_map[row['preview']]
            if row['decision'].startswith('delete') and not group['evidence']['valid']:
                raise ValueError('Missing preserved evidence')
            for item in [group['preview'], *group['evidence']['substitutes'], *group['evidence'].get('source_inputs', [])]:
                protected_evidence[item['path']] = item
        for item in row.get('substitutes', []):
            protected_evidence[item['path']] = item

    for item in protected_evidence.values():
        path = confined(Path(item['path']), workspace)
        if not path.is_file() or sha(path) != item['sha256']:
            raise RuntimeError(f'Changed substitute: {path}')

    output.parent.mkdir(parents=True, exist_ok=True)
    journal = output.with_suffix('.jsonl')
    records = []
    group_actions = defaultdict(list)
    from compact_workspace_media import convert_png, convert_wav, update_mix_snapshot

    def emit(row, conversion=None):
        source = Path(row['path'])
        if conversion is None:
            if row['category'] == 'node_modules':
                shutil.rmtree(source)
                if source.exists():
                    raise RuntimeError(f'Failed to remove node_modules: {source}')
                result = {**row, 'action': 'deleted_directory'}
            else:
                source.unlink()
                result = {**row, 'action': 'deleted'}
        else:
            comp = source.parent / 'storage-compaction.json'
            previous = read(comp) if comp.exists() else {'schema': 'medical_video_storage_compaction_group/v1', 'records': []}
            previous['records'] = [r for r in previous['records'] if r.get('source') != str(source)] + [conversion]
            previous['necessity_policy'] = 'retained_after_necessity_decision'
            write(comp, previous)
            if 'mix-history' in source.parts and source.suffix == '.wav':
                update_mix_snapshot(source.parent, {source.name: Path(row['target']).name})
            source.unlink()
            result = {**row, **conversion, 'action': 'lossless_compressed'}
        records.append(result)
        if row.get('preview'):
            group_actions[row['preview']].append(result)
        stream.write(json.dumps(result, ensure_ascii=False) + '\n')
        stream.flush()
        if len(records) % 250 == 0:
            print(json.dumps({'processed': len(records), 'total': len(selected)}), flush=True)

    def convert(row):
        source = Path(row['path'])
        converter = convert_png if source.suffix == '.png' else convert_wav
        return converter(dict(
            source=str(source),
            target=row['target'],
            kind='qa_png' if source.suffix == '.png' else 'audio_retained',
            allocated_bytes=row['allocated_bytes'],
            size=row['size'],
            mtime_ns=row['mtime_ns'],
        ))

    with journal.open('a', encoding='utf-8') as stream:
        for index, row in enumerate(r for r in selected if r['decision'].startswith('delete')):
            source = Path(row['path'])
            if not source.exists():
                records.append(dict(path=str(source), action='already_absent'))
                continue
            if index % 250 == 0:
                assert_idle(workspace)
            emit(row)
        compression = [r for r in selected if r.get('target') and Path(r['path']).exists()]
        with ThreadPoolExecutor(max_workers=8) as pool:
            for offset in range(0, len(compression), 64):
                assert_idle(workspace)
                futures = {pool.submit(convert, r): r for r in compression[offset:offset + 64]}
                for future in as_completed(futures):
                    emit(futures[future], future.result())

    for preview, actions in group_actions.items():
        pp = Path(preview)
        report = read(pp)
        mappings = {Path(r['path']).name: Path(r['target']).name for r in actions if r['action'] == 'lossless_compressed'}
        removed = {Path(r['path']).name for r in actions if r['action'] == 'deleted'}

        def transform(value):
            if isinstance(value, list):
                return [transform(v) for v in value]
            if isinstance(value, dict):
                result = {k: transform(v) for k, v in value.items()}
                for key in ('file', 'clean_file', 'evidence_ref'):
                    if result.get(key) in removed:
                        result['file_state'] = 'pruned'
                        result['retention_receipt'] = str(output)
                return result
            if isinstance(value, str):
                return mappings.get(value, value)
            return value

        report = transform(report)
        for strip in report.get('motionStrips', []):
            strip['frames'] = [mappings.get(f, f) for f in strip.get('frames', []) if f not in removed]
            if not strip['frames']:
                strip['frames_retained'] = False
        report.setdefault('storage_lifecycle', []).append(dict(
            receipt=str(output),
            deleted_files=len(removed),
            compressed_files=len(mappings),
            exact_rebuild=group_map[preview]['evidence']['exact_rebuild'],
            summary_is_lossy=True,
            review_states_unchanged=True,
        ))
        write(pp, report)
        concat = pp.parent / 'contact-frames.ffconcat'
        if concat.exists():
            concat.unlink()
        write(pp.parent / 'lifecycle-receipt.json', dict(
            schema='medical_video_media_lifecycle/v1',
            plan=str(plan_path),
            receipt=str(output),
            actions=actions,
            substitutes=group_map[preview]['evidence']['substitutes'],
        ))

    deleted_by_directory = defaultdict(set)
    for result in records:
        if result['action'] == 'deleted':
            deleted_by_directory[Path(result['path']).parent].add(result['path'])
    for directory, deleted in deleted_by_directory.items():
        comp = directory / 'storage-compaction.json'
        if comp.is_file():
            payload = read(comp)
            for entry in payload.get('records', []):
                if entry.get('source') in deleted or entry.get('target') in deleted:
                    entry['retention_status'] = 'deleted_by_necessity_decision'
                    entry['retention_receipt'] = str(output)
            write(comp, payload)

    if 'render_temporary' in parts:
        scratch_dirs = sorted(
            {Path(r['path']).parent for r in selected if r['category'] == 'render_temporary'},
            key=lambda p: len(p.parts),
            reverse=True,
        )
        for directory in scratch_dirs:
            if directory.exists() and directory.name.startswith('.render-'):
                try:
                    directory.rmdir()
                except OSError:
                    pass

    saved = sum(
        r.get('allocated_bytes', 0) - r.get('target_allocated_bytes', 0)
        for r in records
        if r['action'] in {'deleted', 'deleted_directory', 'lossless_compressed'}
    )
    vfs = os.statvfs(workspace)
    receipt = dict(
        schema='medical_video_retention_apply/v2',
        created_at=stamp(),
        plan=str(plan_path),
        plan_sha256=sha(plan_path),
        parts=sorted(parts),
        records=records,
        summary=dict(actions=dict(Counter(r['action'] for r in records)), allocated_bytes_reduced=saved),
        disk_free_bytes=vfs.f_bavail * vfs.f_frsize,
    )
    write(output, receipt)
    print(json.dumps(receipt['summary'], ensure_ascii=False))


def restore_file(requested):
    from compact_workspace_media import pixel_sha256
    receipt = requested.parent / 'storage-compaction.json'
    data = read(receipt)
    row = next((r for r in data.get('records', []) if str(requested) in {r.get('source'), r.get('target')}), None)
    if row is None:
        raise ValueError('File not found in the local lossless receipt')
    if row.get('retention_status') == 'deleted_by_necessity_decision':
        raise ValueError('This rebuildable cache was intentionally retired; use its lifecycle receipt')
    source, target = Path(row['source']), Path(row['target'])
    if source.exists():
        if sha(source) != row.get('source_sha256'):
            raise ValueError('Existing source differs; preserved')
        return {'source': str(source), 'action': 'already_restored'}
    if sha(target) != row['target_sha256']:
        raise ValueError('Compressed bytes changed')
    temp = source.with_name('.' + source.name + '.restore-tmp')
    try:
        if target.suffix == '.flac':
            subprocess.run(['flac', '-s', '-d', '--keep-foreign-metadata', '-f', str(target), '-o', str(temp)], check=True)
            if sha(temp) != row['source_sha256']:
                raise ValueError('Restored WAV hash mismatch')
        else:
            from PIL import Image
            with Image.open(target) as image:
                image.save(temp, format='PNG')
            if pixel_sha256(temp) != row['pixel_sha256']:
                raise ValueError('Restored RGBA mismatch')
        os.link(temp, source)
    finally:
        temp.unlink(missing_ok=True)
    return {'source': str(source), 'compressed': str(target), 'sha256': sha(source), 'action': 'restored'}


def check_health(workspace):
    """Fast read-only storage hygiene audit against lifecycle baselines."""
    workspace = workspace.resolve()
    nm_dirs = discover_project_node_modules(workspace)
    nm_alloc = 0
    for nm in nm_dirs:
        _, _, al = directory_stats(nm)
        nm_alloc += al

    active, _ = active_projects(workspace, {})
    render_scratch_files = 0
    render_scratch_alloc = 0
    numbered_or_strip_files = 0
    numbered_or_strip_alloc = 0
    mix_history_wavs = 0
    mix_history_alloc = 0
    inactive_wavs = 0
    inactive_wav_alloc = 0

    for p in leaves(workspace):
        try:
            st = p.stat()
        except OSError:
            continue
        al = st.st_blocks * 512
        if is_render_scratch(p, workspace):
            render_scratch_files += 1
            render_scratch_alloc += al
        elif (NUMBERED.fullmatch(p.name) or STRIP_SOURCE.fullmatch(p.name)) and (p.parent / 'preview.json').is_file():
            if (p.parent / 'contact.jpg').is_file() and any(p.parent.glob('strip-s*.jpg')):
                numbered_or_strip_files += 1
                numbered_or_strip_alloc += al
        elif p.suffix.lower() == '.wav' and p.relative_to(workspace).parts[0] == 'productions':
            proj = project_for(p, workspace)
            if proj and 'mix-history' in p.relative_to(proj).parts:
                mix_history_wavs += 1
                mix_history_alloc += al
            elif proj and proj not in active:
                inactive_wavs += 1
                inactive_wav_alloc += al

    cache_root = workspace / '.cache' / 'node-deps'
    pools = []
    if cache_root.is_dir():
        for child in sorted(cache_root.iterdir()):
            if child.is_dir() and (child / '.ready.json').is_file():
                fc, sz, al = directory_stats(child)
                pools.append({'fingerprint': child.name, 'files': fc, 'allocated_bytes': al})

    vfs = os.statvfs(workspace)
    findings = []
    if nm_dirs:
        findings.append({'code': 'project_node_modules_present', 'count': len(nm_dirs), 'allocated_bytes': nm_alloc})
    if render_scratch_files:
        findings.append({'code': 'render_scratch_present', 'count': render_scratch_files, 'allocated_bytes': render_scratch_alloc})
    if numbered_or_strip_files:
        findings.append({'code': 'redundant_numbered_or_strip_frames', 'count': numbered_or_strip_files, 'allocated_bytes': numbered_or_strip_alloc})
    if mix_history_wavs:
        findings.append({'code': 'uncompressed_mix_history_wavs', 'count': mix_history_wavs, 'allocated_bytes': mix_history_alloc})
    if inactive_wavs:
        findings.append({'code': 'inactive_revision_wavs', 'count': inactive_wavs, 'allocated_bytes': inactive_wav_alloc})

    return {
        'schema': 'medical_video_storage_health/v1',
        'checked_at': stamp(),
        'workspace': str(workspace),
        'status': 'clean' if not findings else 'attention_needed',
        'shared_node_deps_pools': pools,
        'project_node_modules': {'directories': len(nm_dirs), 'allocated_bytes': nm_alloc},
        'render_scratch': {'files': render_scratch_files, 'allocated_bytes': render_scratch_alloc},
        'redundant_preview_frames': {'files': numbered_or_strip_files, 'allocated_bytes': numbered_or_strip_alloc},
        'uncompressed_mix_history_wavs': {'files': mix_history_wavs, 'allocated_bytes': mix_history_alloc},
        'inactive_revision_wavs': {'files': inactive_wavs, 'allocated_bytes': inactive_wav_alloc},
        'findings': findings,
        'disk_free_bytes': vfs.f_bavail * vfs.f_frsize,
    }


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest='command', required=True)

    p = sub.add_parser('plan')
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--policy', type=Path, required=True)
    p.add_argument('--project', type=Path, action='append', help='Optional single/multi project scope for fast closeout')
    p.add_argument('--output', type=Path, required=True)

    p = sub.add_parser('apply')
    p.add_argument('--plan', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument(
        '--parts',
        nargs='+',
        choices=['review_frame', 'audio', 'render_temporary', 'node_modules'],
        required=True,
    )

    p = sub.add_parser('restore')
    p.add_argument('--path', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)

    p = sub.add_parser('check')
    p.add_argument('--workspace', type=Path, required=True)
    p.add_argument('--output', type=Path)

    args = parser.parse_args()
    if args.command == 'plan':
        result = plan(args.workspace.resolve(), read(args.policy), project_filter=args.project)
        write(args.output, result)
        print(json.dumps(result['summary'], ensure_ascii=False))
    elif args.command == 'restore':
        result = restore_file(args.path.absolute())
        write(args.output, result)
        print(json.dumps(result, ensure_ascii=False))
    elif args.command == 'check':
        result = check_health(args.workspace.resolve())
        if args.output:
            write(args.output, result)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        apply(args.plan, args.output, parts=set(args.parts))


if __name__ == '__main__':
    main()
