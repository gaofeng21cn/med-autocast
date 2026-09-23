#!/usr/bin/env bash
set -euo pipefail

# Apple Silicon deployment scaffold. Model downloads are opt-in because the
# H3 bundle is large. The MLX node provides a separate 24/32 GB Core4-pruned
# profile with strict staging; this script keeps downloads explicit.
H3_MAC_ROOT="${H3_MAC_ROOT:-$HOME/ai/minimax-h3-mac}"
COMFY_DIR="$H3_MAC_ROOT/ComfyUI"
VENV_DIR="$H3_MAC_ROOT/.venv"
bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DOWNLOAD_MODELS=0
if [[ "${1:-}" == "--download-models" ]]; then
  DOWNLOAD_MODELS=1
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "This script is for Apple Silicon (arm64); use setup_h3.sh on NVIDIA/WSL2." >&2
  exit 2
fi

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required. Install it with: brew install uv" >&2
  exit 2
fi

mkdir -p "$H3_MAC_ROOT"
available_kib="$(df -Pk "$H3_MAC_ROOT" | awk 'NR==2 {print $4}')"
if [[ "$available_kib" -lt $((60 * 1024 * 1024)) ]]; then
  echo "At least 60 GiB free is recommended for ComfyUI + H3 models; detected $((available_kib / 1024 / 1024)) GiB." >&2
  exit 2
fi

if [[ ! -d "$COMFY_DIR/.git" ]]; then
  git clone --branch v0.34.2 --depth 1 https://github.com/comfyanonymous/ComfyUI.git "$COMFY_DIR"
fi

uv python install 3.13
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  uv venv --python 3.13 "$VENV_DIR"
fi
uv pip install --python "$VENV_DIR/bin/python" -r "$COMFY_DIR/requirements.txt"

CUSTOM_DIR="$COMFY_DIR/custom_nodes"
mkdir -p "$CUSTOM_DIR"
clone_or_update() {
  local url="$1"; local name="$2"
  if [[ ! -d "$CUSTOM_DIR/$name/.git" ]]; then
    git clone --depth 1 "$url" "$CUSTOM_DIR/$name"
  fi
}

# These compatibility layers are required by the currently documented MPS
# H3 route. They are isolated under the Mac install and never alter the 4090.
clone_or_update https://github.com/pawel-mazurkiewicz/ComfyUI-AppleSilicon-FP8.git ComfyUI-AppleSilicon-FP8
clone_or_update https://github.com/city96/ComfyUI-GGUF.git ComfyUI-GGUF
clone_or_update https://github.com/xmarre/ComfyUI-Spectrum-MiniMax-H3.git ComfyUI-Spectrum-MiniMax-H3
clone_or_update https://github.com/yshenaw/ComfyUI-SolAttn-MPS.git ComfyUI-SolAttn-MPS

mlx_node_url="https://github.com/yshenaw/ComfyUI-MiniMax-H3-MLX-SolAttn.git"
mlx_node_revision="55bb7ddd015321a25385683419951e7c7f518775"
mlx_node_dir="$CUSTOM_DIR/ComfyUI-MiniMax-H3-MLX-SolAttn"
if [[ ! -d "$mlx_node_dir/.git" ]]; then
  git clone "$mlx_node_url" "$mlx_node_dir"
fi
if [[ "$(git -C "$mlx_node_dir" remote get-url origin)" != "$mlx_node_url" ]]; then
  echo "Refusing unexpected MLX node repository: $mlx_node_dir" >&2
  exit 1
fi
if [[ "$(git -C "$mlx_node_dir" rev-parse HEAD)" != "$mlx_node_revision" ]]; then
  if [[ -n "$(git -C "$mlx_node_dir" status --porcelain)" ]]; then
    echo "MLX node has local changes on another revision; refusing to overwrite them." >&2
    exit 1
  fi
  git -C "$mlx_node_dir" fetch --depth 1 origin "$mlx_node_revision"
  git -C "$mlx_node_dir" checkout --detach "$mlx_node_revision"
fi
"$bundle_dir/apply_mac_mlx_overlay.sh" "$mlx_node_dir"

for node in "$CUSTOM_DIR"/*; do
  [[ -f "$node/requirements.txt" ]] || continue
  uv pip install --python "$VENV_DIR/bin/python" -r "$node/requirements.txt"
done

if (( DOWNLOAD_MODELS )); then
  uv pip install --python "$VENV_DIR/bin/python" "huggingface_hub[hf_xet]"
  mkdir -p "$COMFY_DIR/models" "$COMFY_DIR/models/loras"
  COMFY_DIR="$COMFY_DIR" "$VENV_DIR/bin/python" - <<'PY'
from huggingface_hub import hf_hub_download
from pathlib import Path
import os

root = Path(os.environ["COMFY_DIR"])
downloads = [
    ("Comfy-Org/MiniMax-H3", "main", "vae/minimax_h3_video_vae_fp16.safetensors", root / "models" / "vae"),
    ("Comfy-Org/MiniMax-H3", "main", "vae/minimax_h3_audio_vae_fp32.safetensors", root / "models" / "vae"),
    ("Comfy-Org/MiniMax-H3", "main", "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors", root / "models" / "diffusion_models"),
    ("lightx2v/Minimax-h3-Turbo", "main", "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", root / "models" / "loras"),
]
for repo, revision, filename, target in downloads:
    target.mkdir(parents=True, exist_ok=True)
    print(f"downloading {repo}:{filename}", flush=True)
    hf_hub_download(repo_id=repo, revision=revision, filename=filename, local_dir=target)
PY
else
  echo "Models skipped. Re-run with --download-models after confirming disk and license constraints."
fi

echo "Mac ComfyUI scaffold ready: $COMFY_DIR"
echo "Start: $VENV_DIR/bin/python $COMFY_DIR/main.py --listen 127.0.0.1 --port 8188"
