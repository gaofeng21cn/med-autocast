"""User delivery is latest-only; receipts and recoverable history live outside it."""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import tempfile


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def locations(workspace: Path, series: str, episode: str) -> dict:
    import yaml
    workspace = workspace.resolve()
    for identifier in (series, episode):
        if not identifier or Path(identifier).name != identifier or identifier in ('.', '..'):
            raise ValueError('无效系列或集号')
    config = yaml.safe_load((workspace / 'workbench.yaml').read_text()) or {}
    directories = config.get('directories', {})
    row = config.get('series', {}).get(series, {})
    publish = workspace / row.get('publish_root', str(Path(directories.get('publish', 'publish')) / series))
    internal = workspace / directories.get('deliveries', 'deliveries') / series
    archive = workspace / directories.get('archive', 'archive') / 'deliveries' / series / episode
    return {'user': publish.resolve() / episode, 'record': internal / episode,
            'pointer': internal / (episode + '.json'), 'archive': archive}


def archive_destination(workspace: Path, series: str, episode: str) -> Path:
    return locations(workspace, series, episode)['archive'] / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def install(workspace: Path, series: str, episode: str, user_stage: Path, record_stage: Path) -> dict:
    """Replace one episode's selected files and receipt with rollback on error."""
    loc = locations(workspace, series, episode)
    user, record, pointer = loc['user'], loc['record'], loc['pointer']
    backup = archive_destination(workspace, series, episode)
    before = pointer.read_bytes() if pointer.exists() else None
    replaced, installed = [], []
    try:
        for destination, name in ((user, 'publish'), (record, 'record')):
            destination.parent.mkdir(parents=True, exist_ok=True)
            if destination.exists():
                backup.mkdir(parents=True, exist_ok=True)
                destination.rename(backup / name)
                replaced.append((destination, backup / name))
        if before is not None:
            backup.mkdir(parents=True, exist_ok=True)
            (backup / 'pointer.json').write_bytes(before)
        for source, destination in ((user_stage, user), (record_stage, record)):
            source.rename(destination)
            installed.append(destination)
        payload = {'current': str(user), 'manifest': str(record / 'manifest.json'),
                   'layout': 'latest_only', 'previous_delivery': str(backup) if backup.exists() else None}
        # Readers see a complete new user directory and record before the pointer switches.
        pointer.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=pointer.parent, delete=False) as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write('\n')
            temporary = Path(handle.name)
        try:
            os.replace(temporary, pointer)
        finally:
            temporary.unlink(missing_ok=True)
        return payload
    except Exception:
        for destination in reversed(installed):
            shutil.rmtree(destination)
        for destination, previous in reversed(replaced):
            previous.rename(destination)
        if before is not None:
            pointer.write_bytes(before)
        else:
            pointer.unlink(missing_ok=True)
        raise
