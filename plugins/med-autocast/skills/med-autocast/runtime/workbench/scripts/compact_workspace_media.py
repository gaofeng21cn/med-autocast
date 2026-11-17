#!/usr/bin/env python3
"""Plan and compact lossless medical-video intermediates without dropping evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from PIL import Image


SCHEMA = "medical_video_lossless_compaction/v1"
INTERMEDIATE_AUDIO = {
    "foley.wav",
    "music-raw.wav",
    "music-prepared.wav",
    "music-ducked.wav",
    "premix.wav",
}


def read_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    os.replace(temporary, path)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def pixel_sha256(path: Path) -> str:
    with Image.open(path) as image:
        rgba = image.convert("RGBA")
        digest = hashlib.sha256()
        digest.update(json.dumps(rgba.size).encode("ascii"))
        digest.update(rgba.tobytes())
        return digest.hexdigest()


def allocated_bytes(path: Path) -> int:
    return path.stat().st_blocks * 512


def candidate(path: Path, kind: str, workspace: Path) -> dict:
    target_suffix = ".webp" if kind == "qa_png" else ".flac"
    stat = path.stat()
    return {
        "kind": kind,
        "source": str(path),
        "relative_source": str(path.relative_to(workspace)),
        "target": str(path.with_suffix(target_suffix)),
        "size": stat.st_size,
        "allocated_bytes": allocated_bytes(path),
        "mtime_ns": stat.st_mtime_ns,
    }


def scan(workspace: Path) -> dict:
    candidates = []
    render_dirs = []
    for path in workspace.rglob("*"):
        if path.is_symlink():
            continue
        if path.is_dir() and path.name.startswith(".render-"):
            files = [item for item in path.rglob("*") if item.is_file() and not item.is_symlink()]
            render_dirs.append({
                "kind": "render_temp",
                "directory": str(path),
                "relative_directory": str(path.relative_to(workspace)),
                "files": len(files),
                "size": sum(item.stat().st_size for item in files),
                "allocated_bytes": sum(allocated_bytes(item) for item in files),
            })
            continue
        if not path.is_file() or path.suffix.lower() != ".png":
            continue
        if "qa" not in {part.lower() for part in path.parts}:
            continue
        candidates.append(candidate(path, "qa_png", workspace))

    for path in (workspace / "productions").rglob("*.wav"):
        if path.is_symlink() or not path.is_file():
            continue
        if path.name in INTERMEDIATE_AUDIO or "mix-history" in path.parts:
            candidates.append(candidate(path, "audio_intermediate", workspace))

    # Directory scans above may encounter a file before pruning the directory.
    unique = {row["source"]: row for row in candidates}
    candidates = sorted(unique.values(), key=lambda row: row["relative_source"])
    render_dirs.sort(key=lambda row: row["allocated_bytes"], reverse=True)
    return {
        "schema": SCHEMA,
        "workspace": str(workspace),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "status": "planned",
        "candidates": candidates,
        "render_temp_directories": render_dirs,
        "summary": {
            "candidates": len(candidates),
            "qa_png": sum(row["kind"] == "qa_png" for row in candidates),
            "audio_intermediate": sum(row["kind"] == "audio_intermediate" for row in candidates),
            "source_allocated_bytes": sum(row["allocated_bytes"] for row in candidates),
            "source_size": sum(row["size"] for row in candidates),
            "render_temp_directories": len(render_dirs),
            "render_temp_files": sum(row["files"] for row in render_dirs),
            "render_temp_allocated_bytes": sum(row["allocated_bytes"] for row in render_dirs),
        },
    }


def group_candidates(rows: list[dict]) -> dict[Path, list[dict]]:
    groups: dict[Path, list[dict]] = {}
    for row in rows:
        groups.setdefault(Path(row["source"]).parent, []).append(row)
    return groups


def prior_group_record(target: Path) -> dict | None:
    receipt = target.parent / "storage-compaction.json"
    if not receipt.is_file():
        return None
    for row in read_json(receipt).get("records", []):
        if Path(row.get("target", "")) == target:
            return row
    return None


def convert_png(row: dict) -> dict:
    source, target = Path(row["source"]), Path(row["target"])
    if source.exists() and target.exists():
        source_pixels, target_pixels = pixel_sha256(source), pixel_sha256(target)
        if source_pixels != target_pixels:
            raise RuntimeError(f"已有 WebP 与 PNG 像素不一致：{target}")
    elif source.exists():
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp.webp")
        try:
            subprocess.run(
                ["cwebp", "-quiet", "-lossless", "-exact", "-z", "4", "-mt",
                 str(source), "-o", str(temporary)],
                check=True,
            )
            source_pixels, target_pixels = pixel_sha256(source), pixel_sha256(temporary)
            if source_pixels != target_pixels:
                raise RuntimeError(f"WebP 像素校验失败：{source}")
            os.replace(temporary, target)
            os.utime(target, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
        finally:
            temporary.unlink(missing_ok=True)
    elif not target.exists():
        raise FileNotFoundError(f"源文件和转换后文件都不存在：{source}")
    else:
        previous = prior_group_record(target)
        if previous is None or previous.get("pixel_sha256") != pixel_sha256(target):
            raise RuntimeError(f"只看到转换后文件，缺少可验证的同批像素记录：{target}")
        row = {**row, **previous}
    result = {
        **row,
        "source_sha256": sha256(source) if source.exists() else None,
        "target_sha256": sha256(target),
        "pixel_sha256": pixel_sha256(target),
        "target_size": target.stat().st_size,
        "target_allocated_bytes": allocated_bytes(target),
    }
    return result


def exact_wav_sha_from_flac(flac_path: Path, directory: Path) -> str:
    with tempfile.NamedTemporaryFile(suffix=".wav", dir=directory, delete=False) as handle:
        restored = Path(handle.name)
    try:
        subprocess.run(
            ["flac", "-s", "-d", "--keep-foreign-metadata", "-f",
             str(flac_path), "-o", str(restored)],
            check=True,
        )
        return sha256(restored)
    finally:
        restored.unlink(missing_ok=True)


def convert_wav(row: dict) -> dict:
    source, target = Path(row["source"]), Path(row["target"])
    source_sha = sha256(source) if source.exists() else None
    if source.exists() and target.exists():
        if exact_wav_sha_from_flac(target, target.parent) != source_sha:
            raise RuntimeError(f"已有 FLAC 无法还原当前 WAV：{target}")
    elif source.exists():
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp.flac")
        try:
            subprocess.run(
                ["flac", "-s", "--verify", "--keep-foreign-metadata", "-8",
                 "-f", str(source), "-o", str(temporary)],
                check=True,
            )
            restored_sha = exact_wav_sha_from_flac(temporary, target.parent)
            if restored_sha != source_sha:
                raise RuntimeError(f"FLAC 还原 WAV 字节校验失败：{source}")
            os.replace(temporary, target)
            os.utime(target, ns=(source.stat().st_atime_ns, source.stat().st_mtime_ns))
        finally:
            temporary.unlink(missing_ok=True)
    elif not target.exists():
        raise FileNotFoundError(f"源文件和转换后文件都不存在：{source}")
    else:
        previous = prior_group_record(target)
        if previous is None or previous.get("restored_wav_sha256") != exact_wav_sha_from_flac(
            target, target.parent
        ):
            raise RuntimeError(f"只看到 FLAC，缺少可验证的同批 WAV 记录：{target}")
        row = {**row, **previous}
    return {
        **row,
        "source_sha256": source_sha,
        "restored_wav_sha256": exact_wav_sha_from_flac(target, target.parent),
        "target_sha256": sha256(target),
        "target_size": target.stat().st_size,
        "target_allocated_bytes": allocated_bytes(target),
    }


def update_text_references(directory: Path, mappings: list[tuple[str, str]]):
    for path in directory.rglob("*"):
        if not path.is_file() or path.name == "storage-compaction.json":
            continue
        if path.suffix.lower() not in {".json", ".ffconcat"}:
            continue
        text = path.read_text(encoding="utf-8")
        updated = text
        for old, new in mappings:
            updated = updated.replace(old, new)
        if updated != text:
            temporary = path.with_name(path.name + ".tmp")
            temporary.write_text(updated, encoding="utf-8")
            os.replace(temporary, path)


def update_mix_snapshot(directory: Path, mappings: dict[str, str]):
    snapshot = directory / "snapshot.json"
    if not snapshot.is_file():
        return
    data = read_json(snapshot)
    files = data.get("files")
    if not isinstance(files, dict):
        return
    changed = False
    for old, new in mappings.items():
        record = files.get(old)
        if not isinstance(record, dict):
            continue
        del files[old]
        files[new] = {
            **record,
            "format": "flac_lossless",
            "compressed_file": new,
            "compressed_sha256": sha256(directory / new),
            "restore": {
                "source": new,
                "command": f"flac -d --keep-foreign-metadata {new} -o {old}",
                "expected_wav_sha256": record.get("sha256"),
            },
        }
        changed = True
    if changed:
        data.setdefault("storage_compaction", {})[
            "policy"
        ] = "lossless FLAC with exact WAV restoration"
        write_json(snapshot, data)


def process_group(directory: Path, rows: list[dict], workers: int) -> dict:
    kind = rows[0]["kind"]
    converter = convert_png if kind == "qa_png" else convert_wav
    records = []
    with ThreadPoolExecutor(max_workers=min(workers, len(rows))) as pool:
        futures = {pool.submit(converter, row): row for row in rows}
        for future in as_completed(futures):
            records.append(future.result())
    records.sort(key=lambda row: row["source"])
    mappings = [(Path(row["source"]).name, Path(row["target"]).name) for row in records]
    update_text_references(directory, mappings)
    update_mix_snapshot(directory, dict(mappings))
    receipt = {
        "schema": "medical_video_storage_compaction_group/v1",
        "directory": str(directory),
        "kind": kind,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "records": records,
        "policy": (
            "lossless_webp_same_rgba_pixels"
            if kind == "qa_png"
            else "lossless_flac_exact_wav_bytes_recoverable"
        ),
    }
    write_json(directory / "storage-compaction.json", receipt)
    for row in records:
        source = Path(row["source"])
        if source.exists():
            source.unlink()
    return {
        "directory": str(directory),
        "kind": kind,
        "files": len(records),
        "source_allocated_bytes": sum(row["allocated_bytes"] for row in records),
        "target_allocated_bytes": sum(row["target_allocated_bytes"] for row in records),
    }


def process_audio(manifest: dict, workers: int, output: Path) -> dict:
    rows = [row for row in manifest["candidates"] if row["kind"] == "audio_intermediate"]
    completed = []
    for index, (directory, group) in enumerate(sorted(group_candidates(rows).items()), 1):
        result = process_group(directory, group, workers)
        completed.append(result)
        print(json.dumps({"group": index, "directory": str(directory), "files": len(group)}),
              flush=True)
    report = {
        "schema": "medical_video_lossless_compaction_apply/v1",
        "kind": "audio_intermediate",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "groups": completed,
        "summary": {
            "groups": len(completed),
            "files": sum(row["files"] for row in completed),
            "source_allocated_bytes": sum(row["source_allocated_bytes"] for row in completed),
            "target_allocated_bytes": sum(row["target_allocated_bytes"] for row in completed),
        },
    }
    write_json(output, report)
    return report


def process_qa(manifest: dict, workers: int, output: Path) -> dict:
    rows = [row for row in manifest["candidates"] if row["kind"] == "qa_png"]
    completed = []
    for index, (directory, group) in enumerate(sorted(group_candidates(rows).items()), 1):
        result = process_group(directory, group, workers)
        completed.append(result)
        print(json.dumps({"group": index, "directory": str(directory), "files": len(group)}),
              flush=True)
    report = {
        "schema": "medical_video_lossless_compaction_apply/v1",
        "kind": "qa_png",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "groups": completed,
        "summary": {
            "groups": len(completed),
            "files": sum(row["files"] for row in completed),
            "source_allocated_bytes": sum(row["source_allocated_bytes"] for row in completed),
            "target_allocated_bytes": sum(row["target_allocated_bytes"] for row in completed),
        },
    }
    write_json(output, report)
    return report


def process_render_temp(manifest: dict, output: Path) -> dict:
    records = []
    for entry in manifest.get("render_temp_directories", []):
        directory = Path(entry["directory"])
        if not directory.exists():
            continue
        files = []
        for path in directory.rglob("*"):
            if path.is_file() and not path.is_symlink():
                files.append({
                    "path": str(path),
                    "size": path.stat().st_size,
                    "sha256": sha256(path),
                })
        record = {**entry, "file_records": files}
        records.append(record)
    receipt = {
        "schema": "medical_video_render_temp_cleanup/v1",
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "directories": records,
        "summary": {
            "directories": len(records),
            "files": sum(row["files"] for row in records),
            "allocated_bytes": sum(row["allocated_bytes"] for row in records),
        },
    }
    write_json(output, receipt)
    for entry in records:
        shutil.rmtree(Path(entry["directory"]))
    return receipt


def restore(manifest_path: Path, requested: list[Path], output: Path):
    manifest = read_json(manifest_path)
    index = {}
    for row in manifest["candidates"]:
        index[Path(row["source"]).resolve()] = row
        index[Path(row["target"]).resolve()] = row
    results = []
    for item in requested:
        resolved = item.resolve()
        row = index.get(resolved)
        if row is None:
            raise KeyError(f"文件不在压缩清单中：{item}")
        source, target = Path(row["source"]), Path(row["target"])
        group_record = prior_group_record(target)
        if group_record is None:
            raise RuntimeError(f"缺少同目录压缩回执：{target.parent / 'storage-compaction.json'}")
        if row["kind"] == "audio_intermediate":
            subprocess.run(
                ["flac", "-s", "-d", "--keep-foreign-metadata", "-f",
                 str(target), "-o", str(source)],
                check=True,
            )
            if sha256(source) != group_record.get("source_sha256"):
                raise RuntimeError(f"恢复后 WAV 字节不一致：{source}")
        else:
            with Image.open(target) as image:
                image.save(source, "PNG")
            if pixel_sha256(source) != group_record.get("pixel_sha256"):
                raise RuntimeError(f"恢复后 PNG 像素不一致：{source}")
        results.append({"source": str(source), "restored_from": str(target)})
    write_json(output, {"schema": "medical_video_lossless_restore/v1", "records": results})
    print(json.dumps({"restored": len(results), "output": str(output)}, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)

    scan_parser = sub.add_parser("plan")
    scan_parser.add_argument("--workspace", type=Path, required=True)
    scan_parser.add_argument("--output", type=Path, required=True)

    apply_parser = sub.add_parser("apply")
    apply_parser.add_argument("--manifest", type=Path, required=True)
    apply_parser.add_argument("--parts", nargs="+", choices=("audio", "qa", "render-temp"),
                              required=True)
    apply_parser.add_argument("--workers", type=int, default=8)
    apply_parser.add_argument("--output", type=Path, required=True)

    restore_parser = sub.add_parser("restore")
    restore_parser.add_argument("--manifest", type=Path, required=True)
    restore_parser.add_argument("--path", type=Path, action="append", required=True)
    restore_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "plan":
        manifest = scan(args.workspace.resolve())
        write_json(args.output, manifest)
        print(json.dumps(manifest["summary"], ensure_ascii=False))
    elif args.command == "apply":
        raise SystemExit("此清单只有格式库存，不能直接批量压缩。请先运行 plan_workspace_retention.py plan，再按必要性计划 apply。")
    elif args.command == "restore":
        restore(args.manifest, args.path, args.output)


if __name__ == "__main__":
    main()
