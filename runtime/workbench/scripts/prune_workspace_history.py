#!/usr/bin/env python3
"""Keep the medical-video workspace current, compact, and free of stale versions.

The workbench episode pointer is the production authority.  The publisher tree
is already latest-only and is never modified here.  A newer built revision than
the current pointer is treated as in-flight rework and is protected.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path

import yaml


VERSION = re.compile(r"^v(\d+)$")
LEDGER = Path("work/season-directing-20261016/episode-rework-status.md")
MANIFEST = Path("work/workspace-current.json")
REPORT = Path("work/workspace-prune-report.json")

# Review visuals are reproducible from the current source, score and media.
# Keep compact visual summaries that are useful during a handoff; raw frame
# sheets and encoded review candidates are removed after their JSON/Markdown
# conclusions have been retained.
REVIEW_TEXT_SUFFIXES = {".json", ".md", ".txt", ".log", ".yaml", ".yml", ".srt"}
REVIEW_COMPACT_IMAGE_DIRS = {"clean-overviews", "motion-overviews", "cuts"}
REVIEW_COMPACT_IMAGE_FILES = {"flagged-motion.jpg"}

# These roots are reproducible review/runtime caches or superseded workspaces.
# Their compact textual conclusions are already represented by the current
# directing review and workbench records.
PRUNABLE_WORK_ROOTS = {
    "work/animation-lab",
    "work/audit-20261014",
    "work/audit-20261015",
    "work/component-examples",
    "work/diabetes-s01",
    "work/four-seasons-paper-renewal",
    "work/hypertension-s01",
    "work/keyframe-library-20260909",
    "work/label-align-audit",
    "work/library-acceptance-20260930",
    "work/lipids-s01",
    "work/mac-media-assets",
    "work/pituitary-paper-season",
    "work/qa",
    "work/qa-frames",
    "work/series-completion-review",
    "work/series-diversity",
    "work/six-new-paper-series",
    "work/voxcpm2-workflow-acceptance",
    "work/weight-lipids-diversity-v2",
    "work/weight-management-s01",
    "docs/reserve-2026-10-11",
    "deliveries/hypertension_s01",
}


def sha256(path: Path) -> str | None:
    if not path.is_file():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def size(path: Path) -> int:
    if path.is_file() or path.is_symlink():
        try:
            return path.lstat().st_size
        except OSError:
            return 0
    if not path.is_dir():
        return 0
    total = 0
    for root, _, files in path.walk():
        for name in files:
            child = Path(root) / name
            try:
                total += child.lstat().st_size
            except OSError:
                pass
    return total


def remove(path: Path, apply: bool, bucket: dict) -> None:
    if not path.exists() and not path.is_symlink():
        return
    bucket["files"] += 1
    bucket["bytes"] += size(path)
    bucket["paths"].append(str(path))
    if apply:
        if path.is_dir() and not path.is_symlink():
            shutil.rmtree(path)
        else:
            path.unlink(missing_ok=True)


def version_number(path: Path) -> int | None:
    match = VERSION.match(path.name)
    return int(match.group(1)) if match else None


def read_ledger_projects(root: Path) -> set[Path]:
    result: set[Path] = set()
    if not LEDGER.is_file():
        return result
    text = LEDGER.read_text(encoding="utf-8")
    for match in re.finditer(r"`(productions/[^`]+/v\d+)`", text):
        result.add((root / match.group(1)).resolve())
    return result


def build_model(root: Path) -> dict:
    data = yaml.safe_load((root / "workbench.yaml").read_text(encoding="utf-8")) or {}
    series = data.get("series", {})
    protected: dict[Path, dict] = {}
    current_projects: set[Path] = set()
    production_roots: set[Path] = set()
    episode_owners: dict[Path, set[str]] = {}

    for series_id, config in series.items():
        production_root = (root / str(config.get("production_root", f"productions/{series_id}"))).resolve()
        production_roots.add(production_root)
        for episode_id, episode in (config.get("episodes") or {}).items():
            project = (root / str(episode["project"])).resolve()
            current_projects.add(project)
            episode_owners.setdefault(project.parent, set()).add(episode_id)
            protected[project] = {"series": series_id, "episode": episode_id, "role": "current"}

    for project in read_ledger_projects(root):
        if project.is_dir():
            protected.setdefault(project, {"series": None, "episode": project.parent.name, "role": "rework_ledger"})

    # Protect the newest built successor when it is newer than the pointer.
    # This keeps an in-flight revision without retaining the whole v1..vN chain.
    for project in list(current_projects):
        current_n = version_number(project)
        if current_n is None:
            continue
        successors = []
        for candidate in project.parent.iterdir():
            number = version_number(candidate)
            if candidate.is_dir() and number is not None and number > current_n:
                successors.append((number, candidate.resolve()))
        for number, candidate in sorted(successors, reverse=True):
            # An unregistered successor is in-flight only while it has not
            # produced a current pointer. Once independently rendered with
            # out/current.json, it is a complete revision that can be
            # archived on purpose, not silently retained as protected.
            if (
                (candidate / "dist/build-receipt.json").is_file()
                and not (candidate / "out/current.json").is_file()
            ):
                protected[candidate] = {
                    "series": protected[project]["series"],
                    "episode": protected[project]["episode"],
                    "role": "in_flight_successor",
                }
                break

    return {
        "data": data,
        "series": series,
        "protected": protected,
        "current_projects": current_projects,
        "production_roots": production_roots,
        "episode_owners": episode_owners,
    }


def snapshot(root: Path, model: dict) -> dict:
    projects = []
    for project, owner in sorted(model["protected"].items(), key=lambda item: str(item[0])):
        current = root / "out/current.json"
        render = None
        if (project / "out/current.json").is_file():
            current = project / "out/current.json"
        if current.is_file():
            try:
                payload = json.loads(current.read_text(encoding="utf-8"))
                render = payload.get("path")
            except (OSError, json.JSONDecodeError):
                pass
        projects.append({
            "path": str(project.relative_to(root)),
            "owner": owner,
            "project_sha256": sha256(project / "project.json"),
            "score_sha256": sha256(project / "score.json"),
            "bundle_sha256": sha256(project / "dist/film.js"),
            "audio_sha256": sha256(project / "audio.wav"),
            "render": render,
            "render_sha256": sha256(Path(render)) if render and Path(render).is_absolute() else None,
        })

    published = []
    for path in sorted((root / "publish").glob("*/*/video.mp4")):
        published.append({
            "path": str(path.relative_to(root)),
            "bytes": path.stat().st_size,
            "sha256": sha256(path),
        })
    return {
        "schema": "medical_workspace_current/v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "workbench_sha256": sha256(root / "workbench.yaml"),
        "projects": projects,
        "published_videos": published,
    }


def prune_project(project: Path, apply: bool, bucket: dict, *, remove_dependencies: bool = False) -> None:
    current = project / "out/current.json"
    keep_render = None
    if current.is_file():
        try:
            payload = json.loads(current.read_text(encoding="utf-8"))
            candidate = Path(str(payload.get("path", "")))
            if candidate.is_absolute() and candidate.is_file():
                keep_render = candidate
        except (OSError, json.JSONDecodeError):
            pass
    if keep_render is None and (project / "out").is_dir():
        # A stale pointer must not turn cleanup into media loss.  Retain the
        # newest encoded file until the next successful render replaces it.
        candidates = sorted(
            (project / "out").glob("*.mp4"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            keep_render = candidates[0]

    out = project / "out"
    if out.is_dir():
        for child in sorted(out.iterdir()):
            if child.name == "current.json":
                continue
            if keep_render and child.resolve() == keep_render.resolve():
                continue
            if keep_render and child.is_file():
                if child.name == keep_render.stem + ".receipt.json":
                    continue
                if child.with_suffix("").resolve() == keep_render.with_suffix("").resolve():
                    continue
            remove(child, apply, bucket)

    qa = project / "qa"
    if qa.is_dir():
        for child in sorted(qa.iterdir()):
            if child.name == "asset-reviews":
                continue
            if child.is_file() and child.suffix.lower() in {".json", ".md"}:
                continue
            remove(child, apply, bucket)

    if remove_dependencies:
        for node in project.rglob("node_modules"):
            remove(node, apply, bucket)
    for node in project.rglob("__pycache__"):
        remove(node, apply, bucket)


def prune_review_artifacts(root: Path, apply: bool, bucket: dict) -> None:
    """Retain textual review conclusions and compact visual summaries only."""
    review = root / "work/review"
    if not review.is_dir():
        return
    stamp = datetime.now(timezone.utc).isoformat()
    for path in sorted(review.rglob("*"), reverse=True):
        if not path.is_file():
            continue
        relative = path.relative_to(review)
        if path.suffix.lower() in REVIEW_TEXT_SUFFIXES:
            if path.name == "preview.json" and apply:
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                    payload["raw_visuals_pruned"] = True
                    payload["raw_visuals_pruned_at"] = stamp
                    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                except (OSError, UnicodeError, json.JSONDecodeError):
                    pass
            continue
        if path.name in REVIEW_COMPACT_IMAGE_FILES or any(
            part in REVIEW_COMPACT_IMAGE_DIRS for part in relative.parts
        ):
            continue
        remove(path, apply, bucket)


def prune_preview_caches(root: Path, apply: bool, bucket: dict) -> None:
    work = root / "work"
    if not work.is_dir():
        return
    for base in sorted(work.glob("season-directing-*")):
        if not base.is_dir():
            continue
        for episode_dir in base.iterdir():
            if not episode_dir.is_dir() or not (
                episode_dir.name.startswith("preview-")
                or "-rework-previews" in episode_dir.name
            ):
                continue
            for child in episode_dir.iterdir():
                if child.is_file() and (
                    child.name == "contact.jpg"
                    or child.name == "preview.json"
                    or re.fullmatch(r"strip-s\d+(?:-r\d+)?\.jpg", child.name)
                ):
                    continue
                remove(child, apply, bucket)

        # Root-level encoded previews and concat manifests are reproducible
        # from the current project; keep review documents and contact/strip files.
        for child in base.iterdir():
            if child.name.startswith("encoded-") or (
                child.is_file() and child.suffix.lower() in {".mp4", ".ffconcat"}
            ):
                remove(child, apply, bucket)


def plan(root: Path, apply: bool) -> dict:
    model = build_model(root)
    missing = [str(project) for project in model["protected"] if not project.is_dir()]
    if missing:
        raise RuntimeError("受保护工程缺失，拒绝执行清理：" + ", ".join(missing[:8]))
    published = list((root / "publish").glob("*/*/video.mp4"))
    if len(published) != len(model["current_projects"]):
        raise RuntimeError(
            f"用户交付数量 {len(published)} 与当前工程数量 {len(model['current_projects'])} 不一致，拒绝清理"
        )
    bucket = {"files": 0, "bytes": 0, "paths": []}

    protected = set(model["protected"])
    for project in model["current_projects"]:
        current_n = version_number(project)
        for candidate in project.parent.iterdir():
            if candidate.is_dir() and version_number(candidate) is not None and candidate.resolve() not in protected:
                if current_n is not None and version_number(candidate) < current_n:
                    remove(candidate, apply, bucket)
        prune_project(project, apply, bucket, remove_dependencies=False)

    for project in protected:
        if project not in model["current_projects"]:
            prune_project(project, apply, bucket, remove_dependencies=True)

    for production_root in model["production_roots"]:
        if not production_root.is_dir():
            continue
        keep_ids = set()
        for project in protected:
            # workbench.yaml points production_root at the series directory;
            # an episode project is series/<episode>/<version>.
            if project.parent.parent == production_root:
                keep_ids.add(project.parent.name)
        for child in sorted(production_root.iterdir()):
            has_protected_descendant = any(
                project.is_relative_to(child.resolve()) for project in protected
            )
            if child.is_dir() and child.name not in keep_ids and not has_protected_descendant:
                remove(child, apply, bucket)

    configured_delivery = set(model["series"].keys())
    deliveries = root / "deliveries"
    if deliveries.is_dir():
        for child in sorted(deliveries.iterdir()):
            if child.is_dir() and child.name not in configured_delivery:
                remove(child, apply, bucket)

    for relative in sorted(PRUNABLE_WORK_ROOTS):
        remove(root / relative, apply, bucket)

    productions = root / "productions"
    if productions.is_dir():
        for child in sorted(productions.iterdir()):
            if child.is_dir() and child.resolve() not in model["production_roots"]:
                remove(child, apply, bucket)

    prune_preview_caches(root, apply, bucket)
    prune_review_artifacts(root, apply, bucket)

    for relative in ("output", "tmp", "qa"):
        directory = root / relative
        if directory.is_dir():
            for child in sorted(directory.iterdir()):
                if child.is_dir() and not any(child.iterdir()):
                    # Keep the declared workspace layout even when its
                    # regenerable leaf is currently empty.
                    continue
                remove(child, apply, bucket)

    # Recoverable delivery history is intentionally retained. It is not a
    # reproducible preview cache, may be the only rollback copy of prior
    # manifests/attachments, and the user's archival contract requires it to
    # survive cleanup until an explicit migration turns it into another form.

    # Retain small TTS evaluation evidence but remove generated WAV payloads.
    tts_eval = root / "archive/tts-evaluation-20261013"
    if tts_eval.is_dir():
        for path in tts_eval.rglob("*"):
            if path.is_file() and path.suffix.lower() in {".wav", ".mp3", ".m4a", ".zip"}:
                remove(path, apply, bucket)

    # A cleanup plan must never remove a protected project or an ancestor of
    # one.  Child cache directories inside a protected project are allowed.
    dangerous = []
    for raw in bucket["paths"]:
        candidate = Path(raw).resolve()
        if any(candidate == project or project.is_relative_to(candidate) for project in protected):
            dangerous.append(raw)
    if dangerous:
        raise RuntimeError(
            "清理计划包含受保护工程或其祖先，拒绝执行：" + ", ".join(dangerous[:8])
        )

    result = {
        "schema": "medical_workspace_prune/v1",
        "mode": "apply" if apply else "dry_run",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "protected_projects": [str(p.relative_to(root)) for p in sorted(protected)],
        "removed_roots": bucket["paths"],
        "removed_entries": bucket["files"],
        "estimated_reclaim_bytes": bucket["bytes"],
        "estimated_reclaim_gib": round(bucket["bytes"] / 1024 ** 3, 3),
    }
    if apply:
        REPORT.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--apply", action="store_true", help="perform the destructive cleanup; default is dry-run")
    parser.add_argument("--refresh-manifest", action="store_true", help="write the compact current-version SHA manifest before pruning")
    args = parser.parse_args()
    root = args.workspace.resolve()
    if not (root / "workbench.yaml").is_file():
        raise SystemExit("需要明确的工作台根目录")
    if args.refresh_manifest:
        model = build_model(root)
        MANIFEST.write_text(json.dumps(snapshot(root, model), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    result = plan(root, args.apply)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
