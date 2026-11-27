"""Resolve the installed companion library via `opl pack inspect`."""
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "native_discovery_companion", ROOT / "runtime/workbench/scripts/media_asset_library.py"
)
companion = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(companion)


class NativeCompanionDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name).resolve()

    @staticmethod
    def library(root: Path):
        (root / "catalog").mkdir(parents=True, exist_ok=True)
        (root / "tools").mkdir(parents=True, exist_ok=True)
        (root / "catalog/assets.jsonl").write_text("")
        (root / "tools/query_assets.py").write_text("# fixture\n")

    def test_locate_installed_companion_uses_framework_package_location(self):
        current = self.base / "installed-companion"
        self.library(current)
        stdout = json.dumps({
            "manifest": {"schema_version": "opl.package.v2", "identity": {"id": "mac-media-assets"}},
            "installed": {"package_id": "mac-media-assets", "enabled": False, "install_path": str(current)},
        })
        with patch.dict(os.environ, {"OPL_BIN": "/fixture/opl"}, clear=False), \
             patch.object(companion.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=stdout, stderr="")) as run:
            self.assertEqual(companion.locate_installed_companion("mac-media-assets"), [current])
        run.assert_called_once_with(
            ["/fixture/opl", "pack", "inspect", "mac-media-assets", "--json"],
            capture_output=True,
            text=True,
            timeout=30,
        )

    def test_uninstalled_or_missing_location_returns_empty(self):
        not_found = json.dumps({"installed": None})
        uninstalled = json.dumps({
            "installed": {"package_id": "mac-media-assets", "install_path": str(self.base / "absent")},
        })
        for payload in (not_found, uninstalled, "not-json"):
            with patch.dict(os.environ, {"OPL_BIN": "/fixture/opl"}, clear=False), \
                 patch.object(companion.subprocess, "run", return_value=subprocess.CompletedProcess([], 0, stdout=payload, stderr="")):
                self.assertEqual(companion.locate_installed_companion("mac-media-assets"), [])

    def test_cli_failure_timeout_or_missing_binary_fails_open(self):
        with patch.dict(os.environ, {"OPL_BIN": "/fixture/opl"}, clear=False), \
             patch.object(companion.subprocess, "run", side_effect=subprocess.TimeoutExpired("opl", 30)):
            self.assertEqual(companion.locate_installed_companion("mac-media-assets"), [])
        with patch.dict(os.environ, {"OPL_BIN": "/fixture/opl"}, clear=False), \
             patch.object(companion.subprocess, "run", return_value=subprocess.CompletedProcess([], 1, stdout="", stderr="err")):
            self.assertEqual(companion.locate_installed_companion("mac-media-assets"), [])
        with patch.dict(os.environ, {}, clear=True), \
             patch.object(companion.shutil, "which", return_value=None):
            self.assertEqual(companion.locate_installed_companion("mac-media-assets"), [])

    def test_locate_resolves_installed_companion_after_framework_locate(self):
        workspace = self.base / "workspace"
        workspace.mkdir()
        current = self.base / "framework-located"
        self.library(current)
        with patch.dict(os.environ, {"CODEX_HOME": str(self.base / "codex")}, clear=True), \
             patch.object(companion, "locate_installed_companion", return_value=[current]):
            self.assertEqual(companion.locate(workspace), (current, "installed_companion"))

    def test_explicit_workspace_library_still_has_precedence(self):
        workspace = self.base / "workspace"
        workspace.mkdir()
        selected = self.base / "user-selected-library"
        self.library(selected)
        (workspace / "workbench.yaml").write_text(
            "asset_library:\n  root: " + json.dumps(str(selected)) + "\n"
        )
        with patch.object(companion, "locate_installed_companion") as locate_mock:
            self.assertEqual(companion.locate(workspace), (selected, "workspace_config"))
        locate_mock.assert_not_called()


if __name__ == "__main__":
    unittest.main()
