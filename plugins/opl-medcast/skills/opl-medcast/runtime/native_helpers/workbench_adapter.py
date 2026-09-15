"""Native Workbench contracts and explicit tool dispatch; no second scheduler."""
from __future__ import annotations

import filecmp
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import yaml

BUNDLE = Path(__file__).resolve().parents[1] / 'workbench'
TOOLS = {
    'workbench_config': ('read_only', '配置、作者覆盖、依赖和资产校验'),
    'media_backend': ('network_read', '后端解析和按需服务诊断；不生成媒体'),
    'render_series_tts': ('generate', '已审旁白配音与逐段回执'),
    'transcribe_series_whisper': ('write', 'ASR 辅助对齐；不覆盖审定医学文字'),
    'build_episode_timelines': ('write', '审定字幕、节拍和制作单'),
    'queue_h3_shots': ('generate', 'H3 提交、原任务轮询、官方提示直通'),
    'render_series_h3': ('generate', '按系列调用 H3 镜头队列'),
    'fetch_h3_receipt': ('download', '按原回执下载精确输出'),
    'build_episode_video': ('write', '唯一通用合成器：字幕、品牌、画布、混音'),
    'build_series_videos': ('write', '系列或指定单集合成与原动画合同'),
    'qa_series_videos': ('write', '技术 QA 与所选范围联系表'),
    'build_timeline_review': ('write', '同期画面、PCM、SRT、可选 ASR 联合定位'),
    'build_controlled_visuals': ('write', '确定性图示素材；仍须解释与视觉准入审查'),
    'build_handdrawn_pulse_animation': ('write', '手绘脉冲动画素材；不自动认定为合格成片'),
    'generate_gentle_bgm': ('write', '确定性无歌词背景音乐'),
    'package_review': ('write', '原制作单的单集审看包、双平台文案与字节回读'),
    'build_release_packages': ('write', '原正式 final 合同与双平台文案'),
    'build_keyframe_library': ('write', '已审目录校验及 HTML、CSV、缩略图投影'),
}


def tool_inventory(root: Path) -> dict:
    entries = []
    for name, (effect, purpose) in TOOLS.items():
        local = root / 'scripts' / (name + '.py')
        path = local if local.is_file() else BUNDLE / 'scripts' / (name + '.py')
        entries.append({'name': name, 'effect': effect, 'purpose': purpose,
                        'path': str(path), 'exists': path.is_file(),
                        'implementation': 'workspace' if path == local else 'package'})
    return {'read_only': True, 'tools': entries, 'production_ready': None}


def run_tool(root: Path, name: str, arguments: list[str], bundled=False) -> int:
    root = root.resolve()
    if name not in TOOLS:
        raise ValueError('未知工作台工具')
    local = root / 'scripts' / (name + '.py')
    script = BUNDLE / 'scripts' / (name + '.py') if bundled or not local.is_file() else local
    env = dict(os.environ, OPL_MEDCAST_WORKSPACE_ROOT=str(root),
               OPL_MEDCAST_HELPERS_ROOT=str(Path(__file__).resolve().parent),
               PYTHONDONTWRITEBYTECODE='1')
    # The caller selects the interpreter (core venv or a separate model environment).
    # Preserve workspace implementations and their sibling module imports.
    return subprocess.run([sys.executable, str(script), *arguments], cwd=root, env=env).returncode


def read_object(path: Path) -> dict:
    value = yaml.safe_load(path.read_text()) if path.suffix in ('.yaml', '.yml') else json.loads(path.read_text())
    if not isinstance(value, dict):
        raise ValueError(f'期望对象：{path.name}')
    return value


def preflight_native(root: Path, series: str, episode: str, plan_ref: str,
                     master_ref: str, delivery_ref=None, source_review_ref=None,
                     allowed_roots=()) -> dict:
    """Read original YAML/JSON in place. Preserve quality debt, never mint approval.

    plan/master are independent current-task selections, not inferred from mtime
    or the delivery being checked. No new selection/delivery JSON is required.
    """
    roots = [root.resolve(), *(Path(p).resolve() for p in allowed_roots)]

    def path(ref, base=root):
        if not isinstance(ref, (str, Path)) or not str(ref):
            raise ValueError('缺少精确文件引用')
        p = (base / ref).resolve()
        if not any(p.is_relative_to(r) for r in roots):
            raise ValueError('引用越出工作区；外部存储需显式 --allow-root')
        if not p.is_file():
            raise ValueError(f'引用文件不存在：{p}')
        return p

    config = read_object(path('workbench.yaml'))
    if config.get('schema') != 'medical_video_workbench/v2':
        raise ValueError('不支持的工作台合同')
    row = config.get('series', {}).get(series)
    if not row or not episode or Path(episode).name != episode or episode in ('.', '..'):
        raise ValueError('未知系列或无效集号')
    episode_root = (root / row['production_root'] / episode).resolve()
    plan_path, master = path(plan_ref), path(master_ref)
    plan = read_object(plan_path)
    if plan.get('schema') not in ('video_production_plan/v2', 'video_production_plan/v3'):
        raise ValueError('不支持的制作单合同')
    if plan.get('episode_id') != episode:
        raise ValueError('制作单集号不一致')
    audio = path(plan.get('audio', {}).get('source'), episode_root)
    srt = path(plan.get('subtitles', {}).get('source'), episode_root)
    catalog_path = path(row['release_catalog'])
    catalog = read_object(catalog_path)
    if catalog.get('series_id') != series:
        raise ValueError('文案目录系列不一致')
    catalog_entries = [e for e in catalog.get('episodes', []) if e.get('id') == episode]
    if len(catalog_entries) != 1:
        raise ValueError('文案目录缺少本集或集号重复')
    debt, checked = [], []
    reviews = read_object(path(source_review_ref)) if source_review_ref else {}
    # Native source-review files may use either a direct ID map or a shots map.
    reviews = reviews.get('shots', reviews)
    if not isinstance(reviews, dict):
        raise ValueError('源片审查记录必须为对象')
    timeline = plan.get('visual_timeline')
    if not isinstance(timeline, list) or not timeline:
        raise ValueError('制作单缺少实际时间轴')
    previous = 0.0
    for segment in timeline:
        start, end = float(segment['start']), float(segment['end'])
        begin = float(segment.get('source_start', 0))
        finish = float(segment.get('source_end', begin + end - start))
        if not all(math.isfinite(v) for v in (start, end, begin, finish)) or abs(start-previous) > .002 or end <= start or begin < 0 or finish <= begin:
            raise ValueError('镜头时间轴或源区间无效')
        previous = end
        source = path(segment['source'], episode_root / 'candidates')
        sid = segment.get('source_id') or segment.get('diversity_scene')
        record = reviews.get(sid, {}) if sid else {}
        candidates = [record]
        for ref in (plan.get('source_review'), segment.get('source_review')):
            if ref:
                linked = read_object(path(ref))
                linked = linked.get('shots', linked)
                if not isinstance(linked, dict):raise ValueError('源片审查记录必须为对象')
                candidates.extend(v for key, v in linked.items() if key == sid or (
                    isinstance(v, dict) and (v.get('source_ref') or v.get('source') or v.get('path'))
                    and path(v.get('source_ref') or v.get('source') or v.get('path')) == source))
        # Explicit path mappings also apply when an older plan has no source ID.
        candidates.extend(v for v in reviews.values() if isinstance(v, dict) and
                          (v.get('source_ref') or v.get('source') or v.get('path')) and
                          path(v.get('source_ref') or v.get('source') or v.get('path')) == source)
        if any(not isinstance(v, dict) for v in candidates):raise ValueError('无效源片审查项')
        if any(v.get('accepted') is False for v in candidates):
            raise ValueError(f'制作单使用已拒绝的源片：{sid or source.name}')
        bound_records = [v for v in candidates if v.get('source_ref') or v.get('source') or v.get('path')]
        if bound_records:record=bound_records[-1]
        if record.get('accepted') is False:
            raise ValueError(f'制作单使用已拒绝的源片：{sid}')
        # A name/ID alone cannot bind a review to media bytes or even its path.
        bound = record.get('source_ref') or record.get('source') or record.get('path')
        if bound and path(bound) != source:
            raise ValueError(f'源片审查与实际文件不一致：{sid}')
        if record.get('accepted') is True and bound:
            lo, hi = map(float, record['usable_range'])
            if not all(math.isfinite(v) for v in (lo, hi)) or not 0 <= lo < hi or begin < lo-.002 or finish > hi+.002:
                raise ValueError(f'源区间超出批准范围：{sid}')
        else:
            debt.append({'segment': segment['segment_id'], 'review': 'source_admission',
                         'status': 'needs_evidence', 'reason': '需按原回执和视觉记录核对；不由名称猜测批准'})
        checked.append({'segment_id': segment['segment_id'], 'source': str(source), 'source_range': [begin, finish]})
    expected_duration = plan.get('audio', {}).get('duration_seconds')
    if expected_duration is not None and (not math.isfinite(float(expected_duration)) or abs(previous-float(expected_duration)) > .3):
        raise ValueError('时间轴与登记音轨时长不一致')
    delivery_path = path(delivery_ref or str(Path(row['publish_root']) / 'manifest.json'))
    delivery = read_object(delivery_path)
    if delivery.get('schema') not in ('medical_video_review_package/v1', 'medical_video_series_delivery/v2') or delivery.get('series_id') != series:
        raise ValueError('不支持的交付合同或系列不一致')
    entries = [e for e in delivery.get('episodes', []) if (e.get('id') or e.get('episode_id')) == episode]
    if len(entries) != 1:
        raise ValueError('交付清单缺少本集或集号重复')
    entry = entries[0]
    if entry.get('source') and path(entry['source']) != master:
        raise ValueError('交付清单来源不是当前选定母版')
    published = path(entry.get('video') or f'{episode}/video.mp4', delivery_path.parent)
    filecmp.clear_cache()
    if not filecmp.cmp(master, published, shallow=False):
        raise ValueError('交付视频与当前母版字节不一致')
    # Use the original formatter, so platform content stays single-source.
    import importlib.util
    scripts = str(BUNDLE / 'scripts')
    sys.path.insert(0, scripts)
    try:
        spec = importlib.util.spec_from_file_location('medcast_release_format', BUNDLE / 'scripts/build_release_packages.py')
        formatter = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(formatter)
        for platform, filename in [('xiaohongshu', '小红书文案.txt'), ('channels', '微信视频号文案.txt')]:
            if path(filename, published.parent).read_text(encoding='utf-8') != formatter.platform_text(catalog_entries[0], platform):
                raise ValueError(f'{filename} 与当前文案目录不一致')
    finally:
        sys.path.remove(scripts)
    path('发布交付包.md', published.parent)
    if (published.parent / '字幕.srt').is_file() and not filecmp.cmp(srt, path('字幕.srt', published.parent), shallow=False):
        raise ValueError('交付字幕与制作单不一致')
    review_path = published.parent / '审看记录.json'
    review = read_object(path(review_path)) if review_path.is_file() else {}
    for field, expected in [('production_plan', plan_path), ('video_source', master), ('audio_source', audio), ('srt_source', srt)]:
        if review.get(field) and path(review[field]) != expected:
            raise ValueError(f'审看记录 {field} 与当前输入不一致')
    if 'segments' in review and review['segments'] != timeline:
        # Review records may add annotations. Compare actual selected ranges only.
        signature = lambda segs: [(s['segment_id'], float(s['start']), float(s['end']), str(path(s['source'], episode_root/'candidates')), float(s.get('source_start', 0)), float(s.get('source_end', float(s.get('source_start', 0))+float(s['end'])-float(s['start'])))) for s in segs]
        if signature(review['segments']) != signature(timeline):
            raise ValueError('审看记录与当前制作单的镜头或区间不一致')
    if not review.get('production_plan') and 'segments' not in review:
        debt.append({'review':'current_plan_binding','status':'needs_evidence','reason':'需回读当前构建记录；母版字节一致不单独证明制作单被实际使用'})
    # Series summaries cannot approve a newly selected episode revision.
    claims = {key: review.get(key, 'pending') for key in ('technical_qa', 'sampled_semantic_review', 'full_motion_review', 'full_listening', 'medical_review')}
    return {'schema': 'opl_medcast_native_preflight/v1', 'status': 'passed', 'read_only': True,
            'series_id': series, 'episode_id': episode, 'plan': str(plan_path), 'master': str(master),
            'delivery': str(delivery_path), 'checked_shots': len(checked), 'sources': checked,
            'video_bytes_equal': True, 'platform_copy_equal': True, 'review_claims': claims,
            'series_review_summary': {key: delivery[key] for key in claims if key in delivery},
            'quality_debt': debt, 'domain_quality_approved': False, 'publication_authorized': False,
            'note': '原合同和交付字节一致；保留原复核声明，未重新审定证据、动态、听感或医学质量'}
