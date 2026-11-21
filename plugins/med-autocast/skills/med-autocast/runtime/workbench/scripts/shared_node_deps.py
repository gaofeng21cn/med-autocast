#!/usr/bin/env python3
"""Workspace-shared Node.js build dependency pool keyed by lockfile fingerprint.

Avoids installing identical per-episode / per-revision `node_modules` copies
across hundreds of paper-theatre projects while keeping every project directory
free of `node_modules` copies and symlinks.
"""
from __future__ import annotations

import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover - non-POSIX fallback
    fcntl = None

SCHEMA = "medical_video_shared_node_deps/v1"
RESOLVER_SCRIPT = Path(__file__).resolve().with_name("shared_node_resolve.mjs")
DEP_SECTIONS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def declared_packages(project: Path) -> list[str]:
    pkg_path = project / "package.json"
    if not pkg_path.is_file():
        return []
    pkg = _read_json(pkg_path)
    names: set[str] = set()
    for section in ("dependencies", "devDependencies"):
        mapping = pkg.get(section)
        if isinstance(mapping, dict):
            names.update(str(k) for k in mapping)
    return sorted(names)


def dependency_fingerprint(project: Path) -> tuple[str, Path | None]:
    """Stable hash of resolved Node dependencies, independent of root kit version metadata."""
    project = project.resolve()
    lock_path = project / "package-lock.json"
    pkg_path = project / "package.json"
    platform_tag = {
        "platform": sys.platform,
        "machine": platform.machine(),
    }
    if lock_path.is_file():
        lock = _read_json(lock_path)
        packages = lock.get("packages")
        if isinstance(packages, dict):
            normalized_packages = {}
            for key, entry in packages.items():
                if key == "" and isinstance(entry, dict):
                    normalized_packages[""] = {
                        section: entry.get(section)
                        for section in (*DEP_SECTIONS, "engines")
                        if entry.get(section)
                    }
                else:
                    normalized_packages[key] = entry
            payload = {
                "lockfileVersion": lock.get("lockfileVersion"),
                "packages": normalized_packages,
                **platform_tag,
            }
        else:
            payload = {
                "lockfileVersion": lock.get("lockfileVersion"),
                "dependencies": lock.get("dependencies", {}),
                **platform_tag,
            }
        source = lock_path
    elif pkg_path.is_file():
        pkg = _read_json(pkg_path)
        payload = {
            section: pkg.get(section)
            for section in DEP_SECTIONS
            if pkg.get(section)
        }
        payload.update(platform_tag)
        source = pkg_path
    else:
        raise ValueError(f"缺少 package.json 或 package-lock.json：{project}")
    canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16], source


def shared_cache_root(workspace: Path | None = None) -> Path:
    override = os.environ.get("MED_AUTOCAST_NODE_DEPS_CACHE", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if workspace is not None:
        return workspace.resolve() / ".cache" / "node-deps"
    env_ws = os.environ.get("MED_AUTOCAST_WORKSPACE_ROOT", "").strip()
    if env_ws:
        return Path(env_ws).expanduser().resolve() / ".cache" / "node-deps"
    return (Path.home() / ".cache" / "med-autocast" / "node-deps").resolve()


def _is_pool_ready(cache_dir: Path, required: list[str]) -> bool:
    ready_file = cache_dir / ".ready.json"
    nm_dir = cache_dir / "node_modules"
    if not ready_file.is_file() or not nm_dir.is_dir():
        return False
    for name in required:
        if not (nm_dir / Path(*name.split("/"))).exists():
            return False
    return True


def ensure_shared_node_modules(project: Path, workspace: Path | None = None) -> dict:
    """Install (once per lockfile fingerprint) and return the shared node_modules path."""
    project = project.resolve()
    fingerprint, source = dependency_fingerprint(project)
    required = declared_packages(project)
    cache_root = shared_cache_root(workspace)
    cache_root.mkdir(parents=True, exist_ok=True)
    cache_dir = cache_root / fingerprint
    nm_dir = cache_dir / "node_modules"

    if _is_pool_ready(cache_dir, required):
        return {
            "fingerprint": fingerprint,
            "cache_dir": cache_dir,
            "node_modules": nm_dir,
            "reused": True,
            "source": str(source) if source else None,
        }

    lock_handle_path = cache_root / f".{fingerprint}.lock"
    with lock_handle_path.open("a+", encoding="utf-8") as lock_file:
        if fcntl is not None:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            if _is_pool_ready(cache_dir, required):
                return {
                    "fingerprint": fingerprint,
                    "cache_dir": cache_dir,
                    "node_modules": nm_dir,
                    "reused": True,
                    "source": str(source) if source else None,
                }
            stage = Path(tempfile.mkdtemp(prefix=f".staging-{fingerprint}-", dir=cache_root))
            try:
                for filename in ("package.json", "package-lock.json"):
                    src = project / filename
                    if src.is_file():
                        shutil.copy2(src, stage / filename)
                cmd = (
                    ["npm", "ci", "--no-audit", "--no-fund"]
                    if (stage / "package-lock.json").is_file()
                    else ["npm", "install", "--no-audit", "--no-fund"]
                )
                subprocess.run(cmd, cwd=stage, check=True)
                ready = {
                    "schema": SCHEMA,
                    "fingerprint": fingerprint,
                    "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                    "platform": sys.platform,
                    "machine": platform.machine(),
                    "packages": required,
                    "source_lock_sha256": (
                        hashlib.sha256((stage / "package-lock.json").read_bytes()).hexdigest()
                        if (stage / "package-lock.json").is_file()
                        else None
                    ),
                }
                (stage / ".ready.json").write_text(
                    json.dumps(ready, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8",
                )
                if cache_dir.exists():
                    shutil.rmtree(cache_dir)
                os.replace(stage, cache_dir)
            except BaseException:
                shutil.rmtree(stage, ignore_errors=True)
                raise
        finally:
            if fcntl is not None:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    return {
        "fingerprint": fingerprint,
        "cache_dir": cache_dir,
        "node_modules": nm_dir,
        "reused": False,
        "source": str(source) if source else None,
    }


def build_env_for_project(
    project: Path,
    workspace: Path | None = None,
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict]:
    """Prepare environment variables to build `project` using the shared dependency pool."""
    project = project.resolve()
    env = dict(os.environ if base_env is None else base_env)
    if workspace is not None:
        env["MED_AUTOCAST_WORKSPACE_ROOT"] = str(workspace.resolve())
    env["PYTHONDONTWRITEBYTECODE"] = "1"

    pool = ensure_shared_node_modules(project, workspace)
    shared_nm = pool["node_modules"]
    bin_dir = shared_nm / ".bin"
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}".rstrip(os.pathsep)
    existing_node_path = env.get("NODE_PATH", "")
    env["NODE_PATH"] = (
        f"{shared_nm}{os.pathsep}{existing_node_path}" if existing_node_path else str(shared_nm)
    )
    env["MED_AUTOCAST_SHARED_NODE_MODULES"] = str(shared_nm)

    import_flag = f"--import={RESOLVER_SCRIPT.as_uri()}"
    existing_opts = env.get("NODE_OPTIONS", "").strip()
    if import_flag not in existing_opts:
        env["NODE_OPTIONS"] = f"{import_flag} {existing_opts}".strip()
    return env, pool


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    ens = sub.add_parser("ensure", help="Ensure shared node_modules for a project and print JSON")
    ens.add_argument("--project", type=Path, required=True)
    ens.add_argument("--workspace", type=Path)

    env_cmd = sub.add_parser("env", help="Print shell exports for building a project")
    env_cmd.add_argument("--project", type=Path, required=True)
    env_cmd.add_argument("--workspace", type=Path)

    args = parser.parse_args()
    if args.command == "ensure":
        info = ensure_shared_node_modules(args.project, args.workspace)
        print(json.dumps({k: str(v) if isinstance(v, Path) else v for k, v in info.items()}, ensure_ascii=False))
    elif args.command == "env":
        env, info = build_env_for_project(args.project, args.workspace)
        import shlex

        for key in ("PATH", "NODE_PATH", "MED_AUTOCAST_SHARED_NODE_MODULES", "NODE_OPTIONS"):
            print(f"export {key}={shlex.quote(env[key])}")


if __name__ == "__main__":
    main()
