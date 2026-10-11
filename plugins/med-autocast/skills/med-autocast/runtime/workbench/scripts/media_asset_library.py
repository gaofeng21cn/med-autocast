#!/usr/bin/env python3
"""MAC companion discovery, non-blocking installation and exact-version reuse."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import yaml

REPOSITORY = 'https://github.com/gaofeng21cn/mac-media-assets.git'
NOTE = '资产库提供可选起点；按当前故事适配、替换或新创，未完成当前镜头审查。'


def config(workspace):
    path = workspace / 'workbench.yaml'
    if not path.is_file():
        return {}
    value = yaml.safe_load(path.read_text()) or {}
    if not isinstance(value, dict):
        raise ValueError('工作台配置应为对象，资产发现保持未完成')
    return value


def absolute(root, ref):
    return (root / Path(ref).expanduser()).resolve()


def valid(root):
    return (root / 'catalog/assets.jsonl').is_file() and (root / 'tools/query_assets.py').is_file()


def locate(workspace, explicit=None):
    spec = config(workspace).get('asset_library') or {}
    if explicit:
        return absolute(workspace, explicit), 'explicit'
    if spec.get('enabled') is False:
        return None, 'disabled'
    if spec.get('root') or spec.get('repo'):
        preferred = absolute(workspace, spec.get('root') or spec['repo'])
        if valid(preferred) or preferred.exists():
            return preferred, 'workspace_config'
        # An explicit missing path is the install target. The generated relative
        # default can instead consume an already installed shared companion.
        if spec.get('root') != '../mac-media-assets':
            return preferred, 'workspace_config'
    else:
        preferred = None
    codex = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex')
    sources = Path(os.environ.get('OPL_COMPANION_SOURCES_ROOT') or codex / 'opl-companion-sources')
    candidates = []
    if os.environ.get('MAC_MEDIA_ASSETS_ROOT'):
        candidates.append(Path(os.environ['MAC_MEDIA_ASSETS_ROOT']).expanduser())
    candidates.extend([workspace.parent / 'mac-media-assets', sources / 'mac-media-assets'])
    skill = codex / 'skills/mac-media-assets'
    if skill.is_dir():
        candidates.append(skill.resolve().parents[1])
    cache = codex / 'plugins/cache/mac-media-assets'
    if cache.is_dir():
        candidates.extend(path.parents[2] for path in cache.glob('**/skills/mac-media-assets/SKILL.md'))
    for root in candidates:
        root = root.resolve()
        if valid(root):
            return root, 'installed_companion'
    return preferred or sources / 'mac-media-assets', 'install_target'


def report(workspace, explicit=None):
    root, source = locate(workspace, explicit)
    result = {'schema': 'mac_media_assets_status/v1', 'read_only': True, 'status': 'unavailable',
              'repo': str(root) if root else None, 'discovery': source,
              'repository': REPOSITORY, 'blocks_production': False, 'note': NOTE}
    if root is None:
        result['status'] = 'disabled'
    elif valid(root):
        try:
            rows = [json.loads(line) for line in (root / 'catalog/assets.jsonl').read_text().splitlines() if line.strip()]
            result.update(status='available', asset_count=len(rows), payload_files=sum(len(row.get('payload', [])) for row in rows),
                          skill=str(root / 'skills/mac-media-assets/SKILL.md'))
        except (OSError, ValueError, TypeError) as error:
            result.update(status='diagnostic', diagnostic=type(error).__name__)
    return result


def ensure(workspace, explicit=None, repository=REPOSITORY, offline=False):
    result = report(workspace, explicit)
    result['read_only'] = False
    if (config(workspace).get('asset_library') or {}).get('auto_install') is False:
        return {**result, 'installation': 'auto_install_disabled'}
    if result['status'] in {'available', 'disabled'}:
        result['installation'] = 'reused_existing' if result['status'] == 'available' else 'disabled'
        return result
    root = Path(result['repo'])
    if root.exists():
        return {**result, 'installation': 'preserved_existing', 'diagnostic': '配置目录已有内容，未覆盖；请检查资产库路径'}
    if offline or os.environ.get('OPL_COMPANION_DISABLE_REMOTE_INSTALL') == '1':
        return {**result, 'installation': 'not_downloaded', 'diagnostic': '离线模式；继续本地素材或新创'}
    if not shutil.which('git'):
        return {**result, 'installation': 'not_downloaded', 'diagnostic': '缺少 Git；继续本地素材或新创'}
    root.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(prefix='.mac-media-assets-', dir=root.parent) as temporary:
            staged = Path(temporary) / 'repo'
            completed = subprocess.run(['git', 'clone', '--depth', '1', '--single-branch', '--branch', 'main',
                                        '--', repository, str(staged)], capture_output=True, timeout=240,
                                       env={**os.environ, 'GIT_TERMINAL_PROMPT': '0'})
            if completed.returncode or not valid(staged):
                return {**result, 'installation': 'not_downloaded',
                        'diagnostic': '获取失败，请检查网络和仓库访问权限；未输出凭据，继续本地素材或新创'}
            verification = subprocess.run([sys.executable, '-B', str(staged / 'tools/verify_catalog.py')],
                                           capture_output=True, timeout=120)
            if verification.returncode:
                return {**result, 'installation': 'not_installed', 'diagnostic': '资产库文件校验失败，保留原工作区并继续新创'}
            staged.rename(root)
        return {**report(workspace, root), 'read_only': False, 'installation': 'installed_and_verified'}
    except (OSError, subprocess.TimeoutExpired):
        return {**result, 'installation': 'not_downloaded', 'diagnostic': '获取或校验超时/失败；继续本地素材或新创'}


def author_id(workspace, series=None):
    from workbench_config import load_author_profile
    # Use the selected series author when present, never a brand constant.
    try:
        _, profile = load_author_profile(root=workspace, series_id=series)
        return profile.get('profile_id')
    except (OSError, ValueError, KeyError):
        return None


def query(workspace, *, explicit=None, text=None, kind=None, scope=None, series=None, include_author_assets=False,
          include_reference=False):
    status = report(workspace, explicit)
    result = {**status, 'schema': 'med_autocast_asset_query/v1', 'library': 'external', 'count': 0, 'assets': []}
    if status['status'] != 'available':
        return result
    root = Path(status['repo'])
    command = [sys.executable, '-B', str(root / 'tools/query_assets.py'), '--json']
    for flag, value in [('--query', text), ('--kind', kind), ('--scope', scope), ('--series', series),
                        ('--author-id', author_id(workspace, series))]:
        if value:
            command.extend([flag, value])
    if include_author_assets:
        command.append('--include-author-assets')
    if include_reference:
        command.append('--include-reference')
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if completed.returncode:
            raise ValueError('query_failed')
        rows = json.loads(completed.stdout)
        if not isinstance(rows, list):
            raise ValueError('invalid_query_output')
        # Old companion queries may not filter authors: apply the owner boundary here too.
        selected_author = author_id(workspace, series)
        rows = [row for row in rows if include_author_assets or (row.get('reuse_scope') or {}).get('kind') != 'author'
                or row['reuse_scope'].get('id') == selected_author]
        if not include_reference and kind != 'reference_frame':
            rows = [row for row in rows if row.get('review_boundary', {}).get('admission') != 'reference_only'
                    and row.get('curation', {}).get('status') not in {'needs_rebuild', 'superseded'}]
        for row in rows:
            row['resolved_payloads'] = [{'role': item.get('role'), 'path': str(confined(root, item['path'])),
                                        'exists': confined(root, item['path']).is_file()} for item in row.get('payload', [])]
        result.update(assets=rows, count=len(rows))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        result.update(status='diagnostic', diagnostic=type(error).__name__)
    return result


def confined(root, ref):
    path = (root / ref).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('素材路径越界')
    return path


def use(workspace, project, identifier, explicit=None, asset_id=None):
    workspace = workspace.resolve()
    from animation_library import archive, read, reuse, digest
    status = report(workspace, explicit)
    result = {'status': 'not_imported', 'blocks_production': False, 'note': NOTE}
    if status['status'] != 'available':
        return {**result, 'quality_debt': ['资产库不可用，可继续本地素材或新创']}
    root = Path(status['repo'])
    rows = [json.loads(line) for line in (root / 'catalog/assets.jsonl').read_text().splitlines() if line.strip()]
    reference_catalog = root / 'catalog/reference-assets.jsonl'
    if reference_catalog.is_file():
        rows.extend(json.loads(line) for line in reference_catalog.read_text().splitlines() if line.strip())
    row = next((item for item in rows if item['id'] == identifier), None)
    if not row:
        return {**result, 'quality_debt': ['未找到所选精确资产 ID，可重新检索或新创']}
    if row.get('kind') == 'reference_frame' or row.get('review_boundary', {}).get('admission') == 'reference_only':
        return {**result, 'quality_debt': ['静态参考只能参考构图，不能作为可运动纸件导入'], 'asset': row}
    if row.get('curation', {}).get('status') in {'needs_rebuild', 'superseded'}:
        return {**result, 'quality_debt': [row['curation'].get('reason', '该版本退出推荐，请使用替代部件或新创')], 'asset': row}
    record_ref = row.get('portable_record')
    if not record_ref:
        return {**result, 'quality_debt': ['该版本缺少独立原记录，请更新库或先作为参考查看']}
    record_path = confined(root, record_ref)
    if row.get('portable_record_sha256') and digest(record_path) != row['portable_record_sha256']:
        raise ValueError('资产原记录字节已变化')
    record = read(record_path)
    selected = read(confined(workspace, project) / 'project.json')
    scope = record.get('reuse_scope') or {}
    if scope.get('kind') == 'author' and scope.get('id') != author_id(workspace, selected['series_id']):
        return {**result, 'quality_debt': ['作者身份与资产复用范围不一致，请换用通用资产或新创']}
    if record['id'] != row['source_id'] or record['revision'] != row['revision']:
        raise ValueError('外库原记录与索引身份不一致')
    files = []
    for item in record['files']:
        matches = [part for part in row['payload'] if part['path'].endswith('/' + item['path'])]
        if len(matches) != 1:
            raise ValueError('缺少精确载荷映射')
        source = confined(root, matches[0]['path'])
        if digest(source) != item['sha256'] or item['sha256'] != matches[0]['sha256']:
            raise ValueError('载荷字节与所选版本不一致')
        files.append({'source': str(source), 'path': item['path'], 'role': item.get('role', 'payload')})
    local = workspace / 'assets/paper-theatre'
    archived = archive(local, record, files)
    if archived['revision'] != record['revision']:
        raise ValueError('独立原记录无法重建原版本，不冒充原资产')
    imported = reuse(workspace, local, project, record['id'], record['revision'], asset_id)
    # Preserve external lineage next to the project's copied original record.
    if imported['status'] == 'copied_and_verified':
        provenance = Path(imported['directory']) / 'external-source.json'
        provenance.write_text(json.dumps({'package_id': 'mac-media-assets', 'asset_id': row['id'],
                                          'revision': row['revision'], 'repository': REPOSITORY,
                                          'original_review_boundary': row.get('review_boundary'),
                                          'current_shot_review': 'pending'}, ensure_ascii=False, indent=2) + '\n')
    return {**imported, 'external_asset_id': identifier, 'blocks_production': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'ensure', 'query', 'use'])
    parser.add_argument('--workspace', type=Path, default=Path(os.environ.get('MED_AUTOCAST_WORKSPACE_ROOT', '.')))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--offline', action='store_true')
    for name in ['query', 'kind', 'scope', 'series', 'id', 'project', 'asset-id']:
        parser.add_argument('--' + name)
    parser.add_argument('--include-author-assets', action='store_true')
    parser.add_argument('--include-reference', action='store_true')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    try:
        if args.action == 'ensure':
            result = ensure(workspace, args.root, offline=args.offline)
        elif args.action == 'query':
            result = query(workspace, explicit=args.root, text=args.query, kind=args.kind,
                           scope=args.scope, series=args.series, include_author_assets=args.include_author_assets,
                           include_reference=args.include_reference)
        elif args.action == 'use':
            if not args.id or not args.project:
                parser.error('use 需要 --id 精确版本ID和 --project 工作区内单集路径')
            result = use(workspace, args.project, args.id, args.root, args.asset_id)
        else:
            result = report(workspace, args.root)
    except (OSError, ValueError, KeyError, yaml.YAMLError) as error:
        result = {'status': 'diagnostic', 'diagnostic': str(error), 'blocks_production': False,
                  'quality_debt': ['资产取用未完成，请检查所选版本或使用其他素材'], 'note': NOTE}
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
