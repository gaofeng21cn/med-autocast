"""User delivery is latest-only; receipts and recoverable history live outside it."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

from _opl_framework_bootstrap import bootstrap_opl_framework

bootstrap_opl_framework()

from opl_framework.delivery_layout import (  # noqa: E402
    compact_archived_wav_files,
    prune_archived_versions,
    transactional_swap_directories,
)
from opl_framework.workspace_storage import sha256_file as _sha256_file  # noqa: E402


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _compact_archived_wavs(backup: Path) -> None:
    """Losslessly archive WAV copies inside a retired delivery backup as exact-restore FLAC."""
    compact_archived_wav_files(
        backup / 'record',
        compaction_schema='medical_video_storage_compaction_group/v1',
        which=shutil.which,
    )


def _prune_old_archived_deliveries(archive_episode_dir: Path, keep_latest: int) -> list[str]:
    """Keep only the newest `keep_latest` rollback backups per episode."""
    return prune_archived_versions(archive_episode_dir, keep_latest=keep_latest)


def locations(workspace: Path, series: str, episode: str, *, config: dict | None = None) -> dict:
    import yaml
    workspace = workspace.resolve()
    for identifier in (series, episode):
        if not identifier or Path(identifier).name != identifier or identifier in ('.', '..'):
            raise ValueError('无效系列或集号')
    if config is None:
        config = yaml.safe_load((workspace / 'workbench.yaml').read_text()) or {}
    directories = config.get('directories', {})
    row = config.get('series', {}).get(series, {})
    publish = workspace / row.get('publish_root', str(Path(directories.get('publish', 'publish')) / series))
    internal = workspace / directories.get('deliveries', 'deliveries') / series
    archive = workspace / directories.get('archive', 'archive') / 'deliveries' / series / episode
    folder = (row.get('delivery') or {}).get('episode_dirs', {}).get(episode, episode)
    if not isinstance(folder, str) or not folder or Path(folder).name != folder or folder in ('.', '..'):
        raise ValueError('无效交付目录名称')
    return {'user': publish.resolve() / folder, 'record': internal / episode,
            'pointer': internal / (episode + '.json'), 'archive': archive}


def archive_destination(workspace: Path, series: str, episode: str) -> Path:
    return locations(workspace, series, episode)['archive'] / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')


def install(workspace: Path, series: str, episode: str, user_stage: Path, record_stage: Path) -> dict:
    """Replace one episode's selected files and receipt with rollback on error."""
    loc = locations(workspace, series, episode)
    user, record, pointer = loc['user'], loc['record'], loc['pointer']
    backup = archive_destination(workspace, series, episode)
    has_previous = user.exists() or record.exists() or pointer.exists()
    payload = {
        'current': str(user),
        'manifest': str(record / 'manifest.json'),
        'layout': 'latest_only',
        'previous_delivery': str(backup) if has_previous else None,
    }
    transactional_swap_directories(
        [(user_stage, user, 'publish'), (record_stage, record, 'record')],
        backup_dir=backup,
        pointer_path=pointer,
        pointer_payload=payload,
    )
    # Compact archived WAVs and cap rollback depth after atomic switch; never rolls back delivery.
    if backup.exists():
        _compact_archived_wavs(backup)
        try:
            import yaml
            cfg = yaml.safe_load((workspace / 'workbench.yaml').read_text(encoding='utf-8')) or {}
            keep_latest = int((cfg.get('delivery_policy') or {}).get('archive_keep_latest', 1))
            pruned = _prune_old_archived_deliveries(loc['archive'], keep_latest)
            if pruned:
                payload['pruned_old_archives'] = pruned
        except Exception:
            pass
    # Navigation is a projection of selected files. A missing catalog must
    # not roll back an otherwise complete, usable episode delivery.
    try:
        from publish_catalog import refresh
        payload['navigation'] = refresh(workspace, series)
    except Exception as exc:
        payload['navigation'] = {'status': 'diagnostic', 'error': str(exc),
                                 'blocks_stage_progress': False}
    return payload
