#!/usr/bin/env bash
set -euo pipefail

H3_MAC_ROOT="${H3_MAC_ROOT:-$HOME/ai/minimax-h3-mac}"
H3_MAC_MODE="${H3_MAC_MODE:-performance}"
COMFY_DIR="$H3_MAC_ROOT/ComfyUI"
PYTHON="$H3_MAC_ROOT/.venv/bin/python"
PORT="${H3_MAC_PORT:-28188}"
LOG_DIR="$H3_MAC_ROOT/logs"
PID_FILE="$H3_MAC_ROOT/comfyui-mac.pid"

case "$H3_MAC_MODE" in
  performance)
    export MINIMAX_H3_MODELS_DIR="${MINIMAX_H3_MODELS_DIR:-$COMFY_DIR/models}"
    ;;
  36gb)
    # The compatibility workflow itself enforces stream2 + offset. The model
    # root may be local, NAS-backed, or otherwise supplied by the machine.
    ;;
  *)
    echo "Unknown H3_MAC_MODE '$H3_MAC_MODE'; choose performance or 36gb." >&2
    exit 2
    ;;
esac
# Keep the Apple Silicon allocator from growing a cached pool into swap. The
# custom FP8 node reads these before torch/MPS initialization; callers can
# override them explicitly when running on a larger machine.
export APPLESILICON_FP8_MPS_WATERMARK="${APPLESILICON_FP8_MPS_WATERMARK:-auto}"
export PYTORCH_MPS_LOW_WATERMARK_RATIO="${PYTORCH_MPS_LOW_WATERMARK_RATIO:-0.8}"
export PYTORCH_MPS_HIGH_WATERMARK_RATIO="${PYTORCH_MPS_HIGH_WATERMARK_RATIO:-1.0}"

if [[ ! -x "$PYTHON" || ! -f "$COMFY_DIR/main.py" ]]; then
  echo "Mac H3 runtime is not installed. Run setup_mac_local.sh first." >&2
  exit 1
fi

mkdir -p "$LOG_DIR"
if [[ -f "$PID_FILE" ]]; then
  existing_pid="$(<"$PID_FILE")"
  if kill -0 "$existing_pid" 2>/dev/null; then
    echo "Mac ComfyUI is already running with PID $existing_pid on port $PORT"
    exit 0
  fi
  rm -f "$PID_FILE"
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use by a process not owned by $PID_FILE; refusing to start a duplicate." >&2
  exit 1
fi

cd "$COMFY_DIR"
nohup "$PYTHON" main.py --listen 127.0.0.1 --port "$PORT" --use-pytorch-cross-attention \
  >"$LOG_DIR/comfyui-mac.log" 2>&1 &
server_pid=$!
echo "$server_pid" >"$PID_FILE"

for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:$PORT/system_stats" >/dev/null 2>&1; then
    sleep 1
    if ! kill -0 "$server_pid" 2>/dev/null; then
      echo "ComfyUI answered once but exited before readiness was stable." >&2
      tail -n 120 "$LOG_DIR/comfyui-mac.log" >&2
      exit 1
    fi
    echo "Mac ComfyUI is ready at http://127.0.0.1:$PORT (PID $server_pid, mode $H3_MAC_MODE)"
    exit 0
  fi
  if ! kill -0 "$server_pid" 2>/dev/null; then
    tail -n 120 "$LOG_DIR/comfyui-mac.log" >&2
    exit 1
  fi
  sleep 2
done

echo "Mac ComfyUI did not become ready within 120 seconds." >&2
tail -n 120 "$LOG_DIR/comfyui-mac.log" >&2
exit 1
