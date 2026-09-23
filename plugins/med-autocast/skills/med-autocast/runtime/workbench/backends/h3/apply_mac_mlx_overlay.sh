#!/usr/bin/env bash
set -euo pipefail

H3_MAC_ROOT="${H3_MAC_ROOT:-$HOME/ai/minimax-h3-mac}"
node_dir="${1:-$H3_MAC_ROOT/ComfyUI/custom_nodes/ComfyUI-MiniMax-H3-MLX-SolAttn}"
bundle_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
overlay_dir="$bundle_dir/mac-mlx-overlay"
expected_revision="55bb7ddd015321a25385683419951e7c7f518775"
files=(
  comfyui_nodes.py
  minimax_h3_mlx/staged.py
  tests/test_comfy_workflow.py
  tests/test_comfyui_nodes.py
  workflows/minimax_h3_mlx_turbo4_sol.json
  workflows/minimax_h3_mlx_36gb_compat_turbo4_sol.json
)

if [[ ! -d "$node_dir/.git" ]]; then
  echo "MLX node repository was not found: $node_dir" >&2
  exit 1
fi

actual_revision="$(git -C "$node_dir" rev-parse HEAD)"
if [[ "$actual_revision" != "$expected_revision" ]]; then
  echo "Overlay expects $expected_revision, found $actual_revision; refusing to overwrite another revision." >&2
  exit 1
fi

if [[ -n "$(git -C "$node_dir" status --porcelain)" ]]; then
  all_match=1
  for relative_path in "${files[@]}"; do
    if [[ ! -f "$node_dir/$relative_path" ]] || ! cmp -s "$overlay_dir/$relative_path" "$node_dir/$relative_path"; then
      all_match=0
      break
    fi
  done
  if (( all_match )); then
    echo "Mac MLX overlay is already applied."
    exit 0
  fi
  echo "MLX node has unrelated or divergent changes; refusing to overwrite them." >&2
  exit 1
fi

for relative_path in "${files[@]}"; do
  mkdir -p "$(dirname "$node_dir/$relative_path")"
  cp "$overlay_dir/$relative_path" "$node_dir/$relative_path"
done

echo "Applied Mac MLX resident and 36GB compatibility overlay."
