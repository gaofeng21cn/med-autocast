#!/usr/bin/env python3
"""审计 episodeshots.ts 中「纸卡/色带 + 文字标签」的配对关系。

Stage.text 默认 textAlign=center / textBaseline=middle。各集本地 helper 用
硬编码坐标放标签，x 偏移与标签长度无关，因此：
  1) 短标签偏左、长标签溢出纸卡；
  2) 标签 y 常落在卡片底部，而色带在顶部。

统一约定：over_* 为正值表示溢出纸卡边界（缺陷），负值表示边界内余量。
"""
import json
import re
from pathlib import Path

Q = chr(39)
DQ = chr(34)
BT = chr(96)

PAPER_RE = re.compile(
    r"s\.paper\(\{\s*x:\s*0\s*,\s*y:\s*0\s*,\s*w:\s*(?P<w>[0-9.]+)\s*,\s*h:\s*(?P<h>[0-9.]+)"
)
TEXT_RE = re.compile(
    r"s\.text\(\s*(?P<label>" + Q + r"(?:[^" + Q + r"\\]|\\.)*" + Q + r"|"
    + DQ + r"(?:[^" + DQ + r"\\]|\\.)*" + DQ + r"|"
    + BT + r"[^" + BT + r"]*" + BT + r"|[A-Za-z_$][\w$]*)\s*,\s*"
    r"(?P<x>-?[0-9.]+)\s*,\s*(?P<y>-?[0-9.]+)\s*,\s*(?P<size>[0-9.]+)\s*"
    r"(?:,\s*" + Q + r"(?P<color>#[0-9a-fA-F]{3,8})" + Q + r"\s*)?\)"
)


def est_width(label, size):
    return sum(1.0 if ord(ch) > 0x2E80 else 0.55 for ch in label if ch != BT) * size


def audit_file(path):
    lines = path.read_text(encoding='utf-8').splitlines()
    papers = []
    for i, ln in enumerate(lines):
        m = PAPER_RE.search(ln)
        if m:
            papers.append((i, float(m.group('w')), float(m.group('h'))))
    findings = []
    for i, ln in enumerate(lines):
        m = TEXT_RE.search(ln)
        if not m:
            continue
        raw = m.group('label')
        is_var = not raw.startswith((Q, DQ, BT))
        label = raw[1:-1] if not is_var else raw
        x, y, size = float(m.group('x')), float(m.group('y')), float(m.group('size'))
        tw = est_width(label, size)
        cand = [p for p in papers if p[0] < i and i - p[0] <= 6]
        if not cand:
            continue
        pline, pw, ph = cand[-1]
        tl, tr = x - tw / 2, x + tw / 2
        tt, tb = y - size * 0.62, y + size * 0.62
        # margin_* 均为正值表示「文本完全在纸卡内」，负值表示溢出该边
        f = {
            'file': str(path),
            'episode': path.parent.parent.parent.name + '/' + path.parent.parent.name,
            'line': i + 1,
            'paper_line': pline + 1,
            'label': label,
            'is_var': is_var,
            'paper': [pw, ph],
            'text_xy': [x, y],
            'size': size,
            'text_w': round(tw, 1),
            'margin_left': round(tl + pw / 2, 1),
            'margin_right': round(pw / 2 - tr, 1),
            'margin_top': round(tt + ph / 2, 1),
            'margin_bottom': round(ph / 2 - tb, 1),
            'off_center_x': x,
            'off_center_y': y,
        }
        f['worst'] = -min(f['margin_left'], f['margin_right'],
                          f['margin_top'], f['margin_bottom'])
        findings.append(f)
    return findings


def main():
    root = Path(__file__).resolve().parents[1] / 'productions'
    latest = {}
    for f in sorted(root.glob('**/v*/src/episodeshots.ts')):
        ep = str(f.parent.parent.parent)
        latest.setdefault(ep, []).append((len(f.parent.parent.name), f))
    selected = [sorted(v)[-1][1] for v in latest.values()]
    all_f = []
    for f in selected:
        all_f.extend(audit_file(f))
    literal = [f for f in all_f if not f['is_var']]
    var = [f for f in all_f if f['is_var']]
    overflow = [f for f in literal if f['worst'] > 2]
    strips = [f for f in literal if f['paper'][1] <= 140 and f['paper'][0] >= 300]
    strip_off = [f for f in strips if abs(f['off_center_x']) > 12]
    cards = [f for f in literal if f['paper'][1] > 140]
    card_low = [f for f in cards if f['off_center_y'] > f['paper'][1] / 2 - 40]
    summary = {
        'episodes': len(selected),
        'text_pairs_total': len(all_f),
        'literal_labels': len(literal),
        'variable_labels': len(var),
        'overflow_any_edge': len(overflow),
        'strip_titles': len(strips),
        'strip_offcenter_gt_12': len(strip_off),
        'card_titles': len(cards),
        'card_label_near_bottom': len(card_low),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    out = {'summary': summary, 'findings': sorted(all_f, key=lambda d: -d['worst'])}
    report_dir = Path(__file__).resolve().parents[1] / 'work/label-align-audit'
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / 'report.json').write_text(
        json.dumps(out, ensure_ascii=False, indent=2), encoding='utf-8'
    )
    print('\n--- 溢出最严重 20 条')
    for f in overflow[:20]:
        print('%6.1f %-52s paper=%s xy=%s mL=%s mR=%s mT=%s mB=%s :: %s' % (
            f['worst'], f['episode'], f['paper'], f['text_xy'],
              f['margin_left'], f['margin_right'],
              f['margin_top'], f['margin_bottom'], f['label']))
    print('\n--- 条带标题偏离中心 15 条')
    for f in strip_off[:15]:
        print('offX=%7.1f %-52s paper=%s :: %s' % (
            f['off_center_x'], f['episode'], f['paper'], f['label']))


if __name__ == '__main__':
    main()
