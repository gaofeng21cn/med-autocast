#!/usr/bin/env bash
set -euo pipefail

H3_ROOT="${H3_ROOT:-$HOME/ai/minimax-h3}"
COMFY_DIR="$H3_ROOT/ComfyUI"
VENV_DIR="$H3_ROOT/.venv"
COMFY_REF="v0.34.0"
H3_REPO="Comfy-Org/MiniMax-H3"
H3_REV="4cc1d817b6184899b41293954329f576cb5ae86b"
TURBO_REPO="lightx2v/Minimax-h3-Turbo"
TURBO_REV="05ef678438e84933c406131b59abbf86919b3aac"

for command_name in curl git python3; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
done

if command -v nvidia-smi >/dev/null 2>&1; then
  NVIDIA_SMI="$(command -v nvidia-smi)"
elif [[ -x /usr/lib/wsl/lib/nvidia-smi ]]; then
  NVIDIA_SMI="/usr/lib/wsl/lib/nvidia-smi"
else
  echo "nvidia-smi was not found; WSL GPU passthrough is unavailable." >&2
  exit 1
fi

gpu_name="$($NVIDIA_SMI --query-gpu=name --format=csv,noheader | head -n 1)"
gpu_vram_mib="$($NVIDIA_SMI --query-gpu=memory.total --format=csv,noheader,nounits | head -n 1 | tr -d ' ')"
if [[ -z "$gpu_vram_mib" || "$gpu_vram_mib" -lt 22000 ]]; then
  echo "A 24 GB-class NVIDIA GPU is required; detected ${gpu_name:-unknown} (${gpu_vram_mib:-unknown} MiB)." >&2
  exit 1
fi

mkdir -p "$H3_ROOT"
available_kib="$(df -Pk "$H3_ROOT" | awk 'NR==2 {print $4}')"
required_kib=$((70 * 1024 * 1024))
if [[ "$available_kib" -lt "$required_kib" ]]; then
  echo "At least 70 GiB free is required under $H3_ROOT; only $((available_kib / 1024 / 1024)) GiB is available." >&2
  exit 1
fi

ram_kib="$(awk '/MemTotal:/ {print $2}' /proc/meminfo)"
if [[ "$ram_kib" -lt $((48 * 1024 * 1024)) ]]; then
  echo "Warning: less than 48 GiB host RAM detected. CPU offload may fail or thrash." >&2
fi

if [[ ! -d "$COMFY_DIR/.git" ]]; then
  git clone --branch "$COMFY_REF" --depth 1 https://github.com/Comfy-Org/ComfyUI.git "$COMFY_DIR"
else
  current_origin="$(git -C "$COMFY_DIR" remote get-url origin)"
  if [[ "$current_origin" != "https://github.com/Comfy-Org/ComfyUI.git" ]]; then
    echo "Refusing to modify unexpected repository at $COMFY_DIR (origin: $current_origin)." >&2
    exit 1
  fi
  git -C "$COMFY_DIR" fetch --depth 1 origin "refs/tags/$COMFY_REF:refs/tags/$COMFY_REF"
  git -C "$COMFY_DIR" checkout --detach "$COMFY_REF"
fi

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  python3 -m venv "$VENV_DIR"
fi

PYTHON="$VENV_DIR/bin/python"
"$PYTHON" -m pip install --upgrade pip
"$PYTHON" -m pip install torch torchvision torchaudio --extra-index-url https://download.pytorch.org/whl/cu130
"$PYTHON" -m pip install -r "$COMFY_DIR/requirements.txt"
"$PYTHON" -m pip install --upgrade "huggingface_hub[hf_xet]"

H3_REPO="$H3_REPO" H3_REV="$H3_REV" TURBO_REPO="$TURBO_REPO" TURBO_REV="$TURBO_REV" COMFY_DIR="$COMFY_DIR" \
  "$PYTHON" - <<'PY'
import os
from pathlib import Path
from huggingface_hub import hf_hub_download

comfy_dir = Path(os.environ["COMFY_DIR"])
model_dir = comfy_dir / "models"
downloads = [
    (os.environ["H3_REPO"], os.environ["H3_REV"], "diffusion_models/minimax_h3_fl2va_pruned_int8_convrot.safetensors", model_dir),
    (os.environ["H3_REPO"], os.environ["H3_REV"], "text_encoders/qwen3vl_32b_minimax_h3_nvfp4_awq.safetensors", model_dir),
    (os.environ["H3_REPO"], os.environ["H3_REV"], "vae/minimax_h3_video_vae_fp16.safetensors", model_dir),
    (os.environ["H3_REPO"], os.environ["H3_REV"], "vae/minimax_h3_audio_vae_fp32.safetensors", model_dir),
    (os.environ["TURBO_REPO"], os.environ["TURBO_REV"], "minimax_h3_fl2v_turbo_8step_v1.0_comfyui_bf16.safetensors", model_dir / "loras"),
]

for repo_id, revision, filename, local_dir in downloads:
    local_dir.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {repo_id}@{revision[:12]}:{filename}", flush=True)
    hf_hub_download(repo_id=repo_id, revision=revision, filename=filename, local_dir=local_dir)
PY

bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${H3_PROMPT_FILE:-}" && -n "${H3_REFERENCE_IMAGE:-}" ]]; then
  "$PYTHON" "$bundle_dir/prepare_workflow.py" \
    --comfy-dir "$COMFY_DIR" \
    --prompt "$H3_PROMPT_FILE" \
    --reference-image "$H3_REFERENCE_IMAGE"
fi

echo "MiniMax H3 files are installed under $H3_ROOT"
echo "Start with: $bundle_dir/run_h3.sh"
