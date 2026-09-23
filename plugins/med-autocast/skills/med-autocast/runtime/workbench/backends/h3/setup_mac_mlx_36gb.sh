#!/usr/bin/env bash
set -euo pipefail

# Prepare Apple Silicon MLX assets for a Mac with roughly 32–36 GiB unified memory.
# This is a disk/build preparation script: it does not reserve or consume 36 GiB
# of RAM by itself. The runtime must explicitly use memory_mode=stream2.
# Downloads/conversion are explicit because the build needs roughly 105–120 GiB
# of free disk space, depending on the selected profile and cache state.
# The default profile "24" is an upstream alias that builds the 4-bit-pruned
# resident weights and the matching stream2 checkpoint. Use "4-pruned" only
# when a resident-only artifact is intentional.
H3_MAC_ROOT="${H3_MAC_ROOT:-$HOME/ai/minimax-h3-mac}"
COMFY_DIR="$H3_MAC_ROOT/ComfyUI"
PYTHON="$H3_MAC_ROOT/.venv/bin/python"
NODE_DIR="$COMFY_DIR/custom_nodes/ComfyUI-MiniMax-H3-MLX-SolAttn"
MODELS_DIR="$COMFY_DIR/models"
MODELS_DIR="${H3_MODELS_DIR:-$MODELS_DIR}"
PROFILE="${H3_MLX_PROFILE:-24}"
mkdir -p "$MODELS_DIR"

if [[ ! -x "$PYTHON" || ! -f "$NODE_DIR/scripts/setup_comfyui.py" ]]; then
  echo "Mac MLX node is not installed. Run setup_mac_local.sh first." >&2
  exit 1
fi

available_kib="$(df -Pk "$MODELS_DIR" | awk 'NR==2 {print $4}')"
required_kib=$((110 * 1024 * 1024))
if [[ "$available_kib" -lt "$required_kib" ]]; then
  echo "Insufficient free disk: $((available_kib / 1024 / 1024)) GiB available; " \
       "about 110 GiB is required for the MLX build and temporary files." >&2
  exit 2
fi

echo "Preparing MLX profile=$PROFILE for a Mac with roughly 32–36 GiB unified memory."
echo "This setup step downloads/builds model files; it does not reserve 36 GiB of RAM."
echo "At runtime, set memory_mode=stream2 explicitly in the workflow."

exec uv run --python "$PYTHON" --no-project \
  "$NODE_DIR/scripts/setup_comfyui.py" \
  --models-dir "$MODELS_DIR" --profile "$PROFILE" --accept-license
