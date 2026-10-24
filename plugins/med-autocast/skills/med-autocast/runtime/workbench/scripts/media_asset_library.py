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
import tomllib

import yaml

REPOSITORY = 'https://github.com/gaofeng21cn/mac-media-assets.git'
NOTE = '资产库提供可选起点；按当前故事适配、替换或新创，未完成当前镜头审查。'


def native_companion_roots(carrier_home: Path):
    """Read installed membership plus its current marketplace source, never caches."""
    config_path = carrier_home / 'config.toml'
    if not config_path.is_file():
        return []
    try:
        config = tomllib.loads(config_path.read_text())
        selector = 'mac-media-assets@mac-media-assets'
        if selector not in config.get('plugins', {}):
            return []
        marketplace = config.get('marketplaces', {}).get('mac-media-assets') or {}
        if marketplace.get('source_type') == 'local':
            root = Path(marketplace['source']).expanduser().resolve()
        else:
            root = (carrier_home / '.tmp/marketplaces/mac-media-assets').resolve()
        descriptor = json.loads((root / '.agents/plugins/marketplace.json').read_text())
        if descriptor.get('name') != 'mac-media-assets':
            return []
        candidates = []
        for plugin in descriptor.get('plugins', []):
            source = plugin.get('source') or {}
            if plugin.get('name') != 'mac-media-assets' or source.get('source') != 'local':
                continue
            reference = Path(source.get('path', '.'))
            if reference.is_absolute():
                continue
            path = (root / reference).resolve()
            if path.is_relative_to(root):
                candidates.append(path)
        return candidates
    except (OSError, ValueError, KeyError, TypeError, tomllib.TOMLDecodeError):
        return []


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
    state = Path(os.environ.get('OPL_STATE_DIR') or
                 (Path(os.environ['OPL_DATA_DIR']) / 'opl/state' if os.environ.get('OPL_DATA_DIR') else
                  Path.home() / 'Library/Application Support/OPL/state')).expanduser()
    # Framework installs headless capabilities in its internal native carrier.
    # Inspect both supported native cache homes; no download or state mutation.
    # Native local-source installs resolve the marketplace checkout directly.
    # An older Framework projection may remain beside it after an update.
    for carrier_home in [state / 'internal-package-carrier', codex]:
        candidates.extend(native_companion_roots(carrier_home))
    candidates.append(state / 'internal-package-carrier/.tmp/marketplaces/mac-media-assets')
    candidates.append(state / 'codex-plugin-marketplaces/mac-media-assets/plugins/mac-media-assets')
    for cache in [state / 'internal-package-carrier/plugins/cache/mac-media-assets',
                  codex / 'plugins/cache/mac-media-assets']:
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
            result.update(status='available', asset_count=len({row.get('source_id', row['id']) for row in rows}),
                          registered_versions=len(rows), payload_files=sum(len(row.get('payload', [])) for row in rows),
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


def clinician_author_policy(workspace, series=None):
    from workbench_config import load_author_profile
    try:
        _, profile = load_author_profile(root=workspace, series_id=series)
    except (OSError, ValueError, KeyError):
        return None
    identity = profile.get('visual_identity') or {}
    library = identity.get('character_library') or {}
    return (profile, identity, library) if identity.get('enabled') and library.get('default_for_clinician') else None


def clinician_role(record):
    discovery = record.get('discovery') or {}
    role = discovery.get('character_role')
    if role:
        return role if role in {'clinician', 'clinician_man', 'clinician_woman'} else None
    values = [record.get('id'), record.get('title'), record.get('source_id'),
              *(record.get('tags') or []), *((discovery.get('aliases') or []))]
    text = ' '.join(str(value) for value in values if value).casefold()
    if any(value in text for value in ('clinician_woman', 'female doctor', '女医生', '女性医生')):
        return 'clinician_woman'
    if any(value in text for value in ('clinician_man', 'male doctor', '男医生', '男性医生')):
        return 'clinician_man'
    if any(value in text for value in ('clinician', 'physician', 'doctor', '医师', '医生')):
        return 'clinician'
    return None


def clinician_pose_from_request(*values):
    text = ' '.join(str(value) for value in values if value).casefold()
    for terms, pose in [
        (('handoff_action', '连续递接报告', '递接全过程'), 'handoff_action'),
        (('sit_cycle', '坐站过渡', '坐下起身'), 'sit_cycle'),
        (('walk_cycle', '连续步态', '走上前'), 'walk_cycle'),
        (('handoff_report', '递接报告', '递交报告'), 'handoff_report'),
        (('pointing', 'point', '指向', '指认'), 'pointing'),
        (('seated', 'sit', '坐姿', '问诊'), 'seated_consult'),
        (('walk', '步行', '行走'), 'walk'),
        (('reach', '接取', '伸手', '递接'), 'reach'),
        (('stand', '站姿', '站立'), 'stand_explain'),
    ]:
        if any(term in text for term in terms):
            return pose
    return None


def author_character_query(workspace, profile, identity, library, *, pose=None, identifier=None):
    if identifier and not identifier.startswith(f"author:{profile['profile_id']}/"):
        raise ValueError('作者人物素材与当前系列作者不一致')
    root = confined(workspace, library['root'])
    index = json.loads(confined(root, library.get('poses', 'poses.json')).read_text())
    pose_aliases = {'站立':'stand_explain','站立讲解':'stand_explain','stand':'stand_explain',
                    '连续步态':'walk_cycle','走上前':'walk_cycle',
                    '坐下起身':'sit_cycle','坐站过渡':'sit_cycle',
                    '连续递接报告':'handoff_action','递接全过程':'handoff_action',
                    '坐姿':'seated_consult','问诊':'seated_consult','坐姿问诊':'seated_consult','seated':'seated_consult',
                    '步行':'walk','行走':'walk','伸手':'reach','接取':'reach','递接':'reach','伸手或接取':'reach',
                    '指向':'pointing','指认':'pointing',
                    '递接报告':'handoff_report','递交报告':'handoff_report','给患者资料':'handoff_report'}
    selected_pose = pose_aliases.get(pose, pose)
    assets = []
    for pose_id, item in (index.get('poses') or {}).items():
        if selected_pose and selected_pose != pose_id:
            continue
        record_path = confined(root, item['record'])
        record = json.loads(record_path.read_text())
        if record.get('id') != item['id'] or record.get('revision') != item['revision']:
            raise ValueError('作者姿态索引与原记录不一致')
        if record.get('reuse_scope') != {'kind':'author','id':profile.get('profile_id')}:
            raise ValueError('作者人物范围不匹配')
        if identifier and identifier != f"author:{profile['profile_id']}/{record['id']}@{record['revision']}":
            continue
        assets.append({'id':f"author:{profile['profile_id']}/{record['id']}@{record['revision']}",
                       'source_id':record['id'],'revision':record['revision'],'pose':pose_id,
                       'title':record.get('title'),'kind':record.get('kind'),'reuse_scope':record['reuse_scope'],
                       'registration':record.get('registration'),'content_bounds':record.get('content_bounds'),
                       'human_scale':record.get('human_scale'),
                       'resolved_payloads':[{'role':part.get('role'),
                                             'path':str(confined(record_path.parent,part['path'])),
                                             'exists':confined(record_path.parent,part['path']).is_file()}
                                            for part in record.get('files',[])],
                       'review_boundary':record.get('review')})
    return {'schema':'med_autocast_asset_query/v1','library':'author_private',
            'status':'available' if assets else 'needs_author_pose','read_only':True,
            'author_id':profile.get('profile_id'),'identity_reference':str(confined(workspace,identity['character_reference'])),
            'count':len(assets),'assets':assets,'blocks_production':False,
            'quality_debt':[] if assets else ['作者姿态尚缺；沿当前作者母版补齐，不回退通用医生。'],
            'note':'本机作者档案启用 default_for_clinician 时，所有医生角色默认使用当前作者形象。'}


def clinician_request(*values):
    text = ' '.join(str(value) for value in values if value).casefold()
    return any(term in text for term in ('clinician', 'physician', 'doctor', '医生', '医师',
                                         'clinician_man', 'clinician_woman', '男医生', '女医生',
                                         '男性医生', '女性医生'))


def query(workspace, *, explicit=None, text=None, kind=None, scope=None, series=None, include_author_assets=False,
          include_reference=False, category=None, action=None, story_role=None, medium=None, collection=None,
          maturity=None, limit=None, character_role=None, pose=None, asset_id=None, all_versions=False,
          character_context=None):
    policy = clinician_author_policy(workspace, series)
    if policy and (character_role or text or asset_id or character_context == 'generic'):
        profile, identity, library = policy
        requested = str(character_role or text or '').replace(' ', '').casefold()
        aliases = {str(value).replace(' ', '').casefold() for value in library.get('request_aliases', [])}
        aliases.update({'医生','男医生','男性医生','女医生','女性医生','主讲医生','讲解医生','作者医生',
                        'doctor','physician','clinician','clinician_man','clinician_woman','male doctor','female doctor','presenter',
                        str(profile.get('profile_id','')).casefold(), str(profile.get('display_name','')).replace(' ','').casefold()})
        if (requested in aliases or clinician_request(character_role, text, asset_id)
                or character_context == 'generic'
                or str(asset_id or '').startswith(f"author:{profile.get('profile_id')}/")):
            return author_character_query(workspace, profile, identity, library,
                                          pose=pose or clinician_pose_from_request(character_role, text, asset_id),
                                          identifier=asset_id if str(asset_id or '').startswith('author:') else None)
    status = report(workspace, explicit)
    result = {**status, 'schema': 'med_autocast_asset_query/v1', 'library': 'external', 'count': 0, 'assets': []}
    if status['status'] != 'available':
        return result
    root = Path(status['repo'])
    command = [sys.executable, '-B', str(root / 'tools/query_assets.py'), '--json']
    for flag, value in [('--query', text), ('--kind', kind), ('--scope', scope), ('--series', series),
                        ('--author-id', author_id(workspace, series)), ('--category', category),
                        ('--action', action), ('--story-role', story_role), ('--medium', medium),
                        ('--collection', collection), ('--maturity', maturity), ('--limit', limit),
                        ('--character-role', character_role), ('--pose', pose), ('--id', asset_id)]:
        if value:
            command.extend([flag, str(value)])
    if include_author_assets:
        command.append('--include-author-assets')
    if include_reference:
        command.append('--include-reference')
    if all_versions:
        command.append('--all-versions')
    try:
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if completed.returncode:
            raise ValueError('query_failed')
        rows = json.loads(completed.stdout)
        if not isinstance(rows, list):
            raise ValueError('invalid_query_output')
        policy = clinician_author_policy(workspace, series)
        clinician_rows = [row for row in rows if clinician_role(row)] if policy else []
        if clinician_rows and (asset_id or character_role or text or character_context == 'generic'):
            profile, identity, library = policy
            requested_pose = pose or clinician_pose_from_request(
                character_role, text, asset_id,
                *(value for row in clinician_rows for value in
                  [row.get('id'), row.get('source_id'), row.get('title')]),
            )
            return author_character_query(workspace, profile, identity, library,
                                          pose=requested_pose)
        if policy:
            rows = [row for row in rows if not clinician_role(row)]
        # Old companion queries may not filter authors: apply the owner boundary here too.
        selected_author = author_id(workspace, series)
        rows = [row for row in rows if include_author_assets
                or (row.get('reuse_scope') or {}).get('kind') != 'author'
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


def collections(workspace, explicit=None):
    status = report(workspace, explicit)
    result = {**status, 'assemblies': [], 'event_kits': [], 'audio': [], 'blocks_production': False}
    if status['status'] != 'available':
        return result
    root = Path(status['repo'])
    for path, key, field in [('assemblies.json', 'assemblies', 'assemblies'),
                             ('event-kits.json', 'event_kits', 'kits'), ('audio.json', 'audio', 'assets')]:
        source = root / 'collections' / path
        if source.is_file():
            try:
                result[key] = json.loads(source.read_text()).get(field, [])
            except (OSError, ValueError):
                result.setdefault('quality_debt', []).append('集合登记不可读：' + path)
    return result


def character_coverage(workspace, explicit=None):
    status = report(workspace, explicit)
    result = {**status, "schema": "med_autocast_character_coverage/v1",
              "roles": [], "missing": [], "blocks_production": False}
    if status["status"] != "available":
        return result
    root = Path(status["repo"])
    try:
        command = [sys.executable, "-B", str(root / "tools/audit_character_coverage.py")]
        completed = subprocess.run(command, capture_output=True, text=True, timeout=30)
        if completed.returncode:
            raise ValueError("coverage_audit_failed")
        result.update(json.loads(completed.stdout))
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        result.update(status="diagnostic", diagnostic=type(error).__name__)
    return result


def use_collection(workspace, project, identifier, explicit=None):
    inventory = collections(workspace, explicit)
    selected = next((item for item in inventory['assemblies'] + inventory['event_kits']
                     if item['id'] == identifier), None)
    result = {'status': 'not_imported', 'collection': identifier, 'imports': [],
              'quality_debt': [], 'blocks_production': False}
    if not selected:
        result['quality_debt'].append('未找到组合，可继续选单件或新创')
        return result
    for part in selected.get('parts', []):
        try:
            item = use(workspace, project, part['asset_id'], explicit)
            result['imports'].append(item)
            if item.get('status') != 'copied_and_verified':
                result['quality_debt'].extend(item.get('quality_debt', ['部件未导入']))
        except (OSError, ValueError, KeyError) as error:
            result['quality_debt'].append({'asset_id': part.get('asset_id'), 'diagnostic': type(error).__name__})
    copied = [item for item in result['imports'] if item.get('status') == 'copied_and_verified']
    if copied:
        directory = confined(workspace, project) / 'library-collections'
        directory.mkdir(parents=True, exist_ok=True)
        safe_name = selected['id'].replace('/', '_').replace('\\', '_')
        receipt = directory / (safe_name + '.json')
        receipt.write_text(json.dumps({'collection': selected, 'imports': copied,
                                      'current_shot_review': 'pending', 'locks_story': False},
                                     ensure_ascii=False, indent=2) + '\n')
        result.update(status='copied_with_debt' if result['quality_debt'] else 'copied_and_verified',
                      receipt=str(receipt))
    return result


def confined(root, ref):
    path = (root / ref).resolve()
    if not path.is_relative_to(root.resolve()) or path == root.resolve():
        raise ValueError('素材路径越界')
    return path


def motion_registration_readback(record, directory):
    """Read motion metadata itself; image-manifest checks cannot cover a code package."""
    copied = json.loads((directory / 'library-record.json').read_text())
    reference = (record.get('registration') or {}).get('frames_ref')
    sequence = confined(directory, reference) if reference else None
    preserved = copied.get('registration') == record.get('registration') and sequence is not None and sequence.is_file()
    status = 'preserved' if preserved else 'diagnostic'
    return {'registration_readback': {'status': status, 'scope': 'motion_package_registration',
                                      'checked_files': [reference] if reference else [],
                                      'checked_assets': [], 'mismatches': [] if preserved else ['motion_registration']},
            'motion_recipe_readback': {'sequence': str(sequence) if sequence else None,
                                      'status': status, 'current_shot': 'pending'}}


def use(workspace, project, identifier, explicit=None, asset_id=None):
    workspace = workspace.resolve()
    from animation_library import archive, read, reuse, digest
    if identifier.startswith('author:'):
        project_path = confined(workspace, project)
        config = read(project_path / 'project.json')
        policy = clinician_author_policy(workspace, config.get('series_id'))
        if not policy:
            raise ValueError('当前系列未配置作者人物素材')
        profile, identity, library = policy
        prefix = f"author:{profile['profile_id']}/"
        if not identifier.startswith(prefix):
            raise ValueError('作者人物素材与当前系列作者不一致')
        source_id, revision = identifier[len(prefix):].rsplit('@', 1)
        imported = reuse(workspace, confined(workspace, library['root']), project_path, source_id, revision, asset_id)
        if imported.get('status') == 'copied_and_verified':
            record = read(confined(workspace, library['root']) / 'entries' / source_id / revision / 'record.json')
            if record.get('kind') == 'motion_recipe':
                imported.update(motion_registration_readback(record, Path(imported['directory'])))
        return {**imported, 'author_asset_id': identifier, 'library': 'author_private', 'blocks_production': False}
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
    if clinician_role(record) and clinician_author_policy(workspace, selected.get('series_id')):
        profile = clinician_author_policy(workspace, selected.get('series_id'))[0]
        return {'status':'not_imported','blocks_production':False,'external_asset_id':identifier,
                'replacement':{'library':'author_private','author_id':profile.get('profile_id'),'query':'media_asset_library query --character-role 医生 --pose <姿态>'},
                'quality_debt':['当前作者档案指定作者医生形象；通用医生没有复制到本集。']}
    scope = record.get('reuse_scope') or {}
    if scope.get('kind') == 'author' and scope.get('id') != author_id(workspace, selected['series_id']):
        return {**result, 'quality_debt': ['作者身份与资产复用范围不一致，请换用通用资产或新创']}
    if record['id'] != row['source_id'] or record['revision'] != row['revision']:
        raise ValueError('外库原记录与索引身份不一致')
    files = []
    for item in record['files']:
        exact_suffix = '/' + row['source_id'] + '/' + row['revision'] + '/' + item['path']
        matches = [part for part in row['payload'] if part['path'].endswith(exact_suffix)]
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
        source_assets = record.get('asset_bundle') or [record.get('asset') or record]
        actual_assets = {}
        if imported.get('imported_assets') and any(item.get('registration') is not None for item in source_assets):
            manifest_path = confined(confined(workspace, project), selected.get('assets', 'asset_manifest.json'))
            actual_assets = {item['asset_id']: item for item in read(manifest_path).get('assets', [])}
        checked, mismatches = [], []
        for source_asset, target_asset in zip(source_assets, imported.get('imported_assets', [])):
            expected = source_asset.get('registration')
            if expected is None:
                continue
            target_id = target_asset['asset_id']
            actual = actual_assets.get(target_id, {}).get('registration')
            checked.append(target_id)
            if actual != expected:
                mismatches.append(target_id)
        imported['registration_readback'] = {
            'status': 'diagnostic' if mismatches else 'preserved' if checked else 'not_applicable',
            'checked_assets': checked, 'mismatches': mismatches,
            'note': '只核对原件连接点是否完整复制；当前镜头的接触、比例与姿态需另看。',
        }
        if mismatches:
            imported.setdefault('quality_debt', []).append('原件连接点未完整进入本集素材清单：' + ', '.join(mismatches))
        if record.get('kind') == 'motion_recipe':
            imported.update(motion_registration_readback(record, Path(imported['directory'])))
        scale_index = root / 'collections/character-scale.json'
        scale = read(scale_index).get('assets', {}).get(identifier) if scale_index.is_file() else None
        if scale:
            payload_hashes = {item['sha256'] for item in record['files'] if item['path'] == record['entry']}
            if scale.get('source_asset_id') != identifier or scale.get('source_sha256') not in payload_hashes:
                raise ValueError('人物尺度与所选精确素材版本不一致')
            manifest_path = confined(confined(workspace, project), selected.get('assets', 'asset_manifest.json'))
            manifest = read(manifest_path)
            target_ids = {item['asset_id'] for item in imported.get('imported_assets', [])}
            for item in manifest.get('assets', []):
                if item['asset_id'] in target_ids:
                    item['human_scale'] = scale
            from animation_library import write
            write(manifest_path, manifest)
            actual = read(manifest_path)
            imported['human_scale_readback'] = {
                'status': 'preserved' if all(item.get('human_scale') == scale for item in actual['assets'] if item['asset_id'] in target_ids) else 'diagnostic',
                'source_asset_id': identifier, 'calibration_status': (scale.get('calibration') or {}).get('status', 'pending'),
                'note': '精确版本的项目尺度注解；原始不可变素材包保持原字节。',
            }
        provenance = Path(imported['directory']) / 'external-source.json'
        provenance.write_text(json.dumps({'package_id': 'mac-media-assets', 'asset_id': row['id'],
                                          'revision': row['revision'], 'repository': REPOSITORY,
                                          'original_review_boundary': row.get('review_boundary'),
                                          'discovery': row.get('discovery'),
                                          'human_scale': scale,
                                          'current_shot_review': 'pending'}, ensure_ascii=False, indent=2) + '\n')
    return {**imported, 'external_asset_id': identifier, 'blocks_production': False}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['status', 'ensure', 'query', 'use', 'collections',
                                           'character-coverage', 'use-collection'])
    parser.add_argument('--workspace', type=Path, default=Path(os.environ.get('MED_AUTOCAST_WORKSPACE_ROOT', '.')))
    parser.add_argument('--root', type=Path)
    parser.add_argument('--offline', action='store_true')
    for name in ['query', 'kind', 'scope', 'series', 'id', 'asset-id', 'project', 'category', 'motion-action',
                 'story-role', 'medium', 'collection', 'maturity', 'character-role', 'pose']:
        parser.add_argument('--' + name)
    parser.add_argument('--character-context', choices=['generic'],
                        help='启用作者医生默认策略时仍解析到作者私有形象；未启用时限定为公共通用范围')
    parser.add_argument('--limit', type=int)
    parser.add_argument('--include-author-assets', action='store_true')
    parser.add_argument('--include-reference', action='store_true')
    parser.add_argument('--all-versions', action='store_true')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    try:
        if args.action == 'ensure':
            result = ensure(workspace, args.root, offline=args.offline)
        elif args.action == 'query':
            result = query(workspace, explicit=args.root, text=args.query, kind=args.kind,
                           scope=args.scope, series=args.series, include_author_assets=args.include_author_assets,
                           include_reference=args.include_reference, category=args.category, action=args.motion_action,
                           story_role=args.story_role, medium=args.medium, collection=args.collection,
                           maturity=args.maturity, limit=args.limit,
                           character_role=getattr(args, 'character_role'), pose=args.pose,
                           asset_id=args.id, all_versions=args.all_versions,
                           character_context=getattr(args, 'character_context', None))
        elif args.action == 'collections':
            result = collections(workspace, args.root)
        elif args.action == 'character-coverage':
            result = character_coverage(workspace, args.root)
        elif args.action == 'use-collection':
            result = use_collection(workspace, args.project, args.id, args.root)
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
