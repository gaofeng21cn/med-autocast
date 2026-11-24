#!/usr/bin/env python3
"""Workspace-shared Node.js build dependency pool keyed by lockfile fingerprint.

Delegates generic pool management to `opl_framework.shared_node_deps` while
preserving MAC schema and environment variable bindings.
"""
from __future__ import annotations

import json
from pathlib import Path

from _opl_framework_bootstrap import bootstrap_opl_framework

bootstrap_opl_framework()

from opl_framework.shared_node_deps import (  # noqa: E402
    DEP_SECTIONS,
    SharedNodeDepsConfig,
    build_shared_node_env,
    declared_packages,
    ensure_shared_node_modules as _fw_ensure_shared_node_modules,
    lockfile_fingerprint as dependency_fingerprint,
    resolve_shared_cache_root,
)

SCHEMA = "medical_video_shared_node_deps/v1"
RESOLVER_SCRIPT = Path(__file__).resolve().with_name("shared_node_resolve.mjs")
MAC_SHARED_NODE_DEPS = SharedNodeDepsConfig(
    schema=SCHEMA,
    env_shared_node_modules="MED_AUTOCAST_SHARED_NODE_MODULES",
    env_cache_dir="MED_AUTOCAST_NODE_DEPS_CACHE",
    env_workspace_root="MED_AUTOCAST_WORKSPACE_ROOT",
    default_cache_subpath=".cache/med-autocast/node-deps",
)


def shared_cache_root(workspace: Path | None = None) -> Path:
    return resolve_shared_cache_root(workspace, config=MAC_SHARED_NODE_DEPS)


def ensure_shared_node_modules(project: Path, workspace: Path | None = None) -> dict:
    """Install (once per lockfile fingerprint) and return the shared node_modules path."""
    return _fw_ensure_shared_node_modules(
        project,
        workspace_root=workspace,
        config=MAC_SHARED_NODE_DEPS,
    )


def build_env_for_project(
    project: Path,
    workspace: Path | None = None,
    base_env: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict]:
    """Prepare environment variables to build `project` using the shared dependency pool."""
    return build_shared_node_env(
        project,
        workspace_root=workspace,
        config=MAC_SHARED_NODE_DEPS,
        resolve_hook_path=RESOLVER_SCRIPT,
        base_env=base_env,
    )


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
        env, _info = build_env_for_project(args.project, args.workspace)
        import shlex

        for key in ("PATH", "NODE_PATH", "MED_AUTOCAST_SHARED_NODE_MODULES", "NODE_OPTIONS"):
            print(f"export {key}={shlex.quote(env[key])}")


if __name__ == "__main__":
    main()
