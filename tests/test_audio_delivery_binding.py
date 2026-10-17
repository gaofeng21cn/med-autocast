"""Regression tests for the read-only audio delivery binding audit."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "runtime/workbench/scripts/test_audit_audio_delivery_binding.py"
SPEC = importlib.util.spec_from_file_location("test_audit_audio_delivery_binding_runtime", SCRIPT)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


DeliveryBindingTests = MODULE.DeliveryBindingTests

