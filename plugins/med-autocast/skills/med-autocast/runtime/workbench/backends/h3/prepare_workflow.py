#!/usr/bin/env python3
import argparse
import json
import shutil
import urllib.request
from pathlib import Path

TEMPLATE_URL = (
    "https://raw.githubusercontent.com/Comfy-Org/workflow_templates/"
    "f331af10934fdf0d773d5f26c1d00f33559ae09d/"
    "templates/video_minimax_h3_t2v.json"
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--comfy-dir", type=Path, required=True)
    parser.add_argument("--prompt", type=Path, required=True)
    parser.add_argument("--reference-image", type=Path, required=True)
    parser.add_argument("--workflow-name", default="minimax_h3_reference")
    args = parser.parse_args()
    if not args.workflow_name or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in args.workflow_name):
        parser.error("--workflow-name must contain only letters, digits, underscores and hyphens")

    with urllib.request.urlopen(TEMPLATE_URL, timeout=60) as response:
        workflow = json.load(response)

    prompt = args.prompt.read_text(encoding="utf-8").strip()
    nodes = {node["id"]: node for node in workflow["nodes"]}

    reference_name = f"{args.workflow_name}{args.reference_image.suffix}"
    input_dir = args.comfy_dir / "input"
    input_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(args.reference_image, input_dir / reference_name)

    nodes[92]["widgets_values"][0] = f"video/{args.workflow_name}"
    nodes[115]["widgets_values"][1] = 0.2
    nodes[140]["widgets_values"][0] = prompt
    nodes[140]["widgets_values"][3] = 14
    nodes[140]["widgets_values"][4] = 409020260903
    nodes[140]["widgets_values"][9] = True
    nodes[140]["widgets_values"][12] = 8

    load_image = {
        "id": 141,
        "type": "LoadImage",
        "pos": [-1760, 4820],
        "size": [320, 310],
        "flags": {},
        "order": 4,
        "mode": 0,
        "inputs": [],
        "outputs": [
            {"name": "IMAGE", "type": "IMAGE", "links": [249, 250]},
            {"name": "MASK", "type": "MASK", "links": None},
        ],
        "properties": {
            "Node name for S&R": "LoadImage",
            "cnr_id": "comfy-core",
            "ver": "0.3.68",
        },
        "widgets_values": [reference_name, "image"],
    }
    nodes[140]["order"] = 5
    nodes[140]["inputs"][0]["link"] = 249
    nodes[140]["inputs"][1]["link"] = 250
    workflow["nodes"].insert(workflow["nodes"].index(nodes[140]), load_image)
    workflow["links"].extend(
        [
            [249, 141, 0, 140, 0, "IMAGE"],
            [250, 141, 0, 140, 1, "IMAGE"],
        ]
    )
    workflow["last_node_id"] = 141
    workflow["last_link_id"] = 250

    output_dir = args.comfy_dir / "user" / "default" / "workflows"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{args.workflow_name}.json"
    output_path.write_text(
        json.dumps(workflow, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"Prepared workflow: {output_path}")


if __name__ == "__main__":
    main()
