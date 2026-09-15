#!/usr/bin/env python3
"""Inspect and select local/remote media backends without mutating credentials."""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - doctor reports the missing dependency
    yaml = None

from workbench_config import load_backend_profile


ROOT = Path(os.environ.get("OPL_MEDCAST_WORKSPACE_ROOT", Path(__file__).resolve().parents[1])).resolve()
WORKBENCH = ROOT / "workbench.yaml"


def expand(value: Any) -> Any:
    if isinstance(value, str):
        # Support shell-style \${NAME:-default} in the checked-in config while
        # keeping secrets in the environment.
        def replace_default(match: re.Match[str]) -> str:
            name, default = match.group(1), match.group(2)
            return os.environ.get(name, default)

        value = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*):-([^}]*)\}", replace_default, value)
        return os.path.expandvars(os.path.expanduser(value))
    if isinstance(value, dict):
        return {key: expand(item) for key, item in value.items()}
    if isinstance(value, list):
        return [expand(item) for item in value]
    return value


def load_config(path: Path | None = None) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required; install it with `python3 -m pip install pyyaml`.")
    _, config = load_backend_profile(profile_path=path, root=ROOT)
    return expand(config)


def torch_devices() -> dict[str, Any]:
    result: dict[str, Any] = {"installed": False, "cuda": False, "mps": False}
    try:
        import torch

        result["installed"] = True
        result["torch"] = torch.__version__
        result["cuda"] = bool(torch.cuda.is_available())
        result["mps"] = bool(torch.backends.mps.is_available())
    except Exception as exc:  # noqa: BLE001 - doctor must remain usable
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


def endpoint_status(endpoint: str) -> dict[str, Any]:
    if not endpoint:
        return {"state": "not_configured"}
    try:
        import urllib.request

        with urllib.request.urlopen(endpoint.rstrip("/") + "/system_stats", timeout=3) as response:
            return {"state": "reachable", "http_status": response.status}
    except Exception as exc:  # noqa: BLE001 - network is optional for local doctor
        return {"state": "unreachable", "error": f"{type(exc).__name__}: {exc}"}


def python_probe(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {"state": "missing", "path": str(path)}
    try:
        completed = subprocess.run(
            [
                str(path),
                "-c",
                (
                    "import torch; "
                    "print(torch.__version__); "
                    "print('cuda=' + str(bool(torch.cuda.is_available()))); "
                    "print('mps=' + str(bool(torch.backends.mps.is_available())))"
                ),
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=10,
        )
        lines = completed.stdout.strip().splitlines()
        return {
            "state": "ready",
            "path": str(path),
            "torch": lines[0] if lines else None,
            "cuda": any(line == "cuda=True" for line in lines),
            "mps": any(line == "mps=True" for line in lines),
        }
    except Exception as exc:  # noqa: BLE001 - doctor is diagnostic
        return {"state": "error", "path": str(path), "error": f"{type(exc).__name__}: {exc}"}


def ssh_path_status(host: str, path: str) -> dict[str, Any]:
    if not host:
        return {"state": "not_configured"}
    if shutil.which("ssh") is None:
        return {"state": "unavailable", "error": "ssh was not found"}
    remote_command = (
        f"if test -d {shlex.quote(path)}; "
        "then printf path_ready; else printf path_missing; fi"
    )
    try:
        completed = subprocess.run(
            [
                "ssh",
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=3",
                host,
                remote_command,
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=8,
        )
        return {
            "state": "reachable",
            "host": host,
            "path": path,
            "path_exists": completed.stdout == "path_ready",
        }
    except Exception as exc:  # noqa: BLE001 - remote availability is optional
        return {"state": "unreachable", "host": host, "error": f"{type(exc).__name__}: {exc}"}


def check_backend(name: str, spec: dict[str, Any], kind: str) -> dict[str, Any]:
    result: dict[str, Any] = {
        "name": name,
        "kind": kind,
        "label": spec.get("label"),
        "mode": spec.get("mode"),
        "capability": spec.get("capability"),
        "device": spec.get("device"),
        "workflow": spec.get("workflow"),
        "runtime_profile": spec.get("runtime_profile"),
        "checks": [],
    }
    if spec.get("kind") in {"comfyui", "indextts"}:
        root = Path(spec["root"])
        result["root"] = str(root)
        result["root_exists"] = root.exists()
        result["runtime"] = python_probe(root / ".venv" / "bin" / "python")
    if spec.get("kind") == "indextts":
        model_root = Path(spec["model_root"])
        result["model_root"] = str(model_root)
        result["model_exists"] = model_root.exists()
        result["python"] = shutil.which("python3")
    if spec.get("kind") == "comfyui":
        result["endpoint"] = spec.get("endpoint")
        result["endpoint_status"] = endpoint_status(spec.get("endpoint", ""))
    if spec.get("kind") == "comfyui_remote":
        result["endpoint"] = spec.get("endpoint")
        result["endpoint_status"] = endpoint_status(spec.get("endpoint", ""))
    if spec.get("kind") == "indextts_remote" and spec.get("endpoint"):
        result["endpoint"] = spec["endpoint"]
        result["endpoint_status"] = endpoint_status(spec["endpoint"])
    if spec.get("kind") == "indextts_remote" and spec.get("transport") == "ssh":
        result["ssh_status"] = ssh_path_status(
            spec.get("host", ""), spec.get("model_root", "")
        )
    if spec.get("kind") == "http_api":
        endpoint = spec.get("endpoint", "")
        api_key_configured = bool(os.getenv(spec.get("api_key_env", "")))
        result["endpoint"] = endpoint
        result["api_key_configured"] = api_key_configured
        if endpoint and api_key_configured:
            state = "configured"
        elif endpoint or api_key_configured:
            state = "partially_configured"
        else:
            state = "not_configured"
        result["endpoint_status"] = {"state": state}
    return result


def doctor(config: dict[str, Any]) -> dict[str, Any]:
    data: dict[str, Any] = {
        "platform": platform.platform(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "torch": torch_devices(),
        "tools": {name: shutil.which(name) for name in ("ffmpeg", "ffprobe", "ssh", "uv", "git")},
        "video": [],
        "audio": [],
        "policy": config.get("policy", {}),
    }
    for name, spec in config.get("video", {}).items():
        data["video"].append(check_backend(name, spec, "video"))
    for name, spec in config.get("audio", {}).items():
        data["audio"].append(check_backend(name, spec, "audio"))
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("list", "doctor", "resolve"), nargs="?", default="doctor")
    parser.add_argument(
        "--profile",
        "--config",
        dest="profile",
        type=Path,
        help="Backend deployment profile; defaults to workbench.yaml active_profiles.media_backends",
    )
    parser.add_argument("--media", choices=("video", "audio"), default="video")
    parser.add_argument("--backend")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    config = load_config(args.profile)
    if args.command == "list":
        output = {
            "profile_id": config.get("profile_id"),
            "video": config.get("video", {}),
            "audio": config.get("audio", {}),
            "policy": config.get("policy", {}),
        }
    elif args.command == "doctor":
        output = doctor(config)
    else:
        backend = args.backend or config.get("policy", {}).get(f"default_{args.media}")
        choices = config.get(args.media, {})
        if backend not in choices:
            raise SystemExit(
                f"Unknown {args.media} backend {backend!r}; choose: {', '.join(choices)}"
            )
        output = {
            "profile_id": config.get("profile_id"),
            "media": args.media,
            "backend": backend,
            "spec": choices[backend],
        }
    print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))


if __name__ == "__main__":
    main()
