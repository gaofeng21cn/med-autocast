#!/usr/bin/env python3
"""MAC-owned project/media projection and revision-bound review notes."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import uuid

from med_autocast import ContractError, local_path, mapping
import yaml

BUNDLE = Path(__file__).resolve().parents[1] / 'workbench/scripts'
sys.path.insert(0, str(BUNDLE))
from delivery_layout import locations

NOTE_ACTION = 'med-autocast.workspace.v1#review.note'
INPUT_SCHEMA = {
    'type': 'object',
    'properties': {
        'series_id': {'type': 'string', 'title': '系列'},
        'episode_id': {'type': 'string', 'title': '集号'},
        'shot_id': {'type': 'string', 'title': '镜头（可选）'},
    },
    'additionalProperties': False,
}
NOTE_SCHEMA = {
    'type': 'object',
    'required': ['series_id', 'episode_id', 'revision', 'request_id', 'note'],
    'properties': {
        **{name: {**field, **({'readOnly': True} if name != 'shot_id' else {})}
           for name, field in INPUT_SCHEMA['properties'].items()},
        'revision': {'type': 'string', 'title': '候选版本', 'readOnly': True},
        'request_id': {'type': 'string', 'title': '意见编号', 'readOnly': True},
        'note': {'type': 'string', 'title': '审看意见', 'format': 'textarea', 'maxLength': 20000},
    },
    'additionalProperties': False,
}


def identifier(value: object) -> str:
    if not isinstance(value, str) or not value or value in ('.', '..') or Path(value).name != value or '\\' in value:
        raise ContractError('需要有效的系列、集号或请求编号')
    return value


def relative(root: Path, path: Path) -> str:
    return str(path.resolve().relative_to(root.resolve()))


def optional_record(root: Path, path: Path) -> dict:
    path = local_path(root, str(path), exists=False)
    return mapping(path) if path.is_file() else {}


def artifact(root: Path, path: Path, title: str, kind: str) -> dict | None:
    path = local_path(root, str(path), exists=False)
    if not path.is_file():
        return None
    return {'id': relative(root, path), 'title': title, 'artifact_ref': str(path),
            'artifact_kind': kind, 'status': 'available'}


def episode(root: Path, sid: str, eid: str, series: dict, spec: dict) -> dict:
    identifier(sid); identifier(eid)
    project = local_path(root, spec.get('project'), exists=False)
    project_file = local_path(root, str(project / spec.get('entry', 'project.json')), exists=False)
    config = optional_record(root, project_file)
    if config and any(config.get(key) not in (None, value) for key, value in [('series_id', sid), ('episode_id', eid)]):
        raise ContractError('登记工程与系列/集号不一致')
    score_path = local_path(root, str(project / config.get('score', 'score.json')), exists=False)
    score = optional_record(root, score_path)
    pointer = local_path(root, str(project / 'out/current.json'), exists=False)
    current = optional_record(root, pointer)
    current_path = local_path(root, str(project / current['path']), exists=False) if current.get('path') else None
    title = str(config.get('title') or spec.get('title') or eid)
    artifacts = [item for item in (
        artifact(root, project_file, '当前工程', 'project'),
        artifact(root, score_path, '镜头与时码', 'score'),
        artifact(root, current_path, title, 'video') if current_path else None,
    ) if item]
    fingerprint = hashlib.sha256()
    for source in (project_file, score_path, pointer):
        fingerprint.update(relative(root, source).encode())
        fingerprint.update(source.read_bytes() if source.is_file() else b'')
    if current_path and current_path.is_file():
        stat = current_path.stat()
        fingerprint.update(f'{stat.st_size}:{stat.st_mtime_ns}'.encode())
    revision = 'sha256:' + fingerprint.hexdigest()
    shots = []
    for shot in score.get('shots', []):
        if not isinstance(shot, dict) or not isinstance(shot.get('id'), str):
            continue
        start, end = shot.get('start'), shot.get('end')
        if any(isinstance(t, bool) or not isinstance(t, (int, float)) or not math.isfinite(t) for t in (start, end)) or not 0 <= start < end:
            continue
        shots.append({'id': shot['id'], 'title': shot.get('title', shot['id']), 'start': start, 'end': end})
    loc = locations(root, sid, eid)
    delivery_path = local_path(root, str(loc['record'] / 'manifest.json'), exists=False)
    delivery = optional_record(root, delivery_path)
    for key, expected in [('series_id', sid), ('episode_id', eid)]:
        if delivery and delivery.get(key) not in (None, expected):
            raise ContractError('交付记录与系列/集号不一致')
    delivered = artifact(root, delivery_path, '交付与原审查记录', 'review')
    if delivered:
        artifacts.append(delivered)
    notes_root = local_path(root, str(project / 'qa/miniapp-notes'), exists=False)
    notes = []
    if notes_root.is_dir():
        for note_path in sorted(notes_root.glob('*.json')):
            note = mapping(local_path(root, str(note_path)))
            notes.append({**note, 'artifact_ref': str(note_path), 'matches_current_revision': note.get('revision') == revision})
    defaults = {'series_id': sid, 'episode_id': eid, 'revision': revision, 'request_id': str(uuid.uuid4())}
    return {
        'id': f'{sid}/{eid}', 'title': f'{series.get("title", sid)} · {title}',
        'series_id': sid, 'episode_id': eid, 'project_ref': str(project_file),
        'summary': f'{len(shots)} 个镜头 · {"当前候选可审看" if current_path and current_path.is_file() else "制作中，已有材料可继续使用"}',
        'status': 'candidate_available' if current_path and current_path.is_file() else 'in_progress',
        'revision': revision, 'artifacts': artifacts, 'shots': shots,
        'media': {'artifact_ref': str(current_path), 'kind': 'video', 'sha256': current.get('sha256')} if current_path and current_path.is_file() else None,
        'current_candidate': current,
        'delivery_review': {'source_ref': str(delivery_path), 'reviews': delivery.get('reviews', {}),
                            'quality_debt': delivery.get('quality_debt', []), 'master_ref': delivery.get('path') or delivery.get('master_ref'),
                            'scope': 'delivered_artifact_only'} if delivery else None,
        'review_notes': notes,
        'next_action': {'title': '阅读审看意见并继续当前任务', 'summary': '通过当前 OPL 任务动作将意见交给复核或返修阶段'},
        'actions': [{'action_ref': NOTE_ACTION, 'input': defaults}],
        'source_refs': [str(p) for p in (project_file, score_path, pointer) if p.is_file()],
    }


def read_workspace(root: Path, value: dict, view: str) -> dict:
    root = root.resolve()
    config = mapping(local_path(root, 'workbench.yaml'), yaml_format=True)
    series_map = config.get('series') or {}
    selected_series = value.get('series_id')
    selected_episode = value.get('episode_id')
    if selected_episode and not selected_series:
        raise ContractError('选择集号时同时指定系列')
    if selected_series and selected_series not in series_map:
        raise ContractError('所选系列未登记')
    items = []
    diagnostics = []
    for sid, series in series_map.items():
        if selected_series and sid != selected_series:
            continue
        episodes = series.get('episodes') or {}
        if selected_episode and selected_episode not in episodes:
            raise ContractError('所选集号未登记')
        for eid, spec in episodes.items():
            if selected_episode and eid != selected_episode:
                continue
            try:
                row = episode(root, sid, eid, series, spec)
                if value.get('shot_id'):
                    if not selected_episode:
                        raise ContractError('定位镜头时先选择系列与集号')
                    shot = next((s for s in row['shots'] if s['id'] == value['shot_id']), None)
                    if not shot:
                        raise ContractError('所选镜头不在当前 Score 中')
                    row['selected_shot'] = shot
                    row['actions'][0]['input']['shot_id'] = shot['id']
                    if row['media']:
                        row['media'].update(start=shot['start'], end=shot['end'])
                items.append(row)
            except (ValueError, OSError, TypeError) as exc:
                if selected_episode:
                    raise
                diagnostics.append({'series_id': sid, 'episode_id': eid, 'message': str(exc)})
    return {'state': 'ready', 'data': {'schema': 'med_autocast_miniapp/v1', 'view': view, 'items': items,
        'diagnostics': diagnostics, 'command_inputs': {NOTE_ACTION: {'input_schema': NOTE_SCHEMA}},
        'workspace_ref': str(root), 'domain_quality_approved': False}}


def record_note(root: Path, value: dict) -> dict:
    text = value.get('note')
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise ContractError('审看意见必须为 1–20000 字符')
    request_id = identifier(value.get('request_id'))
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', request_id):
        raise ContractError('意见编号只允许字母、数字、下划线与短横线')
    for key in ('series_id', 'episode_id'):
        identifier(value.get(key))
    row = read_workspace(root, value, 'media')['data']['items'][0]
    project = Path(row['project_ref']).parent
    target = local_path(root, str(project / 'qa/miniapp-notes' / (request_id + '.json')), exists=False)
    identity = {key: value.get(key, '') for key in ('series_id', 'episode_id', 'shot_id', 'revision', 'request_id', 'note')}
    if target.is_file():
        saved = mapping(target)
        if any(saved.get(key) != field for key, field in identity.items()):
            raise ContractError('意见编号已被不同输入使用')
        return {'state': 'ready', 'result': {'status': 'recorded', 'artifact_ref': str(target), 'note': saved}}
    if value.get('revision') != row['revision']:
        raise ContractError('当前工程或候选已变化；刷新后针对当前版本记录意见')
    record = {'schema': 'med_autocast_review_note/v1', **identity,
              'recorded_at': datetime.now(timezone.utc).isoformat(),
              'project_ref': row['project_ref'], 'media': row['media'],
              'shot': row.get('selected_shot'), 'domain_quality_approved': False,
              'handoff_stage': 'visual-review'}
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with target.open('x', encoding='utf-8') as handle:
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
    except FileExistsError:
        return record_note(root, value)
    saved = mapping(target)
    return {'state': 'ready', 'result': {'status': 'recorded', 'artifact_ref': str(target), 'note': saved}}


def main() -> int:
    try:
        root_value = os.environ.get('OPL_PROFILE_WORKSPACE', '')
        if not root_value or not Path(root_value).is_absolute():
            raise ContractError('请先选择已登记制作工作区')
        root = Path(root_value).resolve()
        value = json.load(sys.stdin)
        if not isinstance(value, dict):
            raise ContractError('输入必须为对象')
        operation = sys.argv[1] if len(sys.argv) > 1 else 'status'
        if operation not in ('status', 'media', 'note'):
            raise ContractError('未知 Mini App 操作')
        result = record_note(root, value) if operation == 'note' else read_workspace(root, value, operation)
    except (ValueError, OSError, TypeError, KeyError, yaml.YAMLError) as exc:
        result = {'state': 'unavailable', 'reason': str(exc)}
        if len(sys.argv) > 1 and sys.argv[1] == 'note':
            result = {'schema_version': 'opl-package-app-contribution-response.v1', 'ok': False,
                      'operation': 'execute', 'ref': NOTE_ACTION, 'error': {'message': str(exc)}}
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
