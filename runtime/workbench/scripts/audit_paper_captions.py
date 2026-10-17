#!/usr/bin/env python3
"""Audit current registered caption words and propose complete timing off-project."""

from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import yaml

from paper_captions import caption_audit, caption_text, complete_caption_proposal


def read(path: Path):
    return json.loads(path.read_text(encoding='utf-8'))


def save(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def digest(path: Path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def project_report(workspace: Path, series: str, episode: str, row: dict) -> dict:
    project = (workspace / row['project']).resolve()
    config = read(project / 'project.json')
    score_path = project / config.get('score', 'score.json')
    source_path = project / config.get('narration', 'preproduction/narration.json')
    receipt_path = project / 'audio/narration_beats.json'
    score, source, receipt = read(score_path), read(source_path), read(receipt_path)
    source_by_id = {b['id']: b for b in source.get('beats', [])}
    beats = [{**b, 'text': source_by_id.get(b['id'], b).get('text', '')} for b in receipt.get('beats', [])]
    audio_text_changes = [b['id'] for b in receipt.get('beats', [])
                          if caption_text(b.get('text', '')) != caption_text(source_by_id.get(b['id'], b).get('text', ''))]
    source_without_audio = sorted(set(source_by_id) - {b['id'] for b in receipt.get('beats', [])})
    audit = caption_audit(beats, score.get('cues', []), score.get('duration'))
    audit['source_beats_without_audio'] = source_without_audio
    if source_without_audio:
        audit['text_complete'] = False
    timing_path = project / 'audio/timing-receipt.json'
    timing = read(timing_path) if timing_path.is_file() else {}
    voice_sha = digest(project / config['voice'])
    known_timing = timing.get('voice_sha256') == voice_sha and (
        timing.get('caption_status') == 'editorial_timing'
        or (timing.get('caption_proposal') or {}).get('schema') == 'paper_caption_timing/v2')
    proposal, repair = complete_caption_proposal(beats, score.get('cues', []), preserve_timing=known_timing)
    repair['source_beats_without_audio'] = source_without_audio
    repair['complete_text_check']['source_beats_without_audio'] = source_without_audio
    if source_without_audio:
        repair['complete_text_check']['text_complete'] = False
    affected = not audit['text_complete'] or bool(audit['timeline_issues']) or any(b['issues'] for b in audit['beats'])
    return {
        'series': series, 'episode': episode, 'project': str(project),
        'snapshot': {'score_sha256': digest(score_path), 'narration_sha256': digest(source_path),
                     'narration_receipt_sha256': digest(receipt_path)},
        'current_audit': audit, 'audio_text_changes_need_regeneration': audio_text_changes,
        'source_beats_without_audio': source_without_audio,
        'status': 'audio_regeneration_required' if audio_text_changes or source_without_audio else
                  'caption_repair_proposed' if affected else 'text_complete_timing_review_required',
        'proposal': {'voice_sha256': voice_sha, 'cues': proposal,
                     'source_beats_without_audio': source_without_audio,
                     'text_complete': repair['complete_text_check']['text_complete']},
        'repair': repair,
        'next_actions': (
            ['regenerate_changed_audio', 'retime_complete_captions', 'calibrate_phrase_timing', 'build_mix_render', 'current_readback']
            if audio_text_changes or source_without_audio
            else ['retime_complete_captions', 'calibrate_phrase_timing', 'build_mix_render', 'current_readback'] if affected
            else ['continuous_caption_review']
        ),
        'release_eligible': False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--series')
    parser.add_argument('--episode')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    output = args.output.resolve()
    registry = yaml.safe_load((workspace / 'workbench.yaml').read_text(encoding='utf-8')) or {}
    detail, failures = [], []
    for series, spec in (registry.get('series') or {}).items():
        if args.series and series != args.series:
            continue
        for episode, row in (spec.get('episodes') or {}).items():
            if not row.get('project') or (args.episode and episode != args.episode):
                continue
            try:
                report = project_report(workspace, series, episode, row)
                save(output / series / episode / 'caption-audit.json', report)
                save(output / series / episode / 'cues.proposed.json', report['proposal'])
                detail.append({k: report[k] for k in ('series', 'episode', 'project', 'status', 'snapshot', 'next_actions')})
                detail[-1].update(
                    text_complete=report['current_audit']['text_complete'],
                    affected_beats=[b['beat_id'] for b in report['current_audit']['beats'] if b['issues']],
                )
            except (OSError, KeyError, ValueError, TypeError) as error:
                failures.append({'series': series, 'episode': episode, 'error': str(error)})
    summary = {'schema': 'paper_caption_audit/v1', 'episodes': len(detail),
               'text_incomplete': sum(not d['text_complete'] for d in detail),
               'episodes_with_review_windows': sum(bool(d['affected_beats']) for d in detail),
               'read_errors': failures, 'detail': detail,
               'writes_actual_score': False, 'phrase_alignment': 'draft_review_required',
               'note': 'Registered current projects only; proposals do not mutate production or approve hearing/medical meaning.'}
    save(output / 'summary.json', summary)
    lines = ['# 当前纸剧场字幕正文与时间窗口检查', '',
             f"已检查 {len(detail)} 集；正文不完整 {summary['text_incomplete']} 集；有待复核窗口 {summary['episodes_with_review_windows']} 集。",
             '只读当前工程；提案保存在本目录，没有改写实际 Score。时间按真实声段窗口生成，句级同期仍需结合原音校准。', '',
             '| 系列 | 单集 | 正文 | 需看窗口 | 下一步 |', '| --- | --- | --- | --- | --- |']
    lines += [f"| {d['series']} | {d['episode']} | {'完整' if d['text_complete'] else '缺失/不一致'} | {','.join(d['affected_beats']) or '—'} | {'、'.join(d['next_actions'])} |" for d in detail]
    (output / '字幕修复定位与计划.md').write_text('\n'.join(lines) + '\n', encoding='utf-8')
    print(json.dumps({k: summary[k] for k in ('episodes', 'text_incomplete', 'episodes_with_review_windows', 'read_errors', 'writes_actual_score')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
