"""User delivery is latest-only; receipts and recoverable history live outside it."""
from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _compact_archived_wavs(backup: Path) -> None:
    """Losslessly archive WAV copies inside a retired delivery backup as exact-restore FLAC."""
    from opl_framework.delivery_layout import compact_archived_wav_files

    compact_archived_wav_files(
        backup / 'record',
        compaction_schema='medical_video_storage_compaction_group/v1',
        which=shutil.which,
    )


def is_pinned_delivery_snapshot(snapshot_dir: Path) -> tuple[bool, str | None]:
    """Return whether an archived delivery snapshot is pinned for long-term retention."""
    if not snapshot_dir.is_dir():
        return False, None
    if (snapshot_dir / '.pinned.json').is_file():
        return True, 'pin_marker'
    for rel, source in (('record/manifest.json', 'manifest'), ('record/review.json', 'review')):
        p = snapshot_dir / rel
        if not p.is_file():
            continue
        try:
            data = json.loads(p.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            continue
        if not isinstance(data, dict):
            continue
        if data.get('release_pinned') is True or data.get('published_release') is True:
            return True, f'{source}_release_pinned'
        reviews = data.get('reviews')
        if isinstance(reviews, dict) and reviews.get('medical') in ('approved', 'passed'):
            return True, f'{source}_medical_approved'
    return False, None


def _prune_old_archived_deliveries(archive_episode_dir: Path, keep_latest: int) -> list[str]:
    """Keep only the newest `keep_latest` unpinned rollback backups while preserving pinned snapshots."""
    if keep_latest < 0 or not archive_episode_dir.is_dir():
        return []
    pinned_names = [
        d.name for d in archive_episode_dir.iterdir()
        if d.is_dir() and is_pinned_delivery_snapshot(d)[0]
    ]
    from opl_framework.delivery_layout import prune_archived_versions

    return prune_archived_versions(
        archive_episode_dir,
        keep_latest=keep_latest,
        protected_names=pinned_names,
    )


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
    from _opl_framework_bootstrap import bootstrap_opl_framework

    bootstrap_opl_framework()
    from opl_framework.delivery_layout import transactional_swap_directories

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
