#!/usr/bin/env bash
set -euo pipefail

H3_ROOT="${H3_ROOT:-$HOME/ai/minimax-h3}"
COMFY_DIR="$H3_ROOT/ComfyUI"
PYTHON="$H3_ROOT/.venv/bin/python"
LOG_DIR="$H3_ROOT/logs"
PID_FILE="$H3_ROOT/comfyui.pid"
SERVICE_NAME="minimax-h3-comfyui.service"
bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [[ ! -x "$PYTHON" || ! -f "$COMFY_DIR/main.py" ]]; then
  echo "MiniMax H3 is not installed under $H3_ROOT. Run setup_h3.sh first." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"

if systemctl --user is-system-running >/dev/null 2>&1; then
  user_unit_dir="$HOME/.config/systemd/user"
  mkdir -p "$user_unit_dir"
  rendered_service="$("$PYTHON" "$bundle_dir/render_service.py" --root "$H3_ROOT")"
  printf '%s\n' "$rendered_service" > "$user_unit_dir/$SERVICE_NAME"
  systemctl --user daemon-reload
  systemctl --user enable --now "$SERVICE_NAME"
  server_pid="$(systemctl --user show -p MainPID --value "$SERVICE_NAME")"
else
  if [[ -f "$PID_FILE" ]]; then
    existing_pid="$(cat "$PID_FILE")"
    if kill -0 "$existing_pid" 2>/dev/null; then
      echo "ComfyUI is already running with PID $existing_pid"
      exit 0
    fi
    rm -f "$PID_FILE"
  fi

  cd "$COMFY_DIR"
  nohup "$PYTHON" main.py \
    --listen 127.0.0.1 \
    --port 8188 \
    --reserve-vram 2.0 \
    >"$LOG_DIR/comfyui.log" 2>&1 &
  server_pid=$!
  echo "$server_pid" >"$PID_FILE"
fi

for _ in $(seq 1 60); do
  if curl -fsS http://127.0.0.1:8188/system_stats >/dev/null 2>&1; then
    echo "ComfyUI is ready at http://127.0.0.1:8188 (PID $server_pid)"
    exit 0
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    if systemctl --user is-system-running >/dev/null 2>&1; then
      journalctl --user -u "$SERVICE_NAME" -n 120 --no-pager >&2
    else
      tail -n 120 "$LOG_DIR/comfyui.log" >&2
    fi
    exit 1
  fi
  sleep 2
done

echo "ComfyUI did not become ready within 120 seconds." >&2
if systemctl --user is-system-running >/dev/null 2>&1; then
  journalctl --user -u "$SERVICE_NAME" -n 120 --no-pager >&2
else
  tail -n 120 "$LOG_DIR/comfyui.log" >&2
fi
exit 1
