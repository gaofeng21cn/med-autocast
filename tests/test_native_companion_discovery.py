"""Resolve the current native companion before stale projections and caches."""
import importlib.util
import json
import os
from pathlib import Path
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
        self.home = self.base / "native"
        self.home.mkdir()

    def marketplace(self, root, relative="./"):
        manifest = root / ".agents/plugins/marketplace.json"
        manifest.parent.mkdir(parents=True, exist_ok=True)
        manifest.write_text(json.dumps({
            "name": "mac-media-assets",
            "plugins": [{"name": "mac-media-assets", "source": {
                "source": "local", "path": relative,
            }}],
        }))

    def native_config(self, root, installed=True, source_type="local"):
        text = ("[marketplaces.mac-media-assets]\nsource_type = "
                + json.dumps(source_type) + "\nsource = " + json.dumps(str(root)) + "\n")
        if installed:
            text += '[plugins."mac-media-assets@mac-media-assets"]\nenabled = false\n'
        (self.home / "config.toml").write_text(text)

    @staticmethod
    def library(root):
        (root / "catalog").mkdir(parents=True, exist_ok=True)
        (root / "tools").mkdir(parents=True, exist_ok=True)
        (root / "catalog/assets.jsonl").write_text("")
        (root / "tools/query_assets.py").write_text("# fixture\n")

    def test_disabled_headless_membership_resolves_current_local_source(self):
        current = self.base / "current"
        self.marketplace(current)
        self.native_config(current)
        self.assertEqual(companion.native_companion_roots(self.home), [current])

    def test_relative_plugin_source_is_resolved_within_marketplace(self):
        current = self.base / "current"
        self.marketplace(current, "./plugins/mac-media-assets")
        self.native_config(current)
        self.assertEqual(companion.native_companion_roots(self.home), [
            current / "plugins/mac-media-assets"
        ])

    def test_available_but_uninstalled_marketplace_is_ignored(self):
        current = self.base / "current"
        self.marketplace(current)
        self.native_config(current, installed=False)
        self.assertEqual(companion.native_companion_roots(self.home), [])

    def test_git_marketplace_uses_its_current_native_checkout(self):
        current = self.home / ".tmp/marketplaces/mac-media-assets"
        self.marketplace(current)
        self.native_config("https://example.invalid/assets.git", source_type="git")
        self.assertEqual(companion.native_companion_roots(self.home), [current])

    def test_relative_source_cannot_escape_marketplace(self):
        current = self.base / "current"
        self.marketplace(current, "../outside")
        self.native_config(current)
        self.assertEqual(companion.native_companion_roots(self.home), [])

    def test_absolute_source_is_not_a_portable_marketplace_path(self):
        current = self.base / "current"
        self.marketplace(current, str(current / "payload"))
        self.native_config(current)
        self.assertEqual(companion.native_companion_roots(self.home), [])

    def test_malformed_config_leaves_fallback_available(self):
        (self.home / "config.toml").write_text("broken = [")
        self.assertEqual(companion.native_companion_roots(self.home), [])

    def test_current_native_source_precedes_historical_projection(self):
        workspace = self.base / "workspace"
        workspace.mkdir()
        state = self.base / "state"
        native = state / "internal-package-carrier"
        native.mkdir(parents=True)
        self.home = native
        current = self.base / "current"
        self.marketplace(current)
        self.library(current)
        self.native_config(current)
        stale = state / "codex-plugin-marketplaces/mac-media-assets/plugins/mac-media-assets"
        self.library(stale)
        env = {"CODEX_HOME": str(self.base / "codex"), "OPL_STATE_DIR": str(state)}
        with patch.dict(os.environ, env, clear=True):
            self.assertEqual(companion.locate(workspace), (current, "installed_companion"))

    def test_explicit_workspace_library_still_has_precedence(self):
        workspace = self.base / "workspace"
        workspace.mkdir()
        selected = self.base / "user-selected-library"
        self.library(selected)
        (workspace / "workbench.yaml").write_text(
            "asset_library:\n  root: " + json.dumps(str(selected)) + "\n"
        )
        self.assertEqual(companion.locate(workspace), (selected, "workspace_config"))


if __name__ == "__main__":
    unittest.main()
