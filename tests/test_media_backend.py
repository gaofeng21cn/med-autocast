from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


SCRIPT_ROOT = Path(__file__).resolve().parents[1] / "runtime/workbench/scripts"
sys.path.insert(0, str(SCRIPT_ROOT))
spec = importlib.util.spec_from_file_location("media_backend", SCRIPT_ROOT / "media_backend.py")
media_backend = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = media_backend
spec.loader.exec_module(media_backend)


class MediaBackendTests(unittest.TestCase):
    @patch("media_backend.endpoint_status", return_value={"state": "reachable"})
    def test_local_remote_and_mlx_comfyui_profiles_probe_endpoint_without_runtime_path(self, _probe):
        for name, kind in (
            ("remote", "comfyui_remote"),
            ("local", "comfyui"),
            ("mlx", "comfyui"),
        ):
            with self.subTest(name=name):
                result = media_backend.check_backend(
                    f"optional_comfyui_{name}",
                    {
                        "kind": kind,
                        "endpoint": "http://127.0.0.1:8188",
                        "selection": "explicit",
                        "default": False,
                    },
                    "video",
                )
                self.assertEqual(result["endpoint_status"]["state"], "reachable")
                self.assertNotIn("runtime", result)
                self.assertFalse(result["default"])


if __name__ == "__main__":
    unittest.main()
