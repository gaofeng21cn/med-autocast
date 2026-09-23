#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1
python3 -m unittest discover -s "${repo_dir}/tests" -v
python3 "${repo_dir}/scripts/verify_contracts.py"
if [[ "${1:-fast}" == "full" ]]; then
  opl_bin="${OPL_BIN:-opl}"
  "${opl_bin}" agents check --repo "${repo_dir}" --json
  "${opl_bin}" workspace source-hygiene --source-root "${repo_dir}" --json
  "${opl_bin}" pack native-helper probe --descriptor "${repo_dir}/runtime/native_helpers/med_autocast.native-helper-probe.json" --json
elif [[ "${1:-fast}" != "fast" ]]; then
  echo "Usage: scripts/verify.sh [fast|full]" >&2
  exit 2
fi
