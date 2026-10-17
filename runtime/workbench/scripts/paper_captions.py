#!/usr/bin/env python3
"""Complete paper-theatre caption proposals, bound to approved beats, not old cuts.

These helpers preserve words and diagnose time windows. Character-ratio timing
is a draft for review, never word alignment or proof of audible pronunciation.
"""

from __future__ import annotations

from copy import deepcopy
import difflib
import math
import re

from build_episode_timelines import split_units

IGNORED = re.compile(r'[\s，。；：、！？,!?;:、“”‘’（）()《》<>]+')
WORD_SPACE = '\ue000'


def caption_text(text: str) -> str:
    # Formatting punctuation may differ, but medical decimals, ranges and
    # English/numeric word boundaries must not disappear from comparison.
    text = re.sub(r'(?<=[A-Za-z0-9.])\s+(?=[A-Za-z0-9])', WORD_SPACE, str(text))
    text = re.sub(r'\.(?!\d)', '', text)
    return IGNORED.sub('', text).replace(WORD_SPACE, ' ').upper()


def split_caption_text(text: str) -> list[str]:
    # The legacy Chinese splitter removes whitespace. Protect meaningful word
    # spaces while keeping its existing editorial sentence-break behavior.
    text = re.sub(r'(?<=[A-Za-z0-9.])\s+(?=[A-Za-z0-9])', WORD_SPACE, text)
    return [unit.replace(WORD_SPACE, ' ') for unit in split_units(text, max_chars=30)]


def caption_rows_text(expected: str, rows: list[dict]) -> str:
    """Keep an approved word space when two cues break at that boundary.

    A cue boundary is a display break, so its trimmed edges may omit the word
    space. Only restore an exact whitespace gap between ordered matches in the
    approved text; missing words or spaces inside one cue stay real differences.
    """
    target = caption_text(expected)
    observed, cursor = '', 0
    for row in rows:
        text = caption_text(row.get('text', ''))
        position = target.find(text, cursor) if text else -1
        if position >= 0:
            gap = target[cursor:position]
            if gap and gap.isspace():
                observed += gap
            cursor = position + len(text)
        observed += text
    return observed


def cue_groups(beats: list[dict], cues: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Locate captions by spoken text order; timing never chooses their owner.

    Old retiming could drift a caption midpoint into another shot. Reusing that
    midpoint both changed ownership and discarded text after clamping. Explicit
    beat IDs win only when the caption actually belongs to that beat's text.
    Legacy captions are located in the complete text stream in narrative order.
    """
    groups = {beat['id']: [] for beat in beats}
    spans = []
    target = ''
    for beat in beats:
        text = caption_text(beat.get('text', ''))
        spans.append((len(target), len(target) + len(text), beat['id']))
        target += text
    cursor = 0
    unassigned = []
    for index, cue in enumerate(cues):
        text = caption_text(cue.get('text', ''))
        explicit = cue.get('beat_id')
        if explicit in groups and text and text in caption_text(next(b['text'] for b in beats if b['id'] == explicit)):
            groups[explicit].append(cue)
            pos = target.find(text, max(cursor, next(a for a, _, bid in spans if bid == explicit)))
            if pos >= 0:
                cursor = pos + len(text)
            continue
        pos = target.find(text, cursor) if text else -1
        owner = next((bid for left, right, bid in spans if left <= pos and pos + len(text) <= right), None)
        if pos < 0 or owner is None:
            unassigned.append({'cue_index': index, 'cue': cue, 'reason': 'text_not_in_ordered_approved_beat'})
        else:
            groups[owner].append(cue)
            cursor = pos + len(text)
    return groups, unassigned


def text_differences(expected: str, actual: str) -> list[dict]:
    expected, actual = caption_text(expected), caption_text(actual)
    changes = []
    for op, a, b, x, y in difflib.SequenceMatcher(None, expected, actual, autojunk=False).get_opcodes():
        if op != 'equal':
            changes.append({'kind': op, 'expected': expected[a:b], 'caption': actual[x:y],
                            'expected_offset': a, 'caption_offset': x})
    return changes


def caption_audit(beats: list[dict], cues: list[dict], duration: float | None = None) -> dict:
    groups, unassigned = cue_groups(beats, cues)
    details = []
    for beat in beats:
        rows = groups[beat['id']]
        expected = caption_text(beat.get('text', ''))
        observed = caption_rows_text(beat.get('text', ''), rows)
        start, end = float(beat['start']), float(beat['end'])
        issues = []
        if expected != observed:
            issues.append('approved_text_not_fully_captioned')
        opening_delay = float(rows[0]['start']) - start if rows else None
        if opening_delay is not None and opening_delay > .75:
            issues.append('opening_caption_late_review_window')
        for row in rows:
            a, b = float(row['start']), float(row['end'])
            if not (math.isfinite(a) and math.isfinite(b) and 0 <= a < b):
                issues.append('invalid_caption_window')
            if b <= start or a >= end:
                issues.append('caption_outside_own_narration_beat')
            elif a < start - .02 or b > end + .02:
                issues.append('caption_crosses_own_narration_boundary')
        details.append({
            'beat_id': beat['id'], 'approved_text': beat.get('text', ''),
            'caption_text': ''.join(str(row.get('text', '')) for row in rows),
            'text_complete': expected == observed, 'cue_count': len(rows),
            'beat_window': [start, end], 'opening_delay_seconds': opening_delay,
            'differences': text_differences(expected, observed),
            'issues': sorted(set(issues)),
        })
    timeline_issues = []
    prior_end = 0.
    for index, row in enumerate(cues):
        start, end = float(row['start']), float(row['end'])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            timeline_issues.append({'cue_index': index, 'code': 'invalid_caption_window'})
        if start < prior_end - .001:
            timeline_issues.append({'cue_index': index, 'code': 'overlap_or_out_of_order'})
        if duration is not None and end > duration + .01:
            timeline_issues.append({'cue_index': index, 'code': 'caption_after_film_end'})
        prior_end = end
    expected_all = caption_text(''.join(str(b.get('text', '')) for b in beats))
    actual_all = caption_rows_text(expected_all, cues)
    return {
        'text_complete': expected_all == actual_all and all(b['text_complete'] for b in details),
        'approved_caption_match_ratio': difflib.SequenceMatcher(None, expected_all, actual_all, autojunk=False).ratio(),
        'beats': details, 'unassigned_cues': unassigned, 'timeline_issues': timeline_issues,
        'audio_recognition_performed': False,
        'review_note': 'Text completeness and time-window diagnostics do not establish word alignment or audible delivery.',
    }


def _windows_valid(rows: list[dict], start: float, end: float, tolerance: float = .02) -> bool:
    previous = start - tolerance
    for row in rows:
        a, b = float(row['start']), float(row['end'])
        if not (math.isfinite(a) and math.isfinite(b) and previous <= a < b
                and start - tolerance <= a and b <= end + tolerance):
            return False
        previous = b
    return bool(rows)


def complete_caption_proposal(beats: list[dict], old_cues: list[dict], *, prior_beats: dict | None = None,
                              preserve_timing: bool = False) -> tuple[list[dict], dict]:
    """Retain complete editorial breaks, repair omissions from the full text.

    Each beat gets its own caption group. A remapped window is never clipped or
    silently deleted; when old timing cannot be mapped safely, retain the words
    and distribute a clearly marked draft over the actual current take window.
    """
    groups, unassigned = cue_groups(beats, old_cues)
    proposed = []
    changes = []
    prior_beats = prior_beats or {}
    for beat in beats:
        bid = beat['id']
        rows = groups[bid]
        expected = caption_text(beat.get('text', ''))
        complete = expected == caption_rows_text(beat.get('text', ''), rows)
        start, end = float(beat['start']), float(beat['end'])
        if not (math.isfinite(start) and math.isfinite(end) and 0 <= start < end):
            raise ValueError(f'{bid}: real source take window is invalid; no caption time can be proposed')
        if preserve_timing and complete and _windows_valid(rows, start, end):
            proposed.extend({**deepcopy(row), 'beat_id': bid} for row in rows)
            changes.append({'beat_id': bid, 'action': 'preserved_complete_current_timing'})
            continue
        if complete and rows:
            previous = prior_beats.get(bid)
            if previous and caption_text(previous.get('text', '')) == expected:
                source_start, source_end = float(previous['start']), float(previous['end'])
            else:
                source_start = min(float(q['start']) for q in rows)
                source_end = max(float(q['end']) for q in rows)
            if source_end > source_start and _windows_valid(rows, source_start, source_end):
                scale = (end - start) / (source_end - source_start)
                mapped = [{**q, 'start': round(start + (float(q['start']) - source_start) * scale, 6),
                           'end': round(start + (float(q['end']) - source_start) * scale, 6), 'beat_id': bid,
                           'timing_source': 'complete_editorial_breaks_mapped_to_current_take'} for q in rows]
                if _windows_valid(mapped, start, end):
                    proposed.extend(mapped)
                    changes.append({'beat_id': bid, 'action': 'remapped_complete_editorial_breaks'})
                    continue
        texts = [str(q['text']) for q in rows] if complete and rows else split_caption_text(str(beat.get('text', '')))
        lengths = [len(caption_text(text)) for text in texts]
        total = sum(lengths)
        if not total:
            raise ValueError(f'{bid}: approved caption text is empty')
        position = 0
        for text, length in zip(texts, lengths):
            proposed.append({'start': round(start + (end - start) * position / total, 6),
                             'end': round(start + (end - start) * (position + length) / total, 6),
                             'text': text.strip(), 'beat_id': bid,
                             'timing_source': 'approved_text_character_ratio_draft'})
            position += length
        changes.append({'beat_id': bid, 'action': 'redistributed_complete_breaks' if complete else 'rebuilt_missing_text',
                        'previous_differences': text_differences(beat.get('text', ''), caption_rows_text(beat.get('text', ''), rows))})
    return proposed, {'schema': 'paper_caption_timing/v2', 'changes': changes, 'unassigned_previous_cues': unassigned,
                      'complete_text_check': caption_audit(beats, proposed),
                      'timing_review': 'draft', 'audio_recognition_performed': False,
                      'note': 'Actual speech and phrase timing still require listening; no words were inferred from ASR.'}
