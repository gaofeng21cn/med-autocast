#!/usr/bin/env python3
"""Render a user service for the explicitly selected runtime directory."""
import argparse
import json
from pathlib import Path


def render(root: Path) -> str:
    root = root.resolve()
    if any(c in str(root) for c in "\r\n\x00"):
        raise ValueError("Runtime path contains a control character")
    template = Path(__file__).with_name("minimax-h3-comfyui.service").read_text()
    directory = json.dumps(str(root / "ComfyUI").replace("%", "%%"), ensure_ascii=False)
    python = json.dumps(str(root / ".venv/bin/python").replace("%", "%%").replace("$", "$$"), ensure_ascii=False)
    return template.replace("@WORKING_DIRECTORY@", directory).replace("@PYTHON@", python)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    print(render(args.root), end="")
