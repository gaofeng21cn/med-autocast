#!/usr/bin/env python3
"""MAC-owned project/media projection and revision-bound review notes."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import uuid

from med_autocast import ContractError, local_path, mapping
import yaml


try:
    from opl_client import helpers as opl_helpers
except ModuleNotFoundError as exc:
    if exc.name != 'opl_client':
        raise
    opl_helpers = None  # The standalone MCP carrier can call the owner directly.

BUNDLE = Path(__file__).resolve().parents[1] / 'workbench/scripts'
sys.path.insert(0, str(BUNDLE))
from delivery_layout import locations  # noqa: E402
from _opl_file_hash import sha256_file  # noqa: E402

PACKAGE_ID = 'med-autocast'


def resolve_workspace_root() -> Path:
    selected = Path(os.environ.get('OPL_PROFILE_WORKSPACE', ''))
    if not selected.is_absolute():
        raise ContractError('请先选择已登记制作工作区')
    return selected.resolve(strict=True)


def list_feedback_notes(directory: Path, revision: str) -> list[dict]:
    notes = []
    for note_path in sorted(directory.glob('*.json')):
        if note_path.is_symlink():
            raise ContractError('审看意见文件不能是符号链接')
        note = mapping(note_path)
        notes.append({
            **note,
            'artifact_ref': str(note_path),
            'matches_current_revision': note.get('revision') == revision,
        })
    return notes


def read_note(target: Path, identity: dict) -> dict:
    if target.is_symlink():
        raise ContractError('审看意见文件不能是符号链接')
    saved = mapping(target)
    if any(saved.get(key) != value for key, value in identity.items()):
        raise ContractError('意见编号已被不同输入使用')
    return saved


def write_note(target: Path, record: dict, identity: dict) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode='w', encoding='utf-8', dir=target.parent, suffix='.tmp', delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(record, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            handle.flush()
            os.fsync(handle.fileno())
        try:
            # Only one writer can claim the request ID, after its JSON is complete.
            os.link(temporary, target)
        except FileExistsError:
            return read_note(target, identity)
        return record
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


NOTE_ACTION = 'med-autocast.workspace.v1#review.note'
INPUT_SCHEMA = {
    'type': 'object',
    'properties': {
        'series_id': {'type': 'string', 'title': '系列'},
        'episode_id': {'type': 'string', 'title': '集号'},
        'shot_id': {'type': 'string', 'title': '镜头（可选）'},
        'request_id': {'type': 'string', 'title': '回查意见编号（可选）'},
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
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,100}', value):
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
    return {
        'id': relative(root, path),
        'title': title,
        'artifact_ref': str(path),
        'artifact_kind': kind,
        'status': 'available',
    }


def episode(root: Path, sid: str, eid: str, series: dict, spec: dict) -> dict:
    identifier(sid)
    identifier(eid)
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
    artifacts = [
        item
        for item in (
            artifact(root, project_file, '当前工程', 'project'),
            artifact(root, score_path, '镜头与时码', 'score'),
            artifact(root, current_path, title, 'video') if current_path else None,
        )
        if item
    ]
    fingerprint = hashlib.sha256()
    for source in (project_file, score_path, pointer):
        fingerprint.update(relative(root, source).encode())
        fingerprint.update(source.read_bytes() if source.is_file() else b'')
    media_digest = sha256_file(current_path) if current_path and current_path.is_file() else None
    if media_digest:
        fingerprint.update(media_digest.encode())
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
    notes_root = project / 'qa/miniapp-notes'
    if notes_root.is_symlink():
        raise ContractError('审看意见目录不能是符号链接')
    notes = list_feedback_notes(local_path(root, str(notes_root), exists=False), revision)
    defaults = {'series_id': sid, 'episode_id': eid, 'revision': revision, 'request_id': str(uuid.uuid4())}
    return {
        'id': f'{sid}/{eid}',
        'title': f'{series.get("title", sid)} · {title}',
        'series_id': sid,
        'episode_id': eid,
        'project_ref': str(project_file),
        'summary': f'{len(shots)} 个镜头 · {"当前候选可审看" if current_path and current_path.is_file() else "制作中，已有材料可继续使用"}',
        'status': 'candidate_available' if current_path and current_path.is_file() else 'in_progress',
        'revision': revision,
        'artifacts': artifacts,
        'shots': shots,
        'media': {'artifact_ref': str(current_path), 'kind': 'video', 'sha256': media_digest} if media_digest else None,
        'current_candidate': current,
        'delivery_review': {
            'source_ref': str(delivery_path),
            'reviews': delivery.get('reviews', {}),
            'quality_debt': delivery.get('quality_debt', []),
            'master_ref': delivery.get('path') or delivery.get('master_ref'),
            'scope': 'delivered_artifact_only',
        } if delivery else None,
        'review_notes': notes,
        'next_action': {
            'title': '阅读审看意见并继续当前任务',
            'summary': '通过当前 OPL 任务动作将意见交给复核或返修阶段',
        },
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
                if value.get('request_id'):
                    request_id = identifier(value['request_id'])
                    saved = next((note for note in row['review_notes'] if note.get('request_id') == request_id), None)
                    row['requested_note'] = {'status': 'recorded', 'note': saved} if saved else {'status': 'not_found', 'request_id': request_id}
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
    return {
        'state': 'ready',
        'input_schema': INPUT_SCHEMA,
        'data': {
            'schema': 'med_autocast_miniapp/v1',
            'view': view,
            'items': items,
            'diagnostics': diagnostics,
            'command_inputs': {NOTE_ACTION: {'input_schema': NOTE_SCHEMA}},
            'workspace_ref': str(root),
            'domain_quality_approved': False,
        },
    }


def record_note(root: Path, value: dict) -> dict:
    text = value.get('note')
    if not isinstance(text, str) or not text.strip() or len(text) > 20000:
        raise ContractError('审看意见必须为 1–20000 字符')
    request_id = identifier(value.get('request_id'))
    for key in ('series_id', 'episode_id'):
        identifier(value.get(key))
    # Resolve the registered episode first. An old shot may have disappeared
    # after the write succeeded; that must not prevent reading its receipt.
    selection = {key: value[key] for key in ('series_id', 'episode_id')}
    row = read_workspace(root, selection, 'media')['data']['items'][0]
    project = Path(row['project_ref']).parent
    notes_dir = local_path(root, str(project / 'qa/miniapp-notes'), exists=False)
    target = notes_dir / f'{request_id}.json'
    identity_keys = ('series_id', 'episode_id', 'shot_id', 'revision', 'request_id', 'note')
    identity = {key: value.get(key, '') for key in identity_keys}
    if target.is_file() or target.is_symlink():
        return note_result(target, read_note(target, identity))
    if value.get('revision') != row['revision']:
        raise ContractError('当前工程或候选已变化；刷新后针对当前版本记录意见')
    if value.get('shot_id'):
        shot = next((item for item in row['shots'] if item['id'] == value['shot_id']), None)
        if not shot:
            raise ContractError('所选镜头不在当前 Score 中')
        row['selected_shot'] = shot
        if row['media']:
            row['media'].update(start=shot['start'], end=shot['end'])
    record = {
        'schema': 'med_autocast_review_note/v1',
        **identity,
        'project_ref': row['project_ref'],
        'media': row['media'],
        'shot': row.get('selected_shot'),
        'domain_quality_approved': False,
        'handoff_stage': 'visual-review',
    }
    from datetime import datetime, timezone
    record['recorded_at'] = datetime.now(timezone.utc).isoformat()
    return note_result(target, write_note(target, record, identity))


def note_result(target: Path, saved: dict) -> dict:
    return {
        'state': 'ready',
        'result': {
            'status': 'recorded',
            'artifact_ref': str(target),
            'note': saved,
            'readback': {
                'data_ref': 'med-autocast.workspace.v1#status',
                'input': {key: saved[key] for key in ('series_id', 'episode_id', 'request_id')},
            },
        },
    }


def read_request() -> dict:
    if opl_helpers is not None:
        return opl_helpers.read_stdin_json()
    raw = sys.stdin.read().strip()
    request = json.loads(raw) if raw else {}
    if not isinstance(request, dict):
        raise ContractError('请求必须是 JSON 对象')
    return request


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else None
    execute = command == 'note'
    ref = NOTE_ACTION if execute else None
    try:
        request = read_request()
        if command is None and 'operation' in request:
            operation = request['operation']
            execute = operation == 'execute'
            ref = request.get('ref') or request.get('action_id')
            value = request.get('input', request.get('payload'))
            if not isinstance(value, dict):
                raise ContractError('请求输入必须是 JSON 对象')
            if execute and ref == NOTE_ACTION:
                command = 'note'
            elif operation == 'read':
                command = {
                    'med-autocast.workspace.v1#status': 'status',
                    'med-autocast.workspace.v1#media': 'media',
                }.get(ref)
        else:
            command = command or 'status'
            value = request
        if request.get('package_id') not in (None, PACKAGE_ID):
            raise ContractError('请求的软件包标识与 med-autocast 不一致')
        if command not in ('status', 'media', 'note'):
            raise ContractError('未知 Mini App 操作')

        root = resolve_workspace_root()
        result = record_note(root, value) if command == 'note' else read_workspace(root, value, command)
        if opl_helpers is not None and command != 'note':
            result = {**opl_helpers.ready_envelope(package_id=PACKAGE_ID, data=result['data']), **result}
    except (ValueError, OSError, TypeError, KeyError, yaml.YAMLError) as exc:
        result = {'state': 'unavailable', 'reason': str(exc), 'error': {'message': str(exc)}}
        if opl_helpers is not None:
            result = {**result, **opl_helpers.unavailable_envelope(package_id=PACKAGE_ID, reason=str(exc))}

    if execute:
        envelope = {
            'schema_version': 'opl-package-app-contribution-response.v1',
            'package_id': PACKAGE_ID,
            'operation': 'execute',
            'ref': ref,
            'ok': result['state'] == 'ready',
        }
        if envelope['ok']:
            result = {**envelope, 'result': result['result']} if command == 'note' and len(sys.argv) == 1 else result
        else:
            result = {**envelope, 'error': result['error']}

    if opl_helpers is not None:
        opl_helpers.write_json_stdout(result)
    else:
        print(json.dumps(result, ensure_ascii=False))
    return 0



if __name__ == '__main__':
    raise SystemExit(main())
