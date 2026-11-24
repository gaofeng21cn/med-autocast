"""Locate OPL Framework Python helpers for standalone and verify.sh workbench runs."""
from __future__ import annotations

import os
from pathlib import Path
import sys


def bootstrap_opl_framework() -> None:
    try:
        import opl_framework  # noqa: F401
        return
    except ImportError:
        pass
    candidates: list[Path] = []
    for env_key, suffix in (
        ("OPL_FRAMEWORK_PYTHON_ROOT", ""),
        ("OPL_FRAMEWORK_ROOT", "python"),
    ):
        raw = os.environ.get(env_key, "").strip()
        if raw:
            candidates.append(Path(raw) / suffix if suffix else Path(raw))
    opl_bin = os.environ.get("OPL_BIN", "").strip()
    if opl_bin:
        candidates.append(Path(opl_bin).resolve().parents[1] / "python")
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidates.append(parent / "src")
        candidates.append(parent / "one-person-lab" / "python")
    for candidate in candidates:
        if (candidate / "opl_framework").is_dir() and str(candidate) not in sys.path:
            sys.path.insert(0, str(candidate))
            return
