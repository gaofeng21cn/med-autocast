"""User delivery is latest-only; receipts and recoverable history live outside it."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile


def save(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _compact_archived_wavs(backup: Path) -> None:
    """Losslessly archive WAV copies inside a retired delivery backup as exact-restore FLAC."""
    if not shutil.which('flac'):
        return
    record_dir = backup / 'record'
    if not record_dir.is_dir():
        return
    records = []
    for wav_path in sorted(record_dir.glob('*.wav')):
        if wav_path.is_symlink() or not wav_path.is_file():
            continue
        try:
            with wav_path.open('rb') as handle:
                if handle.read(4) != b'RIFF':
                    continue
            source_sha = _sha256_file(wav_path)
            flac_path = wav_path.with_suffix('.flac')
            tmp_flac = wav_path.with_name(f'.{wav_path.name}.{os.getpid()}.tmp.flac')
            tmp_wav = wav_path.with_name(f'.{wav_path.name}.{os.getpid()}.verify.wav')
            try:
                subprocess.run(
                    ['flac', '-s', '--verify', '--keep-foreign-metadata', '-8',
                     '-f', str(wav_path), '-o', str(tmp_flac)],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                subprocess.run(
                    ['flac', '-s', '-d', '--keep-foreign-metadata', '-f',
                     str(tmp_flac), '-o', str(tmp_wav)],
                    check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                )
                if _sha256_file(tmp_wav) != source_sha:
                    continue
                st_src = wav_path.stat()
                os.replace(tmp_flac, flac_path)
                os.utime(flac_path, ns=(st_src.st_atime_ns, st_src.st_mtime_ns))
                st_dst = flac_path.stat()
                records.append({
                    'source': str(wav_path),
                    'target': str(flac_path),
                    'kind': 'audio_retained',
                    'source_sha256': source_sha,
                    'restored_wav_sha256': source_sha,
                    'target_sha256': _sha256_file(flac_path),
                    'size': st_src.st_size,
                    'allocated_bytes': st_src.st_blocks * 512,
                    'target_size': st_dst.st_size,
                    'target_allocated_bytes': st_dst.st_blocks * 512,
                })
                wav_path.unlink()
            finally:
                tmp_flac.unlink(missing_ok=True)
                tmp_wav.unlink(missing_ok=True)
        except (OSError, subprocess.CalledProcessError):
            continue
    if records:
        save(record_dir / 'storage-compaction.json', {
            'schema': 'medical_video_storage_compaction_group/v1',
            'directory': str(record_dir),
            'kind': 'audio_retained',
            'policy': 'lossless_flac_exact_wav_bytes_recoverable',
            'records': records,
        })


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
        # Compact archived WAVs after atomic switch succeeds; never rolls back delivery.
        if backup.exists():
            _compact_archived_wavs(backup)
        # Navigation is a projection of selected files. A missing catalog must
        # not roll back an otherwise complete, usable episode delivery.
        try:
            from publish_catalog import refresh
            payload['navigation'] = refresh(workspace, series)
        except Exception as exc:
            payload['navigation'] = {'status': 'diagnostic', 'error': str(exc),
                                     'blocks_stage_progress': False}
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
