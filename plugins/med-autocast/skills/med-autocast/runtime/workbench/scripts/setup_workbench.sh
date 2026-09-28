#!/usr/bin/env bash
set -euo pipefail
source_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workbench_root="$source_root"
check_only=0
while (( $# )); do
  case "$1" in
    --check) check_only=1; shift ;;
    --workspace) [[ $# -ge 2 ]] || { echo '--workspace 需要目录' >&2; exit 2; }; workbench_root="$2"; shift 2 ;;
    *) echo '用法: setup_workbench.sh [--workspace <新建空目录或已有工作区>] [--check]' >&2; exit 2 ;;
  esac
done
bootstrap_python="${WORKBENCH_PYTHON:-python3}"
command -v "$bootstrap_python" >/dev/null || { echo '请先安装 Python 3.11+' >&2; exit 1; }
"$bootstrap_python" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else "需要 Python 3.11+")'
if (( check_only )); then
  python_command="$workbench_root/.venv/bin/python"
  [[ -x "$python_command" ]] || python_command="$bootstrap_python"
  exec "$python_command" -B "$source_root/scripts/environment_check.py" --workspace "$workbench_root" --pretty --strict
fi
# Check prerequisites before downloading dependencies. No implicit sudo or global package installation.
for tool in node npm ffmpeg ffprobe magick; do
  command -v "$tool" >/dev/null || { echo "缺少 $tool。macOS: brew install python node ffmpeg imagemagick；Linux 请安装同等工具。" >&2; exit 1; }
done
node -e 'if (Number(process.versions.node.split(".")[0]) < 20) { console.error("需要 Node.js 20+"); process.exit(1); }'
if [[ ! -f "$workbench_root/workbench.yaml" ]]; then
  "$bootstrap_python" -B "$source_root/scripts/init_workbench.py" --workspace "$workbench_root"
fi
workbench_root="$(cd "$workbench_root" && pwd)"
# Do not put runtimes in the versioned plugin cache or overwrite an old workspace.
for file in requirements.txt package-lock.json scripts/environment_check.py; do
  [[ -f "$workbench_root/$file" ]] || { echo "已有工作区缺少 $file；请由智能体核对本机改动后增量更新，或用 --workspace 新建空目录。" >&2; exit 1; }
done
runtime="$workbench_root/.venv"
if [[ ! -x "$runtime/bin/python" ]]; then
  "$bootstrap_python" -m venv "$runtime"
fi
"$runtime/bin/python" -c 'import sys; sys.exit(0 if sys.version_info >= (3,11) else "已有 .venv 需要升级到 Python 3.11+")'
"$runtime/bin/python" -m pip install -r "$workbench_root/requirements.txt"
(cd "$workbench_root" && npm ci --workspaces=false --no-audit --no-fund)
if [[ -z "${CHROME_PATH:-}" ]]; then
  "$workbench_root/node_modules/.bin/playwright" install chromium
fi
export MED_AUTOCAST_WORKSPACE_ROOT="$workbench_root"
"$runtime/bin/python" -B "$workbench_root/scripts/environment_check.py" --workspace "$workbench_root" --pretty --strict
