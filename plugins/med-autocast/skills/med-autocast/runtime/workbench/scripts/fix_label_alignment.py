#!/usr/bin/env python3
"""Legacy label-fix entry, retained as a read-only candidate locator.

Source proximity does not establish a shared coordinate frame or text ownership.
Use actual rendered frames before editing the episode-local layout.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import yaml
from audit_label_alignment import audit_file


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--workspace', type=Path, default=Path.cwd())
    parser.add_argument('--only', help='Filter registered project paths')
    parser.add_argument('--dry-run', action='store_true', help='Read-only (the default)')
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    config = yaml.safe_load((workspace / 'workbench.yaml').read_text()) or {}
    findings = []
    count = 0
    for series in (config.get('series') or {}).values():
        for row in (series.get('episodes') or {}).values():
            if not row.get('project'):
                continue
            project = workspace / row['project']
            source = project / 'src/episodeshots.ts'
            if not source.is_file() or (args.only and args.only not in str(project)):
                continue
            count += 1
            for finding in audit_file(source):
                if not finding['is_var'] and finding['worst'] > 2:
                    findings.append({**finding, 'pairing': 'unverified_source_proximity',
                                     'requires_rendered_frame_review': True})
    print(json.dumps({'mode': 'read_only', 'registered_episodes_with_source': count,
                      'candidates': findings, 'files_changed': 0,
                      'note': '候选配对可能跨局部坐标或属于独立标注，不可据此自动居中或判定画面缺陷。'},
                     ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
