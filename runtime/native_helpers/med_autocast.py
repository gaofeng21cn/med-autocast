#!/usr/bin/env python3
"""Read-only Med Auto Cast workspace inspection and deterministic preflight.

These checks never authorize media quality, medical claims, publication or execution.
"""
from __future__ import annotations
import argparse
import json
import math
import sys
from pathlib import Path


class ContractError(ValueError):
    pass


def local_path(root: Path, ref: str, *, exists: bool = True) -> Path:
    if not isinstance(ref, str) or not ref.strip():
        raise ContractError('文件引用必须为非空字符串')
    path = (root / ref).resolve()
    if not path.is_relative_to(root.resolve()):
        raise ContractError('文件引用越出工作区')
    if exists and not path.is_file():
        raise ContractError(f'缺少文件：{ref}')
    return path


def mapping(path: Path, *, yaml_format: bool = False) -> dict:
    if yaml_format:
        try:
            import yaml
        except ImportError as exc:
            raise ContractError('需要 PyYAML；在独立环境安装本仓 pyproject.toml 的依赖') from exc
        data = yaml.safe_load(path.read_text())
    else:
        data = json.loads(path.read_text())
    if not isinstance(data, dict):
        raise ContractError(f'期望对象：{path.name}')
    return data


def inspect_workspace(root: Path) -> dict:
    config = mapping(local_path(root, 'workbench.yaml'), yaml_format=True)
    if config.get('schema') != 'medical_video_workbench/v2':
        raise ContractError('不支持的 workbench schema')
    profiles = config.get('active_profiles', {})
    profile_readback = {}
    for key in ('author', 'media_backends'):
        ref = profiles.get(key)
        local_path(root, ref)
        # Deliberately do not serialize profile body: it may contain secrets/endpoints.
        profile_readback[key] = {'ref': ref, 'exists': True}
    series = []
    for sid, item in config.get('series', {}).items():
        locations = {}
        for key in ('release_catalog', 'technical_qa', 'production_root', 'publish_root'):
            ref = item.get(key)
            if ref:
                p = local_path(root, ref, exists=False)
                locations[key] = {'ref': ref, 'exists': p.exists()}
        series.append({'series_id': sid, 'declared_status': item.get('status'), 'episode_count': item.get('episode_count'), 'locations': locations})
    scripts = {name: (root/'scripts'/name).is_file() for name in ('media_backend.py','workbench_config.py','build_release_packages.py','build_keyframe_library.py')}
    return {'schema': 'med_autocast_workspace_inspection/v1', 'read_only': True,
            'workspace_root': str(root.resolve()), 'profiles': profile_readback, 'series': series,
            'workbench_entrypoints': scripts,
            'keyframe_catalog_exists': (root/'assets/keyframes/catalog.json').is_file(),
            'production_ready': None, 'note': '仅配置与路径回读，未调用后端或批准任何媒体'}


def query_assets(root: Path, category: str | None = None, series: str | None = None) -> dict:
    catalog = mapping(local_path(root, 'assets/keyframes/catalog.json'))
    if catalog.get('schema') != 'medical_keyframe_library/v1':
        raise ContractError('不支持的关键帧 catalog schema')
    if category is not None and category not in catalog.get('categories', {}):
        raise ContractError('未知关键帧类别')
    if series is not None and series not in catalog.get('series', {}):
        raise ContractError('未知关键帧系列')
    base = local_path(root, catalog.get('asset_base', 'assets/keyframes'), exists=False)
    seen = set()
    assets = []
    for item in catalog.get('assets', []):
        aid = item.get('id')
        if not isinstance(aid,str) or not aid or aid in seen:
            raise ContractError('关键帧 ID 缺失或重复')
        seen.add(aid)
        if category and item.get('category') != category:
            continue
        if series and item.get('series_id') != series:
            continue
        file = local_path(base, item.get('file'))
        if item.get('admission', {}).get('decision') != 'reference_library_only':
            continue
        related_review = item.get('related_video_review') or {}
        video = related_review.get('snapshot') or {}
        assets.append({'id': aid, 'title': item.get('title'), 'category': item.get('category'),
                       'series_id': item.get('series_id'), 'file': str(file),
                       'purpose': item.get('purpose'), 'reuse_notes': item.get('reuse_notes', []),
                       'static_reference_only': True, 'related_video_rejected': video.get('accepted') is False,
                       'related_video_usable_range': None if video.get('accepted') is False else video.get('usable_range'),
                       'review_ref': related_review.get('path')})
    return {'schema': 'med_autocast_asset_query/v1', 'read_only': True, 'count': len(assets), 'assets': assets,
            'note': '仅静态参考检索；真实复用前看图和审核医学细节、人物及关联动态'}


def interval(value) -> tuple[float,float]:
    if not isinstance(value,list) or len(value)!=2:
        raise ContractError('区间必须为 [start,end]')
    if any(isinstance(x,bool) or not isinstance(x,(int,float)) or not math.isfinite(x) for x in value):
        raise ContractError('区间必须为有限数字')
    start,end=value
    if start<0 or end<=start:
        raise ContractError('区间必须满足 0 <= start < end')
    return start,end


def ids(values, label):
    if not isinstance(values,list) or not values or any(not isinstance(v,str) or not v for v in values):
        raise ContractError(f'{label}必须为非空字符串列表')
    if len(values)!=len(set(values)):
        raise ContractError(f'{label}存在重复集号')
    return values


REVIEW_GATES=('technical','visual','continuous_motion','listening','medical')


def preflight(root: Path, delivery_ref: str, current_ref: str, review_ref: str) -> dict:
    delivery=mapping(local_path(root,delivery_ref));current=mapping(local_path(root,current_ref));sources=mapping(local_path(root,review_ref))
    if delivery.get('schema')!='med_autocast_delivery/v1' or current.get('schema')!='med_autocast_current_selection/v1':
        raise ContractError('不支持的交付/当前制作单 schema')
    for key in ('series_id','revision'):
        if not isinstance(current.get(key),str) or not current[key] or delivery.get(key)!=current[key]:
            raise ContractError(f'交付与当前制作单 {key} 不一致')
    expected=ids(current.get('episode_ids'),'当前集号')
    episodes=delivery.get('episodes')
    if not isinstance(episodes,list) or any(not isinstance(e,dict) for e in episodes):
        raise ContractError('episodes 必须为对象列表')
    actual=ids([e.get('episode_id') for e in episodes],'交付集号')
    if set(actual)!=set(expected):
        raise ContractError('交付选集不等于当前期望清单')
    if delivery.get('intent') not in ('review','publication_candidate'):
        raise ContractError('交付 intent 必须为 review 或 publication_candidate')
    debt=[];checked_shots=0
    for episode in episodes:
        eid=episode['episode_id']
        for key in ('master_ref','narration_ref','subtitles_ref'):
            local_path(root,episode.get(key))
        # Bind current authority to exact selected master, not just a revision label.
        expected_master=current.get('master_refs',{}).get(eid)
        if not expected_master or local_path(root,expected_master)!=local_path(root,episode['master_ref']):
            raise ContractError(f'{eid} 母版与当前制作单不符')
        shots=episode.get('shots')
        if not isinstance(shots,list) or not shots:
            raise ContractError(f'{eid} 缺少实际时间轴镜头')
        for shot in shots:
            if not isinstance(shot,dict):raise ContractError('镜头必须为对象')
            source_id=shot.get('source_id');source=sources.get(source_id)
            if not isinstance(source,dict) or source.get('accepted') is not True:
                raise ContractError(f'{eid} 使用未批准或已拒用源：{source_id}')
            begin,end=interval(shot.get('source_range'));lower,upper=interval(source.get('usable_range'))
            if begin<lower or end>upper:raise ContractError(f'{eid} 区间超出已审可用范围：{source_id}')
            source_path=local_path(root,source.get('source_ref'))
            if local_path(root,shot.get('source_ref'))!=source_path:
                raise ContractError(f'{eid} 源 ID 与实际文件不一致')
            checked_shots+=1
        gates=episode.get('reviews',{})
        if not isinstance(gates,dict):raise ContractError('reviews必须为对象')
        for key in REVIEW_GATES:
            record=gates.get(key,{'status':'pending'})
            if not isinstance(record,dict) or record.get('status') not in ('passed','pending','failed','not_applicable'):
                raise ContractError(f'{eid} {key} 状态无效')
            state=record['status']
            if state=='passed':
                local_path(root,record.get('evidence_ref'))
                if record.get('artifact_ref')!=episode['master_ref']:
                    raise ContractError(f'{eid} {key} 审查证据未绑定当前母版')
            elif state=='not_applicable':
                # N/A cannot make the machine treat a missing review as approval.
                if not record.get('reason'):raise ContractError(f'{eid} {key} 不适用缺少理由')
                debt.append(f'{eid}:{key}:not_applicable_needs_owner_review')
            else:debt.append(f'{eid}:{key}:{state}')
    if delivery['intent']=='publication_candidate' and debt:
        raise ContractError('发布候选仍有未完成或未通过的复核')
    return {'schema':'med_autocast_preflight/v1','read_only':True,'status':'passed',
            'series_id':current['series_id'],'revision':current['revision'],'episode_ids':actual,
            'checked_shots':checked_shots,'quality_debt':debt,'domain_quality_approved':False,
            'publication_authorized':False,'uploaded':False,
            'note':'只证明引用、当前性和声明一致；未审查证据内容、审查者权限、真实动态或医学质量'}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('inspect','assets','preflight','tools','preflight-workbench'):
        p=sub.add_parser(name);p.add_argument('--workspace',type=Path,required=True)
        if name=='assets':p.add_argument('--category');p.add_argument('--series')
        if name=='preflight':
            p.add_argument('--delivery',required=True);p.add_argument('--current',required=True);p.add_argument('--source-review',required=True)
        if name=='preflight-workbench':
            p.add_argument('--series',required=True);p.add_argument('--episode',required=True)
            p.add_argument('--plan',required=True);p.add_argument('--master',required=True)
            p.add_argument('--delivery');p.add_argument('--source-review')
            p.add_argument('--allow-root',action='append',default=[])
    a=parser.parse_args()
    try:
        root=a.workspace.resolve()
        if not root.is_dir():raise ContractError('workspace 必须为现有目录')
        if a.command=='inspect':result=inspect_workspace(root)
        elif a.command=='assets':result=query_assets(root,a.category,a.series)
        elif a.command=='preflight':result=preflight(root,a.delivery,a.current,a.source_review)
        else:
            from workbench_adapter import tool_inventory, preflight_native
            if a.command=='tools':result=tool_inventory(root)
            else:result=preflight_native(root,a.series,a.episode,a.plan,a.master,a.delivery,a.source_review,a.allow_root)
        print(json.dumps(result,ensure_ascii=False,indent=2));return 0
    except (ValueError,OSError,TypeError,AttributeError,KeyError) as exc:
        print(json.dumps({'status':'blocked','error':str(exc)},ensure_ascii=False));return 2


if __name__=='__main__':raise SystemExit(main())
