"""Exercise the distributed freshness regression through the repository check."""
import importlib.util
from pathlib import Path
import sys

SCRIPT = Path(__file__).resolve().parents[1] / 'runtime/workbench/scripts/test_audio_freshness_build.py'
sys.path.insert(0, str(SCRIPT.parent))
SPEC = importlib.util.spec_from_file_location('freshness_build_runtime_test', SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)
FreshBuildTests = MODULE.FreshBuildTests
