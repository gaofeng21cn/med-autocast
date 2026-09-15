#!/usr/bin/env bash
set -euo pipefail

INDEXTTS_MAC_ROOT="${INDEXTTS_MAC_ROOT:-$HOME/ai/index-tts-mac}"
REPO_DIR="$INDEXTTS_MAC_ROOT/src"
VENV_DIR="$INDEXTTS_MAC_ROOT/.venv"
MODEL_DIR="$INDEXTTS_MAC_ROOT/checkpoints"
INDEXTTS_REPO="https://github.com/index-tts/index-tts.git"
INDEXTTS_REV="ee40fa7d6c6b8a2c7f06105f9f1e65775b74868c"
REMOTE_HOST="${INDEXTTS_REMOTE_HOST:-}"
REMOTE_MODEL_ROOT="${INDEXTTS_REMOTE_MODEL_ROOT:-}"
COPY_MODELS=1
if [[ "${1:-}" == "--skip-models" ]]; then
  COPY_MODELS=0
fi

if [[ "$(uname -m)" != "arm64" ]]; then
  echo "This script is for Apple Silicon; use the existing CUDA environment on the 4090." >&2
  exit 2
fi
command -v uv >/dev/null 2>&1 || { echo "uv is required (brew install uv)." >&2; exit 2; }
if (( COPY_MODELS )); then
  if [[ -z "$REMOTE_HOST" || -z "$REMOTE_MODEL_ROOT" ]]; then
    echo "Set INDEXTTS_REMOTE_HOST and INDEXTTS_REMOTE_MODEL_ROOT from your deployment profile, or use --skip-models." >&2
    exit 2
  fi
  command -v rsync >/dev/null 2>&1 || { echo "rsync is required for LAN model transfer." >&2; exit 2; }
  command -v ssh >/dev/null 2>&1 || { echo "ssh is required for LAN model transfer." >&2; exit 2; }
fi

mkdir -p "$INDEXTTS_MAC_ROOT"
if [[ ! -d "$REPO_DIR/.git" ]]; then
  git clone "$INDEXTTS_REPO" "$REPO_DIR"
fi
if [[ "$(git -C "$REPO_DIR" remote get-url origin)" != "$INDEXTTS_REPO" ]]; then
  echo "Refusing unexpected IndexTTS repository: $REPO_DIR" >&2
  exit 1
fi
if [[ "$(git -C "$REPO_DIR" rev-parse HEAD)" != "$INDEXTTS_REV" ]]; then
  if [[ -n "$(git -C "$REPO_DIR" status --porcelain)" ]]; then
    echo "IndexTTS source has local changes on another revision; refusing to overwrite them." >&2
    exit 1
  fi
  git -C "$REPO_DIR" fetch --depth 1 origin "$INDEXTTS_REV"
  git -C "$REPO_DIR" checkout --detach "$INDEXTTS_REV"
fi

# Upstream currently declares Python >=3.10,<3.12; keep this isolated from the
# workbench's Python 3.12 and from the remote 4090 environment.
uv python install 3.11
if [[ ! -x "$VENV_DIR/bin/python" ]]; then
  uv venv --python 3.11 "$VENV_DIR"
fi
uv pip install --python "$VENV_DIR/bin/python" -e "$REPO_DIR"

if (( COPY_MODELS )); then
  if ! ssh -o BatchMode=yes -o ConnectTimeout=5 "$REMOTE_HOST" test -d "$REMOTE_MODEL_ROOT"; then
    echo "IndexTTS model directory is not reachable on $REMOTE_HOST: $REMOTE_MODEL_ROOT" >&2
    exit 1
  fi
  mkdir -p "$MODEL_DIR"
  rsync -a --partial "$REMOTE_HOST:$REMOTE_MODEL_ROOT/" "$MODEL_DIR/"
fi

echo "IndexTTS Mac runtime ready: $INDEXTTS_MAC_ROOT"
if (( COPY_MODELS )); then
  echo "IndexTTS weights copied over LAN from $REMOTE_HOST:$REMOTE_MODEL_ROOT"
else
  echo "Weights skipped. Re-run without --skip-models to copy them from the workstation over LAN."
fi
echo "Smoke device check:"
echo "  $VENV_DIR/bin/python -c 'import torch; print(torch.__version__, torch.backends.mps.is_available())'"
