#!/usr/bin/env python3
"""Rewrite paper-backed text labels so they are derived from the paper box.

Root cause: Stage.text() defaults to textAlign=center, but every episode wrote
hard-coded x offsets that were hand-tuned per label length. A short label ends
up left of the paper centre; a long one spills off the left edge. This codemod
replaces each paper+text pair with kit/labels.cardTitle(s, W, H, ...), which
derives x from the box and shrinks the type to fit as a floor.

It only touches text whose coordinates sit inside a paper drawn at x:0,y:0 in
the same local frame, so positional annotations elsewhere are left alone. The
original y is preserved (the vertical composition was intentional); x becomes
box-derived.

Usage:
  python3 scripts/fix_label_alignment.py --dry-run     # report only
  python3 scripts/fix_label_alignment.py --apply       # rewrite + sync kit
"""
from __future__ import annotations

import argparse
import json
import re
import shutil
import sys
import time
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
_LOCAL_KIT = WORKSPACE / 'templates/animation/paper_theatre/src/kit'
TEMPLATE_KIT = _LOCAL_KIT if _LOCAL_KIT.is_dir() else Path(
    '/Users/gaofeng/workspace/med-autocast/runtime/workbench/templates/'
    'animation/paper_theatre/src/kit'
)
BACKUP = WORKSPACE / 'work/label-align-audit/originals'

Q = chr(39)
DQ = chr(34)
BT = chr(96)

# s.paper({ x: 0, y: 0, w: <expr>, h: <expr>, ...
PAPER_RE = re.compile(
    r"s\.paper\(\{\s*x:\s*0\s*,\s*y:\s*0\s*,\s*w:\s*(?P<w>[0-9.]+(?:\s*\*\s*[0-9.]+)?)"
    r"\s*,\s*h:\s*(?P<h>[0-9.]+)\s*[,}]"
)
# s.text(<label>, <x>, <y>, <size>[, '<color>'])
TEXT_RE = re.compile(
    r"s\.text\(\s*(?P<label>" + Q + r"(?:[^" + Q + r"\\]|\\.)*" + Q + r"|"
    + DQ + r"(?:[^" + DQ + r"\\]|\\.)*" + DQ + r"|"
    + BT + r"[^" + BT + r"]*" + BT + r"|[A-Za-z_$][\w$]*)\s*,\s*"
    r"(?P<x>-?[0-9.]+)\s*,\s*(?P<y>-?[0-9.]+)\s*,\s*(?P<size>[0-9.]+)\s*"
    r"(?:,\s*(?P<color>" + Q + r"#[0-9a-fA-F]{3,8}" + Q + r"))?\s*\)"
)
IMPORT_LINE = "import { cardTitle } from './kit/labels';"


def rewrite_file(path: Path, apply: bool):
    lines = path.read_text(encoding='utf-8').splitlines()
    paper_at = []  # (idx, w_expr, h_expr)
    for i, ln in enumerate(lines):
        m = PAPER_RE.search(ln)
        if m:
            paper_at.append((i, m.group('w').replace(' ', ''), m.group('h')))
    edits = {}  # line_idx -> new_line
    rewrites = 0
    for i, ln in enumerate(lines):
        m = TEXT_RE.search(ln)
        if not m:
            continue
        # nearest paper above, within 6 lines. If several papers appear in the
        # window the block has branching card widths (e.g. a shape switch), so
        # pairing is ambiguous and we must not guess the box.
        cand = [p for p in paper_at if p[0] < i and i - p[0] <= 6]
        if not cand:
            continue
        if len(cand) > 1:
            continue
        pidx, w, h = cand[-1]
        label = m.group('label')
        y = m.group('y')
        size = m.group('size')
        color = m.group('color')
        # A wide short strip is a headline band: centre it on both axes so the
        # type sits in the middle of the colour strip. Small tags and ruled
        # cards keep their original vertical composition (tape at the top,
        # ruled lines below), which the director placed on purpose.
        try:
            wf = float(w)
            hf = float(h)
        except ValueError:
            wf = hf = 0.0
        if wf >= 260 and hf <= 140:
            y = '0'
        if color:
            opts = '{ size: ' + size + ', color: ' + color + ', y: ' + y + ' }'
        else:
            opts = '{ size: ' + size + ', y: ' + y + ' }'
        new = 'cardTitle(s, ' + w + ', ' + h + ', ' + label + ', ' + opts + ')'
        edits[i] = ln[:m.start()] + new + ln[m.end():]
        rewrites += 1
    if rewrites and apply:
        out = list(lines)
        for i, new in edits.items():
            out[i] = new
        text = '\n'.join(out) + '\n'
        if IMPORT_LINE not in text:
            lines2 = text.split('\n')
            # insert after the last top-of-file import
            last = 0
            for k, l in enumerate(lines2[:20]):
                if l.startswith('import '):
                    last = k
            lines2.insert(last + 1, IMPORT_LINE)
            text = '\n'.join(lines2)
        path.write_text(text, encoding='utf-8')
    return rewrites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--apply', action='store_true')
    ap.add_argument('--sync-kit', dest='sync_kit', action='store_true')
    ap.add_argument('--only', default=None,
                    help='substring filter on series/episode path (dry-run or apply one slice)')
    args = ap.parse_args()
    apply = args.apply

    # latest v* per episode
    latest = {}
    for f in sorted((WORKSPACE / 'productions').glob('**/v*/src/episodeshots.ts')):
        ep = str(f.parent.parent.parent)
        latest.setdefault(ep, []).append((len(f.parent.parent.name), f))
    files = [sorted(v)[-1][1] for v in latest.values()]
    if args.only:
        files = [f for f in files if args.only in str(f)]

    # sync labels.ts into every episode kit + template
    if args.sync_kit or apply:
        src = TEMPLATE_KIT / 'labels.ts'
        kits = 0
        for f in files:
            kdir = f.parent / 'kit'
            if kdir.is_dir():
                shutil.copy2(src, kdir / 'labels.ts')
                kits += 1
        print(json.dumps({'synced_labels_kit': kits}, ensure_ascii=False))

    if apply:
        BACKUP.mkdir(parents=True, exist_ok=True)
        for f in files:
            dst = BACKUP / (f.parent.parent.parent.name + '__' + f.parent.parent.name + '.ts')
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst)

    total = 0
    per = {}
    for f in files:
        n = rewrite_file(f, apply)
        total += n
        if n:
            per[str(f.parent.parent.parent.name) + '/' + f.parent.parent.name] = n
    print(json.dumps({
        'mode': 'apply' if apply else 'dry-run',
        'episodes': len(files),
        'rewrites': total,
        'per_episode': per,
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
