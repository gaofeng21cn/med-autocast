#!/usr/bin/env bash
set -euo pipefail
repo_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PYTHONDONTWRITEBYTECODE=1

opl_bin="${OPL_BIN:-${OPL_FRAMEWORK_ROOT:+${OPL_FRAMEWORK_ROOT}/bin/opl}}"
if [[ -z "${opl_bin}" ]]; then
  if [[ -x "${repo_dir}/../one-person-lab/bin/opl" ]]; then
    opl_bin="${repo_dir}/../one-person-lab/bin/opl"
  else
    opl_bin="$(command -v opl || true)"
  fi
fi

framework_python_root="${OPL_FRAMEWORK_PYTHON_ROOT:-${OPL_FRAMEWORK_ROOT:+${OPL_FRAMEWORK_ROOT}/python}}"
if [[ -z "${framework_python_root}" && -n "${opl_bin}" && -d "$(dirname "${opl_bin}")/../python/opl_framework" ]]; then
  framework_python_root="$(cd "$(dirname "${opl_bin}")/../python" && pwd)"
elif [[ -z "${framework_python_root}" && -d "${repo_dir}/../one-person-lab/python/opl_framework" ]]; then
  framework_python_root="${repo_dir}/../one-person-lab/python"
elif [[ -z "${framework_python_root}" && -d "${repo_dir}/src/opl_framework" ]]; then
  framework_python_root="${repo_dir}/src"
fi
if [[ -n "${framework_python_root}" && -d "${framework_python_root}" ]]; then
  export OPL_FRAMEWORK_PYTHON_ROOT="${framework_python_root}"
  export PYTHONPATH="${framework_python_root}${PYTHONPATH:+:${PYTHONPATH}}"
fi

sdk_root="${OPL_PYTHON_SDK_ROOT:-${OPL_FRAMEWORK_ROOT:+${OPL_FRAMEWORK_ROOT}/sdks/python-client}}"
if [[ -z "${sdk_root}" && -n "${opl_bin}" ]] && command -v "${opl_bin}" >/dev/null 2>&1; then
  sdk_root="$(dirname "$(command -v "${opl_bin}")")/../sdks/python-client"
fi
if [[ -n "${sdk_root}" && -d "${sdk_root}/src/opl_client" ]]; then
  export OPL_PYTHON_SDK_ROOT="${sdk_root}"
  export PYTHONPATH="${sdk_root}/src${PYTHONPATH:+:${PYTHONPATH}}"
fi

if command -v node >/dev/null 2>&1; then
  node "${repo_dir}/scripts/project-carrier.mjs" >/dev/null
fi

python3 -m unittest discover -s "${repo_dir}/tests" -v
python3 "${repo_dir}/scripts/verify_contracts.py"
if [[ "${1:-fast}" == "full" ]]; then
  [[ -n "${opl_bin}" && -x "${opl_bin}" ]] || {
    echo "OPL CLI is unavailable; set OPL_BIN or OPL_FRAMEWORK_ROOT." >&2
    exit 1
  }
  "${opl_bin}" pack inspect "${repo_dir}" --json
  "${opl_bin}" pack build "${repo_dir}" --no-write-lock --json
elif [[ "${1:-fast}" != "fast" ]]; then
  echo "Usage: scripts/verify.sh [fast|full]" >&2
  exit 2
fi
