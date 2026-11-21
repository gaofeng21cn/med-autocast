#!/usr/bin/env python3
"""Three-state episode storage lifecycle: working -> sealed -> retired.

Separates in-process working data (transient caches, undo history, copied library
assets, uncompressed mix intermediates, superseded revisions) from durable
canonical assets and final deliverables, with transparent SHA-256-verified
re-hydration whenever a sealed episode is edited, built, rendered, or revised.
"""
from __future__ import annotations

import argparse
import collections
import ctypes
import hashlib
import json
import os
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

SCHEMA_HYDRATION = "medical_video_project_hydration/v1"
HYDRATION_FILE = "storage-hydration.json"
VERSION_RE = re.compile(r"^v(\d+)$")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", ".cache"}
F_LOG2PHYS = 49
COW_SCAN_DIRS = ("assets", "productions", "publish", "deliveries", "archive/deliveries", "work")
WORK_PRUNABLE_MEDIA_EXTS = {
    ".png", ".webp", ".jpg", ".jpeg", ".mp4", ".mov",
    ".wav", ".flac", ".mp3", ".m4a", ".aac", ".ffconcat",
}
WORK_PROTECTED_PREFIXES = ("disk-lifecycle-", "disk-cleanup-")
WORK_PROTECTED_NAMES = {"historical-interaction-review"}
QA_PRUNABLE_IMAGE_EXTS = {".png", ".webp"}
QA_KEEP_FILENAMES = {"contact.jpg", "cut-pairs.jpg", "mobile-360.jpg"}
QA_KEEP_STRIP_RE = re.compile(r"^strip-s\d+(?:-r\d+)?\.jpg$")
LINEAGE_TEXT_EXTS = {
    ".ts", ".tsx", ".js", ".mjs", ".cjs", ".css", ".html", ".svg",
    ".json", ".md", ".txt", ".yaml", ".yml", ".srt", ".py", ".sh",
}
LINEAGE_SKIP_DIRS = {"assets", "qa", "out", "dist", "node_modules", "__pycache__", "entries"}
LINEAGE_AUDIO_KEEP = {"narration_beats.json", "mix-receipt.json", "timing-receipt.json", "narration.json", "pronunciation-review.json"}


def stamp() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S%z")


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def clone_or_copy(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin" and src.is_file() and not src.is_symlink():
        try:
            libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
            fn = libc.clonefile
            fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
            fn.restype = ctypes.c_int
            tmp = dst.with_name(f".{dst.name}.{os.getpid()}.hydrate-tmp")
            try:
                if fn(os.fsencode(src), os.fsencode(tmp), 0) == 0:
                    os.replace(tmp, dst)
                    return
            finally:
                tmp.unlink(missing_ok=True)
        except OSError:
            pass
    tmp = dst.with_name(f".{dst.name}.{os.getpid()}.hydrate-tmp")
    try:
        shutil.copy2(src, tmp)
        os.replace(tmp, dst)
    finally:
        tmp.unlink(missing_ok=True)


def dir_stats(directory: Path) -> tuple[int, int]:
    files = alloc = 0
    if not directory.exists():
        return 0, 0
    for dp, dns, fns in os.walk(directory, followlinks=False):
        dns[:] = [d for d in dns if not (Path(dp) / d).is_symlink()]
        for fn in fns:
            p = Path(dp) / fn
            if p.is_symlink():
                continue
            try:
                alloc += p.lstat().st_blocks * 512
                files += 1
            except OSError:
                pass
    return files, alloc


def build_global_asset_index(workspace: Path) -> dict[str, str]:
    """Index authoritative workspace/assets/ files as {sha256: workspace_rel_path}."""
    workspace = workspace.resolve()
    assets_root = workspace / "assets"
    if not assets_root.is_dir():
        return {}
    candidates = []
    for dp, dns, fns in os.walk(assets_root, followlinks=False):
        dns[:] = [d for d in dns if d not in SKIP_DIRS and not (Path(dp) / d).is_symlink()]
        for fn in fns:
            p = Path(dp) / fn
            if p.is_symlink() or not p.is_file():
                continue
            candidates.append(p)
    # Prefer canonical entries/ paths over auxiliary copies when hashes collide.
    candidates.sort(key=lambda p: (0 if "entries" in p.parts else 1, str(p)))
    index: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=8) as pool:
        for p, digest in zip(candidates, pool.map(sha256_file, candidates)):
            index.setdefault(digest, str(p.relative_to(workspace)))
    return index


def hydrate_project(project: Path, workspace: Path) -> dict:
    """Transparently restore a sealed project back to working state with exact SHA-256 checks."""
    project = project.resolve()
    workspace = workspace.resolve()
    manifest_path = project / HYDRATION_FILE
    if not manifest_path.is_file():
        return {"status": "already_working", "project": str(project), "restored_files": 0}

    data = read_json(manifest_path)
    if data.get("schema") != SCHEMA_HYDRATION:
        raise ValueError(f"Unsupported hydration manifest schema: {manifest_path}")

    restored_clones = 0
    restored_audio = 0
    for entry in data.get("entries", []):
        kind = entry.get("kind")
        rel_path = entry["rel_path"]
        expected_sha = entry["sha256"]
        target = (project / rel_path).resolve()
        if not target.is_relative_to(project):
            raise ValueError(f"Hydration target escapes project: {rel_path}")

        if kind == "clone_from_workspace":
            if target.is_file() and sha256_file(target) == expected_sha:
                continue
            source = (workspace / entry["source_rel"]).resolve()
            if not source.is_relative_to(workspace) or not source.is_file():
                raise FileNotFoundError(f"Missing authoritative hydration source: {entry['source_rel']}")
            if sha256_file(source) != expected_sha:
                raise RuntimeError(f"Authoritative hydration source hash changed: {entry['source_rel']}")
            clone_or_copy(source, target)
            if sha256_file(target) != expected_sha:
                raise RuntimeError(f"Hydrated file hash mismatch: {rel_path}")
            restored_clones += 1
        elif kind == "flac_audio":
            flac_path = (project / entry["archive_rel"]).resolve()
            if not (target.is_file() and sha256_file(target) == expected_sha):
                if not flac_path.is_file():
                    raise FileNotFoundError(f"Missing sealed FLAC archive: {entry['archive_rel']}")
                if not shutil.which("flac"):
                    raise RuntimeError("Missing flac binary required to hydrate sealed audio")
                target.parent.mkdir(parents=True, exist_ok=True)
                tmp = target.with_name(f".{target.name}.{os.getpid()}.restore-tmp")
                try:
                    subprocess.run(
                        ["flac", "-s", "-d", "--keep-foreign-metadata", "-f", str(flac_path), "-o", str(tmp)],
                        check=True,
                        stdout=subprocess.DEVNULL,
                        stderr=subprocess.DEVNULL,
                    )
                    if sha256_file(tmp) != expected_sha:
                        raise RuntimeError(f"Restored WAV hash mismatch: {rel_path}")
                    os.replace(tmp, target)
                finally:
                    tmp.unlink(missing_ok=True)
            # Remove archive copy after verified restoration so working tree has single WAV.
            flac_path.unlink(missing_ok=True)
            comp_path = flac_path.parent / "storage-compaction.json"
            if comp_path.is_file():
                comp = read_json(comp_path)
                comp["records"] = [
                    r for r in comp.get("records", [])
                    if Path(r.get("target", "")).name != flac_path.name
                ]
                if comp["records"]:
                    write_json(comp_path, comp)
                else:
                    comp_path.unlink(missing_ok=True)
            restored_audio += 1
        else:
            raise ValueError(f"Unknown hydration entry kind: {kind}")

    manifest_path.unlink()
    return {
        "status": "hydrated",
        "project": str(project),
        "restored_clones": restored_clones,
        "restored_audio": restored_audio,
        "restored_files": restored_clones + restored_audio,
    }


def _active_map(workspace: Path, wb_config: dict | None = None) -> dict[Path, tuple[str, str]]:
    if wb_config is None:
        wb_path = workspace / "workbench.yaml"
        wb_config = yaml.safe_load(wb_path.read_text(encoding="utf-8")) if wb_path.is_file() else {}
    mapping: dict[Path, tuple[str, str]] = {}
    for sid, row in (wb_config.get("series") or {}).items():
        for eid, ep in (row.get("episodes") or {}).items():
            proj = ep.get("project")
            if proj:
                mapping[(workspace / proj).resolve()] = (sid, eid)
    return mapping


def _collect_external_qa_refs(workspace: Path) -> set[Path]:
    """Collect qa/ image paths explicitly cited by docs outside productions/ or by review docs."""
    cited: set[Path] = set()
    token_re = re.compile(r'[^\s\"\'`<>\[\](){};,，：]+\.(?:png|webp)')
    for top in ("work/historical-interaction-review", "content", "docs", "deliveries"):
        base = workspace / top
        if not base.is_dir():
            continue
        for dp, dns, fns in os.walk(base, followlinks=False):
            dns[:] = [d for d in dns if d not in SKIP_DIRS]
            for fn in fns:
                p = Path(dp) / fn
                if p.suffix.lower() not in {".md", ".json", ".txt", ".yaml", ".yml"}:
                    continue
                try:
                    txt = p.read_text(encoding="utf-8")
                except (OSError, UnicodeError):
                    continue
                for tok in token_re.findall(txt):
                    if "productions/" in tok:
                        idx = tok.find("productions/")
                        cand = (workspace / tok[idx:]).resolve()
                        if cand.is_file():
                            cited.add(cand)
    return cited


def seal_project(
    project: Path,
    workspace: Path,
    *,
    global_index: dict[str, str] | None = None,
    wb_config: dict | None = None,
    external_refs: set[Path] | None = None,
    apply: bool = False,
) -> dict:
    """Seal an already-published active episode by retiring in-process artifacts and dehydrating duplicates."""
    project = project.resolve()
    workspace = workspace.resolve()
    if not project.is_relative_to(workspace):
        raise ValueError("Project must reside inside workspace")

    import delivery_layout as dl
    import plan_workspace_retention as retention
    from compact_workspace_media import convert_wav

    if wb_config is None:
        wb_config = yaml.safe_load((workspace / "workbench.yaml").read_text(encoding="utf-8")) or {}
    active = _active_map(workspace, wb_config)
    if project not in active:
        return {"status": "skipped", "project": str(project), "reason": "not_active_in_workbench"}

    sid, eid = active[project]
    loc = dl.locations(workspace, sid, eid, config=wb_config)
    pub_video = loc["user"] / "video.mp4"
    deliv_manifest = loc["record"] / "manifest.json"
    cur_json = project / "out/current.json"
    if not (pub_video.is_file() and deliv_manifest.is_file() and cur_json.is_file()):
        return {"status": "skipped", "project": str(project), "reason": "delivery_or_current_pointer_missing"}

    cur_data = read_json(cur_json)
    pub_sha = sha256_file(pub_video)
    if cur_data.get("sha256") != pub_sha:
        return {
            "status": "skipped_working",
            "project": str(project),
            "reason": "current_render_differs_from_published_video",
            "current_sha256": cur_data.get("sha256"),
            "publish_sha256": pub_sha,
        }

    if global_index is None:
        global_index = build_global_asset_index(workspace)
    if external_refs is None:
        external_refs = _collect_external_qa_refs(workspace)

    # Preserve existing hydration entries if partially sealed already.
    existing_hydration = read_json(project / HYDRATION_FILE) if (project / HYDRATION_FILE).is_file() else {}
    hydration_by_rel = {e["rel_path"]: e for e in existing_hydration.get("entries", [])}

    plan_mix_history = []
    mix_hist_dir = project / "audio/mix-history"
    if mix_hist_dir.is_dir():
        fc, al = dir_stats(mix_hist_dir)
        if fc > 0:
            plan_mix_history.append({"path": str(mix_hist_dir), "files": fc, "allocated_bytes": al})

    plan_qa_prune = []
    qa_dir = project / "qa"
    if qa_dir.is_dir():
        for dp, dns, fns in os.walk(qa_dir, followlinks=False):
            dns[:] = [d for d in dns if d != "asset-reviews" and not (Path(dp) / d).is_symlink()]
            for fn in fns:
                p = Path(dp) / fn
                if p.is_symlink() or not p.is_file():
                    continue
                if fn in QA_KEEP_FILENAMES or QA_KEEP_STRIP_RE.fullmatch(fn):
                    continue
                if p.suffix.lower() not in QA_PRUNABLE_IMAGE_EXTS:
                    continue
                if p.resolve() in external_refs:
                    continue
                # Preserve frames explicitly cited by local review markdown docs.
                plan_qa_prune.append({"path": str(p), "allocated_bytes": p.lstat().st_blocks * 512})

    # Filter out frames referenced by any project-local review markdown
    local_cited_names: set[str] = set()
    for md in list(project.glob("*.md")) + list((project / "qa").glob("*.md") if qa_dir.is_dir() else []):
        try:
            txt = md.read_text(encoding="utf-8")
            for tok in re.findall(r'[^\s\"\'`<>\[\](){};,，：]+\.(?:png|webp)', txt):
                local_cited_names.add(Path(tok).name)
        except (OSError, UnicodeError):
            pass
    if local_cited_names:
        plan_qa_prune = [r for r in plan_qa_prune if Path(r["path"]).name not in local_cited_names]

    # Audio files to archive to exact-restore FLAC (keep audio/narration.wav untouched as CoW-shared w/ deliveries)
    plan_audio_flac = []
    audio_candidates = [project / "audio.wav", project / "audio/narration-normalized.wav"]
    seg_dir = project / "audio/segments"
    if seg_dir.is_dir():
        audio_candidates.extend(sorted(p for p in seg_dir.iterdir() if p.is_file() and not p.is_symlink() and p.suffix.lower() == ".wav"))
    for wav in audio_candidates:
        if not wav.is_file() or wav.is_symlink():
            continue
        try:
            with wav.open("rb") as fh:
                if fh.read(4) != b"RIFF":
                    continue
        except OSError:
            continue
        st = wav.lstat()
        plan_audio_flac.append({
            "source": str(wav),
            "target": str(wav.with_suffix(".flac")),
            "rel_path": str(wav.relative_to(project)),
            "archive_rel": str(wav.with_suffix(".flac").relative_to(project)),
            "size": st.st_size,
            "allocated_bytes": st.st_blocks * 512,
            "mtime_ns": st.st_mtime_ns,
        })

    # Assets identical to global workspace/assets/ -> dehydrate into storage-hydration.json
    plan_asset_dehydrate = []
    assets_dir = project / "assets"
    if assets_dir.is_dir():
        for dp, dns, fns in os.walk(assets_dir, followlinks=False):
            dns[:] = [d for d in dns if d not in SKIP_DIRS and not (Path(dp) / d).is_symlink()]
            for fn in fns:
                p = Path(dp) / fn
                if p.is_symlink() or not p.is_file():
                    continue
                digest = sha256_file(p)
                global_rel = global_index.get(digest)
                if global_rel:
                    st = p.lstat()
                    plan_asset_dehydrate.append({
                        "path": str(p),
                        "rel_path": str(p.relative_to(project)),
                        "source_rel": global_rel,
                        "sha256": digest,
                        "size": st.st_size,
                        "allocated_bytes": st.st_blocks * 512,
                    })

    # Current rendered MP4 identical to publish/video.mp4 -> dehydrate into storage-hydration.json
    plan_mp4_dehydrate = []
    cur_mp4_raw = cur_data.get("path")
    if cur_mp4_raw:
        cur_mp4 = Path(cur_mp4_raw)
        if not cur_mp4.is_absolute():
            cur_mp4 = (project / cur_mp4).resolve()
        if cur_mp4.is_file() and not cur_mp4.is_symlink() and cur_mp4.is_relative_to(project):
            if sha256_file(cur_mp4) == pub_sha:
                st = cur_mp4.lstat()
                plan_mp4_dehydrate.append({
                    "path": str(cur_mp4),
                    "rel_path": str(cur_mp4.relative_to(project)),
                    "source_rel": str(pub_video.relative_to(workspace)),
                    "sha256": pub_sha,
                    "size": st.st_size,
                    "allocated_bytes": st.st_blocks * 512,
                })

    summary = {
        "mix_history_dirs": len(plan_mix_history),
        "mix_history_bytes": sum(x["allocated_bytes"] for x in plan_mix_history),
        "qa_pruned_files": len(plan_qa_prune),
        "qa_pruned_bytes": sum(x["allocated_bytes"] for x in plan_qa_prune),
        "audio_flac_files": len(plan_audio_flac),
        "audio_flac_source_bytes": sum(x["allocated_bytes"] for x in plan_audio_flac),
        "assets_dehydrated_files": len(plan_asset_dehydrate),
        "assets_dehydrated_bytes": sum(x["allocated_bytes"] for x in plan_asset_dehydrate),
        "mp4_dehydrated_files": len(plan_mp4_dehydrate),
        "mp4_dehydrated_bytes": sum(x["allocated_bytes"] for x in plan_mp4_dehydrate),
    }

    if not apply:
        return {"status": "planned", "project": str(project), "series_id": sid, "episode_id": eid, "summary": summary}

    retention.assert_idle(workspace)

    # 1. Convert WAVs to verified exact-restore FLAC first and register compaction + hydration
    audio_bytes_saved = 0
    for row in plan_audio_flac:
        wav = Path(row["source"])
        conv = convert_wav({
            "source": row["source"],
            "target": row["target"],
            "kind": "audio_sealed",
            "allocated_bytes": row["allocated_bytes"],
            "size": row["size"],
            "mtime_ns": row["mtime_ns"],
        })
        comp_path = wav.parent / "storage-compaction.json"
        prev = read_json(comp_path) if comp_path.is_file() else {
            "schema": "medical_video_storage_compaction_group/v1",
            "records": [],
        }
        prev["records"] = [r for r in prev["records"] if r.get("source") != str(wav)] + [conv]
        prev["necessity_policy"] = "sealed_published_episode_lossless_recoverable"
        write_json(comp_path, prev)
        hydration_by_rel[row["rel_path"]] = {
            "kind": "flac_audio",
            "rel_path": row["rel_path"],
            "archive_rel": row["archive_rel"],
            "sha256": conv["source_sha256"],
            "size": row["size"],
        }
        audio_bytes_saved += row["allocated_bytes"] - conv["target_allocated_bytes"]

    # 2. Register dehydrated assets & MP4 in storage-hydration.json BEFORE removing duplicates
    for item in plan_asset_dehydrate + plan_mp4_dehydrate:
        hydration_by_rel[item["rel_path"]] = {
            "kind": "clone_from_workspace",
            "rel_path": item["rel_path"],
            "source_rel": item["source_rel"],
            "sha256": item["sha256"],
            "size": item["size"],
        }

    if hydration_by_rel:
        write_json(project / HYDRATION_FILE, {
            "schema": SCHEMA_HYDRATION,
            "sealed_at": stamp(),
            "series_id": sid,
            "episode_id": eid,
            "published_video_rel": str(pub_video.relative_to(workspace)),
            "published_video_sha256": pub_sha,
            "entries": sorted(hydration_by_rel.values(), key=lambda e: e["rel_path"]),
        })

    # 3. Now safely unlink replaced WAVs, dehydrated clones, mix-history, and heavy qa screenshots
    for row in plan_audio_flac:
        Path(row["source"]).unlink(missing_ok=True)
    for item in plan_asset_dehydrate + plan_mp4_dehydrate:
        Path(item["path"]).unlink(missing_ok=True)
    for mh in plan_mix_history:
        shutil.rmtree(Path(mh["path"]))
    for qf in plan_qa_prune:
        Path(qf["path"]).unlink(missing_ok=True)

    # Clean up empty dirs under project/assets/
    if assets_dir.is_dir():
        for dp, _dns, _fns in os.walk(assets_dir, topdown=False, followlinks=False):
            d = Path(dp)
            if d != assets_dir:
                try:
                    d.rmdir()
                except OSError:
                    pass

    summary["audio_bytes_saved"] = audio_bytes_saved
    summary["total_logical_bytes_reduced"] = (
        summary["mix_history_bytes"]
        + summary["qa_pruned_bytes"]
        + audio_bytes_saved
        + summary["assets_dehydrated_bytes"]
        + summary["mp4_dehydrated_bytes"]
    )
    return {"status": "sealed", "project": str(project), "series_id": sid, "episode_id": eid, "summary": summary}


def retire_revisions(
    workspace: Path,
    *,
    archive_path: Path | None = None,
    protected_projects: set[Path] | None = None,
    apply: bool = False,
) -> dict:
    """Archive lightweight creative/review lineage of superseded revisions, then retire their flat directories."""
    workspace = workspace.resolve()
    import plan_workspace_retention as retention

    wb_path = workspace / "workbench.yaml"
    wb_config = yaml.safe_load(wb_path.read_text(encoding="utf-8")) if wb_path.is_file() else {}
    active = set(_active_map(workspace, wb_config).keys())
    protected = set(active) | {p.resolve() for p in (protected_projects or set())}

    # Also protect any unregistered in-flight successor newer than current pointer without out/current.json
    for cur in list(active):
        m = VERSION_RE.match(cur.name)
        if not m:
            continue
        cur_num = int(m.group(1))
        for sibling in cur.parent.iterdir():
            sm = VERSION_RE.match(sibling.name)
            if sibling.is_dir() and sm and int(sm.group(1)) > cur_num:
                if (sibling / "dist/build-receipt.json").is_file() and not (sibling / "out/current.json").is_file():
                    protected.add(sibling.resolve())

    # Safety check: ensure no active delivery manifest points to a candidate retired revision
    delivery_projects: set[Path] = set()
    deliv_root = workspace / "deliveries"
    if deliv_root.is_dir():
        for mf in deliv_root.glob("*/*/manifest.json"):
            try:
                p = read_json(mf).get("project")
                if p:
                    delivery_projects.add(Path(p).resolve())
            except (OSError, ValueError):
                pass
    protected |= delivery_projects

    candidates = []
    prod_root = workspace / "productions"
    if prod_root.is_dir():
        for pj in sorted(prod_root.glob("*/*/*/project.json")):
            proj = pj.parent.resolve()
            if proj in protected:
                continue
            fc, al = dir_stats(proj)
            candidates.append({
                "project": str(proj),
                "relative_project": str(proj.relative_to(workspace)),
                "files": fc,
                "allocated_bytes": al,
            })

    total_files = sum(c["files"] for c in candidates)
    total_alloc = sum(c["allocated_bytes"] for c in candidates)

    if not apply:
        return {
            "status": "planned",
            "retired_revisions_count": len(candidates),
            "total_files": total_files,
            "total_allocated_bytes": total_alloc,
            "total_allocated_gib": round(total_alloc / 1024**3, 2),
            "protected_projects_count": len(protected),
            "samples": [c["relative_project"] for c in candidates[:10]],
        }

    retention.assert_idle(workspace)
    if archive_path is None:
        archive_path = workspace / f"archive/retired-revisions-lineage-{time.strftime('%Y%m%d')}.tar.gz"
    archive_path = archive_path.resolve()
    archive_path.parent.mkdir(parents=True, exist_ok=True)

    # 1. Pack 100% of lightweight creative/review lineage into verified tar.gz before deleting anything
    lineage_files = 0
    tmp_tar = archive_path.with_name(archive_path.name + ".tmp")
    try:
        with tarfile.open(tmp_tar, "w:gz", compresslevel=6) as tar:
            for item in candidates:
                proj = Path(item["project"])
                for dp, dns, fns in os.walk(proj, followlinks=False):
                    rel_dir = Path(dp).relative_to(proj)
                    if rel_dir == Path("."):
                        dns[:] = [d for d in dns if d not in LINEAGE_SKIP_DIRS and not (Path(dp) / d).is_symlink()]
                    elif rel_dir.parts[0] == "audio":
                        dns[:] = []  # skip mix-history & segments binary dirs
                    else:
                        dns[:] = [d for d in dns if d not in SKIP_DIRS and not (Path(dp) / d).is_symlink()]
                    for fn in sorted(fns):
                        p = Path(dp) / fn
                        if p.is_symlink() or not p.is_file():
                            continue
                        if rel_dir.parts and rel_dir.parts[0] == "audio" and fn not in LINEAGE_AUDIO_KEEP:
                            continue
                        if p.suffix.lower() not in LINEAGE_TEXT_EXTS:
                            continue
                        if p.stat().st_size > 2 * 1024 * 1024:
                            continue
                        tar.add(p, arcname=str(p.relative_to(workspace)))
                        lineage_files += 1
                # Also archive out/current.json if present
                cur_j = proj / "out/current.json"
                if cur_j.is_file() and not cur_j.is_symlink():
                    tar.add(cur_j, arcname=str(cur_j.relative_to(workspace)))
                    lineage_files += 1
        # Verify archive readability before replacing
        with tarfile.open(tmp_tar, "r:gz") as chk:
            verified_members = len(chk.getmembers())
        if verified_members != lineage_files:
            raise RuntimeError(f"Lineage archive member mismatch: {verified_members} != {lineage_files}")
        os.replace(tmp_tar, archive_path)
    finally:
        tmp_tar.unlink(missing_ok=True)

    archive_sha = sha256_file(archive_path)
    archive_size = archive_path.stat().st_size

    # 2. Remove retired revision directories
    removed = 0
    for item in candidates:
        proj = Path(item["project"])
        if proj in protected:
            raise RuntimeError(f"Refusing to delete protected project: {proj}")
        shutil.rmtree(proj)
        if proj.exists():
            raise RuntimeError(f"Failed to remove retired revision: {proj}")
        removed += 1

    return {
        "status": "retired",
        "retired_revisions_removed": removed,
        "total_files_removed": total_files,
        "total_allocated_bytes_reduced": total_alloc,
        "total_allocated_gib_reduced": round(total_alloc / 1024**3, 2),
        "lineage_archive": str(archive_path),
        "lineage_archive_sha256": archive_sha,
        "lineage_archive_files": lineage_files,
        "lineage_archive_size_bytes": archive_size,
        "lineage_archive_mib": round(archive_size / 1024**2, 2),
    }


def prune_archived_deliveries(workspace: Path, *, keep_latest: int = 1, apply: bool = False) -> dict:
    """Retain at most `keep_latest` newest rollback delivery backups per episode."""
    workspace = workspace.resolve()
    import plan_workspace_retention as retention

    if keep_latest < 0:
        raise ValueError("keep_latest must be >= 0")
    arch_root = workspace / "archive/deliveries"
    to_remove = []
    kept = 0
    if arch_root.is_dir():
        for sdir in sorted(arch_root.iterdir()):
            if not sdir.is_dir() or sdir.name.startswith("_"):
                continue
            for edir in sorted(sdir.iterdir()):
                if not edir.is_dir():
                    continue
                snaps = sorted([d for d in edir.iterdir() if d.is_dir()], key=lambda p: p.name)
                if len(snaps) <= keep_latest:
                    kept += len(snaps)
                    continue
                kept += keep_latest
                stale = snaps[: len(snaps) - keep_latest] if keep_latest > 0 else snaps
                for st_dir in stale:
                    fc, al = dir_stats(st_dir)
                    to_remove.append({
                        "path": str(st_dir),
                        "relative_path": str(st_dir.relative_to(workspace)),
                        "files": fc,
                        "allocated_bytes": al,
                    })

    total_files = sum(x["files"] for x in to_remove)
    total_alloc = sum(x["allocated_bytes"] for x in to_remove)
    if not apply:
        return {
            "status": "planned",
            "keep_latest": keep_latest,
            "snapshots_kept": kept,
            "snapshots_to_remove": len(to_remove),
            "files_to_remove": total_files,
            "allocated_bytes_to_reduce": total_alloc,
            "allocated_gib_to_reduce": round(total_alloc / 1024**3, 2),
        }

    retention.assert_idle(workspace)
    for item in to_remove:
        shutil.rmtree(Path(item["path"]))
    return {
        "status": "pruned",
        "keep_latest": keep_latest,
        "snapshots_kept": kept,
        "snapshots_removed": len(to_remove),
        "files_removed": total_files,
        "allocated_bytes_reduced": total_alloc,
        "allocated_gib_reduced": round(total_alloc / 1024**3, 2),
    }


def seal_all_published(workspace: Path, *, apply: bool = False, workers: int = 6) -> dict:
    """Seal all eligible published active episodes across the workspace."""
    workspace = workspace.resolve()
    import plan_workspace_retention as retention

    if apply:
        retention.assert_idle(workspace)
    wb_config = yaml.safe_load((workspace / "workbench.yaml").read_text(encoding="utf-8")) or {}
    active = _active_map(workspace, wb_config)
    global_index = build_global_asset_index(workspace)
    external_refs = _collect_external_qa_refs(workspace)

    projects = sorted(active.keys())
    results = []
    if apply and len(projects) > 4:
        with ThreadPoolExecutor(max_workers=workers) as pool:
            futs = {
                pool.submit(
                    seal_project,
                    proj,
                    workspace,
                    global_index=global_index,
                    wb_config=wb_config,
                    external_refs=external_refs,
                    apply=True,
                ): proj
                for proj in projects
            }
            for idx, fut in enumerate(as_completed(futs), 1):
                results.append(fut.result())
                if idx % 50 == 0:
                    print(json.dumps({"sealed_progress": idx, "total": len(projects)}), flush=True)
    else:
        for proj in projects:
            results.append(
                seal_project(
                    proj,
                    workspace,
                    global_index=global_index,
                    wb_config=wb_config,
                    external_refs=external_refs,
                    apply=apply,
                )
            )

    sealed_rows = [r for r in results if r["status"] in {"sealed", "planned"}]
    skipped_rows = [r for r in results if r["status"] not in {"sealed", "planned"}]
    totals = {
        "episodes_total": len(projects),
        "episodes_eligible": len(sealed_rows),
        "episodes_skipped": len(skipped_rows),
        "skipped_details": skipped_rows,
        "mix_history_bytes": sum(r["summary"]["mix_history_bytes"] for r in sealed_rows),
        "qa_pruned_files": sum(r["summary"]["qa_pruned_files"] for r in sealed_rows),
        "qa_pruned_bytes": sum(r["summary"]["qa_pruned_bytes"] for r in sealed_rows),
        "audio_flac_files": sum(r["summary"]["audio_flac_files"] for r in sealed_rows),
        "audio_flac_source_bytes": sum(r["summary"]["audio_flac_source_bytes"] for r in sealed_rows),
        "audio_bytes_saved": sum(r["summary"].get("audio_bytes_saved", 0) for r in sealed_rows),
        "assets_dehydrated_files": sum(r["summary"]["assets_dehydrated_files"] for r in sealed_rows),
        "assets_dehydrated_bytes": sum(r["summary"]["assets_dehydrated_bytes"] for r in sealed_rows),
        "mp4_dehydrated_files": sum(r["summary"]["mp4_dehydrated_files"] for r in sealed_rows),
        "mp4_dehydrated_bytes": sum(r["summary"]["mp4_dehydrated_bytes"] for r in sealed_rows),
        "total_logical_bytes_reduced": sum(r["summary"].get("total_logical_bytes_reduced", 0) for r in sealed_rows),
    }
    return {
        "schema": "medical_video_seal_batch/v1",
        "created_at": stamp(),
        "mode": "apply" if apply else "dry_run",
        "workspace": str(workspace),
        "totals": totals,
    }


def _devoff_of(path: Path) -> int | None:
    if sys.platform != "darwin":
        return None
    import fcntl
    try:
        fd = os.open(path, os.O_RDONLY)
        try:
            res = fcntl.fcntl(fd, F_LOG2PHYS, struct.pack("<Iqq", 0, 0, 0))
            _flags, _contig, devoff = struct.unpack("<Iqq", res)
            return devoff if devoff > 0 else None
        finally:
            os.close(fd)
    except OSError:
        return None


def storage_report(workspace: Path) -> dict:
    """Fast read-only dual-metric storage report: logical du vs unique APFS physical blocks."""
    workspace = workspace.resolve()
    seen_global: set[tuple[int, int]] = set()
    per_top: dict[str, list[int]] = collections.defaultdict(lambda: [0, 0, 0])
    total_files = total_logical = total_unique_phys = 0

    for entry in sorted(workspace.iterdir(), key=lambda p: p.name):
        top = entry.name
        seen_top: set[tuple[int, int]] = set()
        if entry.is_symlink():
            continue
        if entry.is_file():
            try:
                al = entry.lstat().st_blocks * 512
            except OSError:
                continue
            per_top[top][0] += 1
            per_top[top][1] += al
            per_top[top][2] += al
            total_files += 1
            total_logical += al
            total_unique_phys += al
            continue
        for dp, dns, fns in os.walk(entry, followlinks=False):
            dns[:] = [d for d in dns if not (Path(dp) / d).is_symlink()]
            for fn in fns:
                p = Path(dp) / fn
                if p.is_symlink():
                    continue
                try:
                    al = p.lstat().st_blocks * 512
                except OSError:
                    continue
                per_top[top][0] += 1
                per_top[top][1] += al
                total_files += 1
                total_logical += al
                devoff = _devoff_of(p) if al > 0 else None
                key = (devoff, al) if devoff is not None else None
                if key is None or key not in seen_top:
                    if key is not None:
                        seen_top.add(key)
                    per_top[top][2] += al
                if key is None or key not in seen_global:
                    if key is not None:
                        seen_global.add(key)
                    total_unique_phys += al

    vfs = os.statvfs(workspace)
    return {
        "schema": "medical_video_storage_report/v1",
        "created_at": stamp(),
        "workspace": str(workspace),
        "platform": sys.platform,
        "total_files": total_files,
        "total_logical_alloc_bytes": total_logical,
        "total_logical_alloc_gib": round(total_logical / 1024**3, 2),
        "total_unique_physical_bytes": total_unique_phys,
        "total_unique_physical_gib": round(total_unique_phys / 1024**3, 2),
        "disk_free_bytes": vfs.f_bavail * vfs.f_frsize,
        "by_top_dir": {
            k: {
                "files": v[0],
                "logical_bytes": v[1],
                "logical_gib": round(v[1] / 1024**3, 2),
                "unique_phys_bytes": v[2],
                "unique_phys_gib": round(v[2] / 1024**3, 2),
            }
            for k, v in sorted(per_top.items(), key=lambda x: -x[1][1])
            if v[1] >= 1024 * 1024
        },
    }


def cow_dedup(workspace: Path, *, min_size: int = 65536, apply: bool = False) -> dict:
    """Safe atomic APFS Copy-on-Write (clonefile) physical block deduplication."""
    workspace = workspace.resolve()
    if sys.platform != "darwin":
        return {"status": "skipped_unsupported_platform", "platform": sys.platform}
    import plan_workspace_retention as retention

    if apply:
        retention.assert_idle(workspace)

    libc = ctypes.CDLL("/usr/lib/libSystem.B.dylib")
    clonefile_fn = libc.clonefile
    clonefile_fn.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
    clonefile_fn.restype = ctypes.c_int

    by_size: dict[int, list[tuple[Path, int]]] = collections.defaultdict(list)
    scanned = 0
    for rel_root in COW_SCAN_DIRS:
        root = workspace / rel_root
        if not root.exists():
            continue
        for dp, dns, fns in os.walk(root, followlinks=False):
            dns[:] = [d for d in dns if d not in SKIP_DIRS and not (Path(dp) / d).is_symlink()]
            for fn in fns:
                p = Path(dp) / fn
                if p.is_symlink():
                    continue
                try:
                    st = p.lstat()
                except OSError:
                    continue
                scanned += 1
                if st.st_size >= min_size and st.st_nlink == 1:
                    by_size[st.st_size].append((p, st.st_blocks * 512))

    candidates = [p for items in by_size.values() if len(items) > 1 for p, _ in items]
    sha_map: dict[Path, str] = {}
    if candidates:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for p, digest in zip(candidates, pool.map(sha256_file, candidates)):
                sha_map[p] = digest

    groups: dict[tuple[int, str], list[Path]] = collections.defaultdict(list)
    for sz, items in by_size.items():
        if len(items) <= 1:
            continue
        for p, _ in items:
            digest = sha_map.get(p)
            if digest:
                groups[(sz, digest)].append(p)

    deduped = already_shared = reclaimed_bytes = 0
    errors = []
    for (sz, expected_sha), paths in groups.items():
        if len(paths) <= 1:
            continue
        paths.sort(key=lambda p: (0 if p.relative_to(workspace).parts[0] == "assets" else 1, str(p)))
        canonical = paths[0]
        canon_devoff = _devoff_of(canonical)
        if canon_devoff is None:
            continue
        for target in paths[1:]:
            try:
                cur_devoff = _devoff_of(target)
                if cur_devoff == canon_devoff:
                    already_shared += 1
                    continue
                st_before = target.lstat()
                if st_before.st_size != sz or st_before.st_nlink != 1:
                    continue
                alloc = st_before.st_blocks * 512
                if not apply:
                    deduped += 1
                    reclaimed_bytes += alloc
                    continue
                tmp = target.with_name(f".{target.name}.{os.getpid()}.cowtmp")
                try:
                    rc = clonefile_fn(os.fsencode(canonical), os.fsencode(tmp), 0)
                    if rc != 0:
                        raise OSError(f"clonefile failed rc={rc}")
                    if sha256_file(tmp) != expected_sha:
                        raise RuntimeError("cloned SHA mismatch")
                    if os.path.samefile(canonical, tmp) or tmp.lstat().st_nlink != 1:
                        raise RuntimeError("clone unexpectedly shared inode or hardlinked")
                    os.chmod(tmp, st_before.st_mode & 0o7777)
                    os.utime(tmp, ns=(st_before.st_atime_ns, st_before.st_mtime_ns))
                    os.replace(tmp, target)
                finally:
                    if tmp.exists() or tmp.is_symlink():
                        tmp.unlink(missing_ok=True)
                if _devoff_of(target) != canon_devoff:
                    raise RuntimeError("devoff did not converge")
                deduped += 1
                reclaimed_bytes += alloc
            except Exception as exc:
                errors.append({"path": str(target), "error": str(exc)})

    return {
        "schema": "medical_video_apfs_cow_dedup/v1",
        "status": "deduped" if apply else "planned",
        "created_at": stamp(),
        "scanned_files": scanned,
        "hashed_candidates": len(candidates),
        "deduped_files": deduped,
        "already_shared_files": already_shared,
        "reclaimed_physical_bytes": reclaimed_bytes,
        "reclaimed_physical_gib": round(reclaimed_bytes / 1024**3, 2),
        "errors": errors,
    }


def _has_active_pending_queue(directory: Path) -> bool:
    for q in directory.glob("*queue*.json"):
        try:
            data = read_json(q)
            items = data if isinstance(data, list) else (
                data.get("episodes") or data.get("items") or data.get("queue") or []
            )
            if isinstance(items, list) and len(items) > 0:
                return True
        except (OSError, ValueError, TypeError):
            continue
    return False


def prune_work_caches(
    workspace: Path,
    *,
    targets: list[str] | None = None,
    all_completed: bool = False,
    prune_root_scratch: bool = False,
    apply: bool = False,
) -> dict:
    """Prune transient binary media caches in completed work/ campaigns while keeping all scripts/docs/queues."""
    workspace = workspace.resolve()
    import plan_workspace_retention as retention

    if apply:
        retention.assert_idle(workspace)

    work_root = workspace / "work"
    selected_dirs: list[Path] = []
    skipped_protected: list[str] = []

    if work_root.is_dir():
        if targets:
            for name in targets:
                cand = (work_root / name).resolve()
                if not cand.is_relative_to(work_root) or not cand.is_dir():
                    raise ValueError(f"Invalid work target directory: {name}")
                selected_dirs.append(cand)
        elif all_completed:
            for child in sorted(work_root.iterdir()):
                if not child.is_dir() or child.is_symlink():
                    continue
                if child.name in WORK_PROTECTED_NAMES or child.name.startswith(WORK_PROTECTED_PREFIXES):
                    skipped_protected.append(child.name)
                    continue
                if _has_active_pending_queue(child):
                    skipped_protected.append(child.name)
                    continue
                selected_dirs.append(child)

    records = []
    total_files = total_alloc = 0
    for root_dir in selected_dirs:
        fc = al = 0
        for dp, dns, fns in os.walk(root_dir, topdown=False, followlinks=False):
            for fn in fns:
                p = Path(dp) / fn
                if p.is_symlink() or not p.is_file():
                    continue
                if p.suffix.lower() in WORK_PRUNABLE_MEDIA_EXTS or p.name == ".DS_Store":
                    al += p.lstat().st_blocks * 512
                    fc += 1
                    if apply:
                        p.unlink()
            for dn in dns:
                sub = Path(dp) / dn
                if sub.is_dir() and not sub.is_symlink():
                    if dn == "__pycache__":
                        sfc, sal = dir_stats(sub)
                        fc += sfc
                        al += sal
                        if apply:
                            shutil.rmtree(sub)
                    elif apply:
                        try:
                            sub.rmdir()
                        except OSError:
                            pass
        if fc > 0:
            total_files += fc
            total_alloc += al
            records.append({
                "path": str(root_dir.relative_to(workspace)),
                "files": fc,
                "allocated_bytes": al,
            })

    if prune_root_scratch:
        wb_text = (workspace / "workbench.yaml").read_text(encoding="utf-8") if (workspace / "workbench.yaml").is_file() else ""
        for rname in ("qa", "out", "tmp", "review"):
            rd = workspace / rname
            if rd.is_dir() and not rd.is_symlink() and f": {rname}" not in wb_text:
                fc, al = dir_stats(rd)
                if fc > 0:
                    total_files += fc
                    total_alloc += al
                    records.append({"path": rname, "files": fc, "allocated_bytes": al, "kind": "root_scratch"})
                    if apply:
                        shutil.rmtree(rd)

    return {
        "schema": "medical_video_work_cache_prune/v1",
        "status": "pruned" if apply else "planned",
        "created_at": stamp(),
        "skipped_protected_dirs": skipped_protected,
        "total_files": total_files,
        "total_allocated_bytes": total_alloc,
        "total_allocated_gib": round(total_alloc / 1024**3, 2),
        "records": records,
    }


def clean_dangling_node_modules_symlinks(workspace: Path, *, apply: bool = False) -> dict:
    """Detect and optionally remove broken legacy node_modules symlinks inside productions/."""
    workspace = workspace.resolve()
    prod_root = workspace / "productions"
    found = []
    if prod_root.is_dir():
        for dp, dns, fns in os.walk(prod_root, followlinks=False):
            for name in list(dns) + list(fns):
                if name != "node_modules":
                    continue
                p = Path(dp) / name
                if p.is_symlink() and not p.exists():
                    found.append({"path": str(p.relative_to(workspace)), "broken_target": os.readlink(p)})
                    if apply:
                        p.unlink()
    return {
        "status": "cleaned" if apply else "planned",
        "count": len(found),
        "samples": found[:20],
    }


def optimize_workspace(
    workspace: Path,
    *,
    keep_latest_deliveries: int | None = None,
    include_retire: bool = True,
    include_seal: bool = True,
    include_cow_dedup: bool = True,
    include_work_prune: bool = False,
    prune_root_scratch: bool = False,
    apply: bool = False,
    output_dir: Path | None = None,
) -> dict:
    """One-command autonomous storage optimization orchestrating all lifecycle stages with receipts."""
    workspace = workspace.resolve()
    import plan_workspace_retention as retention

    if apply:
        retention.assert_idle(workspace)

    wb_path = workspace / "workbench.yaml"
    wb_config = yaml.safe_load(wb_path.read_text(encoding="utf-8")) if wb_path.is_file() else {}
    if keep_latest_deliveries is None:
        keep_latest_deliveries = int((wb_config.get("delivery_policy") or {}).get("archive_keep_latest", 1))

    if output_dir is None:
        output_dir = workspace / f"work/disk-lifecycle-{time.strftime('%Y%m%d')}"
    output_dir = output_dir.resolve()

    before_report = storage_report(workspace)
    before_health = retention.check_health(workspace)

    stages: dict[str, dict] = {}
    stages["dangling_symlinks"] = clean_dangling_node_modules_symlinks(workspace, apply=apply)

    # Retention plan + apply (node_modules, render_temporary, review_frame, audio, orphan_take, superseded_render)
    ret_plan = retention.plan(workspace, {"protected_projects": []})
    actionable_parts = sorted({
        r["category"]
        for r in ret_plan["decisions"]
        if r["category"] in {"node_modules", "render_temporary", "review_frame", "audio", "orphan_take", "superseded_render"}
        and (r["decision"].startswith("delete") or r.get("target"))
    })
    if apply and actionable_parts:
        output_dir.mkdir(parents=True, exist_ok=True)
        plan_gz = output_dir / "optimize-retention-plan.json.gz"
        apply_gz = output_dir / "optimize-retention-apply.json.gz"
        retention.write(plan_gz, ret_plan)
        retention.apply(plan_gz, apply_gz, parts=set(actionable_parts))
        stages["retention"] = {
            "status": "applied",
            "parts": actionable_parts,
            "summary": retention.read(apply_gz)["summary"],
        }
    else:
        stages["retention"] = {
            "status": "planned" if actionable_parts else "clean",
            "parts": actionable_parts,
            "summary": ret_plan["summary"],
        }

    # Compress bulky > 2 MiB plain-text lifecycle logs under work/disk-lifecycle-*
    big_logs = []
    if (workspace / "work").is_dir():
        for d in sorted((workspace / "work").glob("disk-lifecycle-*")):
            if not d.is_dir():
                continue
            for p in sorted(d.rglob("*")):
                if p.is_file() and not p.is_symlink() and p.suffix in {".json", ".jsonl"} and p.stat().st_size > 2 * 1024 * 1024:
                    big_logs.append(p)
                    if apply:
                        retention.compress_log_file(p)
    stages["lifecycle_logs"] = {"status": "compressed" if apply else "planned", "files": len(big_logs)}

    stages["delivery_archives"] = prune_archived_deliveries(workspace, keep_latest=keep_latest_deliveries, apply=apply)
    if include_retire:
        stages["retire_revisions"] = retire_revisions(workspace, apply=apply)
    if include_seal:
        stages["seal_published"] = seal_all_published(workspace, apply=apply)
    if include_work_prune or prune_root_scratch:
        stages["work_caches"] = prune_work_caches(
            workspace, all_completed=include_work_prune, prune_root_scratch=prune_root_scratch, apply=apply
        )
    if include_cow_dedup:
        stages["cow_dedup"] = cow_dedup(workspace, apply=apply)

    after_health = retention.check_health(workspace) if apply else before_health
    after_report = storage_report(workspace) if apply else before_report

    result = {
        "schema": "medical_video_workspace_optimize/v1",
        "created_at": stamp(),
        "mode": "apply" if apply else "dry_run",
        "workspace": str(workspace),
        "before": {
            "logical_gib": before_report["total_logical_alloc_gib"],
            "unique_physical_gib": before_report["total_unique_physical_gib"],
            "total_files": before_report["total_files"],
            "health_status": before_health["status"],
            "findings_count": len(before_health["findings"]),
        },
        "after": {
            "logical_gib": after_report["total_logical_alloc_gib"],
            "unique_physical_gib": after_report["total_unique_physical_gib"],
            "total_files": after_report["total_files"],
            "health_status": after_health["status"],
            "findings_count": len(after_health["findings"]),
            "findings": after_health["findings"],
        },
        "stages": stages,
    }
    if apply:
        output_dir.mkdir(parents=True, exist_ok=True)
        write_json(output_dir / "optimize-receipt.json", result)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    for cmd in ("seal", "hydrate"):
        p = sub.add_parser(cmd)
        p.add_argument("--workspace", type=Path, required=True)
        p.add_argument("--project", type=Path, required=True)
        if cmd == "seal":
            p.add_argument("--apply", action="store_true")

    p = sub.add_parser("seal-all")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--workers", type=int, default=6)
    p.add_argument("--output", type=Path)

    p = sub.add_parser("retire-revisions")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--archive", type=Path)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--output", type=Path)

    p = sub.add_parser("prune-delivery-archives")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--keep-latest", type=int, default=1)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--output", type=Path)

    p = sub.add_parser("cow-dedup")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--min-size", type=int, default=65536)
    p.add_argument("--apply", action="store_true")
    p.add_argument("--output", type=Path)

    p = sub.add_parser("prune-work")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--target", action="append", help="Explicit work/<subdir> name(s) to prune binary media caches from")
    p.add_argument("--all-completed", action="store_true", help="Prune completed non-protected work/ subdirs without active pending queues")
    p.add_argument("--prune-root-scratch", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--output", type=Path)

    p = sub.add_parser("report")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--output", type=Path)

    p = sub.add_parser("optimize")
    p.add_argument("--workspace", type=Path, required=True)
    p.add_argument("--keep-latest-deliveries", type=int)
    p.add_argument("--no-retire", action="store_true")
    p.add_argument("--no-seal", action="store_true")
    p.add_argument("--no-cow-dedup", action="store_true")
    p.add_argument("--include-work-prune", action="store_true")
    p.add_argument("--prune-root-scratch", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--output", type=Path)

    args = parser.parse_args()
    ws = args.workspace.resolve()
    if args.command == "seal":
        res = seal_project(args.project, ws, apply=args.apply)
    elif args.command == "hydrate":
        res = hydrate_project(args.project, ws)
    elif args.command == "seal-all":
        res = seal_all_published(ws, apply=args.apply, workers=args.workers)
    elif args.command == "retire-revisions":
        res = retire_revisions(ws, archive_path=args.archive, apply=args.apply)
    elif args.command == "prune-delivery-archives":
        res = prune_archived_deliveries(ws, keep_latest=args.keep_latest, apply=args.apply)
    elif args.command == "cow-dedup":
        res = cow_dedup(ws, min_size=args.min_size, apply=args.apply)
    elif args.command == "prune-work":
        res = prune_work_caches(
            ws,
            targets=args.target,
            all_completed=args.all_completed,
            prune_root_scratch=args.prune_root_scratch,
            apply=args.apply,
        )
    elif args.command == "report":
        res = storage_report(ws)
    else:
        res = optimize_workspace(
            ws,
            keep_latest_deliveries=args.keep_latest_deliveries,
            include_retire=not args.no_retire,
            include_seal=not args.no_seal,
            include_cow_dedup=not args.no_cow_dedup,
            include_work_prune=args.include_work_prune,
            prune_root_scratch=args.prune_root_scratch,
            apply=args.apply,
        )

    if getattr(args, "output", None):
        write_json(args.output, res)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
