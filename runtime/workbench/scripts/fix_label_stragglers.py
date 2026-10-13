#!/usr/bin/env python3
"""Hand-fix the multi-branch paper cases the codemod deliberately skipped."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / 'productions'

CASES = [
    (
        'hashimoto_paper_theatre/03_the_breakfast_arrangement/v1/src/episodeshots.ts',
        "s.text('每天稳定 比今天多少明天少重要', -230, -12, 24, '#33504c');",
        "cardTitle(s, 500, 94, '每天稳定 比今天多少明天少重要', "
        "{ size: 24, color: '#33504c', y: 0 })",
    ),
    (
        'pituitary_paper_theatre/08_cortisol_find_the_source/v8/src/episodeshots.ts',
        "s.text('外形只是线索之一', -130, -20, 22, '#33504c');",
        "cardTitle(s, 320, 130, '外形只是线索之一', "
        "{ size: 22, color: '#33504c', y: 0 })",
    ),
]

for rel, old, new in CASES:
    p = ROOT / rel
    src = p.read_text(encoding='utf-8')
    if old not in src:
        print('MISS', rel)
        continue
    p.write_text(src.replace(old, new), encoding='utf-8')
    print('OK', rel)
