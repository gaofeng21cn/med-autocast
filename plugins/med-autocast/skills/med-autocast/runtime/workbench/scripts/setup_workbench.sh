#!/usr/bin/env bash
set -euo pipefail
case "${1:-}" in
  ""|--check) ;;
  *) echo "Usage: bash scripts/setup_workbench.sh [--check]" >&2; exit 2 ;;
esac
workbench_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
runtime="$workbench_root/.venv"
if [[ "${1:-}" != "--check" ]]; then
  if [[ ! -x "$runtime/bin/python" ]]; then
    python3 -m venv "$runtime"
  fi
  "$runtime/bin/python" -m pip install -r "$workbench_root/requirements.txt"
fi
for tool in ffmpeg ffprobe magick; do
  command -v "$tool" >/dev/null || { echo "Missing system tool: $tool" >&2; exit 1; }
done
python_command="${WORKBENCH_PYTHON:-$runtime/bin/python}"
if [[ ! -x "$python_command" ]]; then
  echo "Run bash scripts/setup_workbench.sh first, or set WORKBENCH_PYTHON to an existing interpreter." >&2
  exit 1
fi
"$python_command" -B "$workbench_root/scripts/workbench_config.py" validate --pretty
PYTHONPATH="$workbench_root/scripts" "$python_command" -B -c 'from workbench_config import resolve_font; print("Font:", resolve_font())'
