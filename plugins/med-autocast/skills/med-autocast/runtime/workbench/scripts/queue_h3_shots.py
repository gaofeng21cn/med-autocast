#!/usr/bin/env python3
"""Queue reviewed series shot prompts against the local H3 ComfyUI workflow."""

import argparse
import copy
import hashlib
import json
import math
import time
import urllib.request
import uuid
from pathlib import Path


def request_json(url: str, payload: dict | None = None) -> dict:
    request = urllib.request.Request(
        url,
        data=None if payload is None else json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="GET" if payload is None else "POST",
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        return json.load(response)


def wait_for_idle(base_url: str, timeout_seconds: int) -> None:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        queue = request_json(f"{base_url}/queue")
        if not queue.get("queue_running") and not queue.get("queue_pending"):
            return
        time.sleep(5)
    raise TimeoutError("ComfyUI queue did not become idle")


def wait_for_prompt(base_url: str, prompt_id: str, timeout_seconds: int) -> dict:
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        record = request_json(f"{base_url}/history/{prompt_id}").get(prompt_id)
        if record and record.get("status", {}).get("status_str") == "error":
            raise RuntimeError(json.dumps(record["status"], ensure_ascii=False))
        if record and record.get("status", {}).get("completed"):
            if record["status"].get("status_str") != "success":
                raise RuntimeError(json.dumps(record["status"], ensure_ascii=False))
            return record
        time.sleep(5)
    raise TimeoutError(f"Prompt {prompt_id} did not complete")


def build_generation_prompt(prompt_spec: dict, shot: dict, reference_lock: str) -> str:
    if "official_prompt" in shot:
        prompt = shot["official_prompt"].strip()
        fields = ["integrated_multimodal_description:", "overall_soundscape:", "non_diegetic_music:"]
        positions = [prompt.find(field) for field in fields]
        if -1 in positions or positions != sorted(positions):
            raise ValueError("Official base prompt needs the three ordered H3 fields")
        if "[Shot 1]" not in prompt:
            raise ValueError("Official base prompt needs [Shot 1]")
        return prompt
    constraints = [prompt_spec["common"]]
    if shot.get("brand_required"):
        brand_common = prompt_spec.get("brand_common")
        if brand_common:
            constraints.append(brand_common)
    else:
        constraints.append(
            "The supplied first frame defines the complete cast and all visible objects."
        )
    motion_prompt = shot["motion_prompt"] if "motion_prompt" in shot else shot["prompt"]
    return (
        f"integrated_multimodal_description: {reference_lock}{motion_prompt}\n\n"
        f"Scene continuity: {' '.join(constraints)}"
    )


def apply_sampling(graph: dict, sampling: dict) -> None:
    if not sampling:
        return
    width, height = int(sampling["width"]), int(sampling["height"])
    if min(width, height) < 32 or width % 32 or height % 32 or width * height > 1344 * 768:
        raise ValueError("H3 canvas must be multiples of 32 within 1344x768 pixel area")
    turbo, steps = sampling["turbo"], int(sampling["steps"])
    if not isinstance(turbo, bool) or not 1 <= steps <= 100 or (turbo and steps != 8):
        raise ValueError("This FL2VA workflow uses Turbo8 or explicit regular steps")
    graph["140:131"]["inputs"].update(width=width, height=height)
    graph["140:139"]["inputs"]["value"] = turbo
    graph["140:138" if turbo else "140:137"]["inputs"]["value"] = steps


def save_receipts(path: Path | None, receipts: list[dict]) -> None:
    if path is None:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps({
        "schema": "minimax_h3_generation_receipt/v1", "review_status": "required", "shots": receipts,
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def recover_submission(base_url: str, client_id: str) -> str | None:
    queue = request_json(f"{base_url}/queue")
    entries = queue.get("queue_running", []) + queue.get("queue_pending", [])
    history = request_json(f"{base_url}/history")
    entries += [record["prompt"] for record in history.values() if "prompt" in record]
    matches = {entry[1] for entry in entries if len(entry) > 3 and entry[3].get("client_id") == client_id}
    if len(matches) > 1:
        raise RuntimeError("Multiple backend tasks match this submission; reconcile before continuing")
    return next(iter(matches), None)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-queue", type=Path, required=True)
    parser.add_argument("--prompts", type=Path, required=True)
    parser.add_argument("--base-url", default="http://127.0.0.1:8188")
    parser.add_argument("--output-prefix", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=1800)
    parser.add_argument("--shot", action="append", dest="shots")
    parser.add_argument("--receipt", type=Path)
    parser.add_argument("--dry-run", type=Path, help="Write prepared graphs without contacting ComfyUI")
    parser.add_argument("--lock-last-frame", action="store_true")
    parser.add_argument("--duration-seconds", type=float)
    parser.add_argument("--ignore-reference-image", action="store_true")
    parser.add_argument("--brand-reference", help="Approved reference already uploaded to this ComfyUI instance")
    args = parser.parse_args()

    snapshot = json.loads(args.base_queue.read_text(encoding="utf-8"))
    graph_template = snapshot["queue_running"][0][2]
    prompt_spec = json.loads(args.prompts.read_text(encoding="utf-8"))
    selected = {value.upper() for value in args.shots or []}
    shots = [shot for shot in prompt_spec["shots"] if not selected or shot["id"].upper() in selected]
    if selected - {shot["id"].upper() for shot in shots}:
        raise SystemExit("One or more requested shot ids do not exist")
    if prompt_spec.get("schema") in {"h3_capability_first_shots/v1", "h3_semantic_shots/v2", "h3_official_ir_shots/v1"}:
        blocked = [shot["id"] for shot in shots if shot.get("status") != "ready_to_generate"]
        if blocked:
            raise SystemExit(
                "Prompt set only queues ready_to_generate shots: "
                + ", ".join(blocked)
            )

    receipts = []
    if args.receipt and args.receipt.is_file():
        receipts = json.loads(args.receipt.read_text(encoding="utf-8")).get("shots", [])

    prepared_graphs = []
    for shot in shots:
        graph = copy.deepcopy(graph_template)
        graph["92"]["inputs"]["filename_prefix"] = f"{args.output_prefix}_{shot['id'].lower()}"
        graph["140:129"]["inputs"]["noise_seed"] = shot["seed"]
        duration = float(args.duration_seconds or shot["duration"])
        if not math.isfinite(duration) or not 4 <= duration <= 15:
            raise ValueError("H3 shots must request 4-15 seconds")
        graph["140:133"]["inputs"]["value"] = duration
        apply_sampling(graph, shot.get("sampling", prompt_spec.get("sampling", {})))
        reference_image = None if args.ignore_reference_image else shot.get("reference_image")
        if shot.get("brand_required"):
            reference_image = shot.get("brand_scene_reference") or args.brand_reference or shot.get("brand_reference_image")
            if not reference_image:
                raise SystemExit(f"Shot {shot['id']} requires an approved author reference")
            if shot.get("requires_brand_scene_keyframe") and not shot.get("brand_scene_reference"):
                raise SystemExit(
                    f"Shot {shot['id']} contains a brand character in a multi-subject scene but has no approved brand scene keyframe"
                )
        reference_lock = ""
        graph["140:131"]["inputs"].pop("first_frame", None)
        graph["140:131"]["inputs"].pop("last_frame", None)
        if reference_image:
            if "141" not in graph or graph["141"].get("class_type") != "LoadImage":
                raise RuntimeError("The selected H3 workflow has no LoadImage node for reviewed references")
            graph["141"]["inputs"]["image"] = reference_image
            graph["140:131"]["inputs"]["first_frame"] = ["141", 0]
            if shot.get("last_reference_image"):
                last_image_node = "reviewed_last_frame"
                if last_image_node in graph:
                    raise RuntimeError("The selected workflow already uses reviewed_last_frame")
                graph[last_image_node] = copy.deepcopy(graph["141"])
                graph[last_image_node]["inputs"]["image"] = shot["last_reference_image"]
                graph["140:131"]["inputs"]["last_frame"] = [last_image_node, 0]
            elif args.lock_last_frame:
                graph["140:131"]["inputs"]["last_frame"] = ["141", 0]
            else:
                graph["140:131"]["inputs"].pop("last_frame", None)
            reference_lock = (
                "Reference-frame lock: Use the supplied first frame as the complete approved scene. "
                "Keep its exact visual style, people, objects, background, camera angle, "
                "framing, and spatial relationships throughout one continuous locked-camera take. "
                "Only the existing people and the existing object named in the action move. Every other "
                "visible element remains visually consistent and every surface remains plain and unmarked.\n\n"
            )
        generation_prompt = build_generation_prompt(prompt_spec, shot, reference_lock)
        if "official_prompt" in shot:
            mode = shot.get("mode")
            has_last = "last_frame" in graph["140:131"]["inputs"]
            actual_mode = "FL2VA" if has_last else "I2VA" if reference_image else "T2VA"
            if mode != actual_mode:
                raise ValueError(f"Shot {shot['id']} mode {mode} does not match inputs {actual_mode}")
            if reference_image and "Picture 1" not in generation_prompt:
                raise ValueError("Official image prompt must align Picture 1")
        graph["140:131"]["inputs"]["prompt"] = generation_prompt
        graph_hash = hashlib.sha256(json.dumps(graph, sort_keys=True).encode()).hexdigest()
        prepared_graphs.append({"shot": shot["id"], "graph": graph, "graph_sha256": graph_hash})
        if args.dry_run:
            continue
        existing = [receipt for receipt in receipts if receipt["shot"] == shot["id"]]
        if len(existing) > 1:
            raise RuntimeError(f"Multiple receipts for {shot['id']}; reconcile before continuing")
        if existing:
            receipt = existing[0]
            if receipt.get("graph_sha256") not in (None, graph_hash):
                raise ValueError("Changed request cannot reuse an existing shot receipt; use a new shot id")
            prompt_id = receipt.get("prompt_id") or recover_submission(args.base_url, receipt["client_id"])
            if not prompt_id:
                raise RuntimeError("Previous submission outcome is unknown; do not automatically resubmit")
        else:
            wait_for_idle(args.base_url, args.timeout_seconds)
            client_id = str(uuid.uuid4())
            receipt = {
                "shot": shot["id"], "client_id": client_id, "status": "submitting",
                "reference_image": reference_image,
                "last_reference_image": shot.get("last_reference_image") if reference_image else None,
                "reference_sha256": shot.get("reference_sha256"),
                "seed": shot["seed"], "requested_duration_seconds": duration,
                "lock_last_frame": bool(reference_image and args.lock_last_frame),
                "generation_prompt": generation_prompt,
                "generation_prompt_sha256": hashlib.sha256(generation_prompt.encode()).hexdigest(),
                "graph": graph, "graph_sha256": graph_hash, "submitted_at": time.time(),
            }
            receipts.append(receipt)
            save_receipts(args.receipt, receipts)
            prompt_id = request_json(
                f"{args.base_url}/prompt", {"prompt": graph, "client_id": client_id}
            )["prompt_id"]
        receipt.update(prompt_id=prompt_id, status="queued")
        save_receipts(args.receipt, receipts)
        print(json.dumps({"event": "queued", "shot": shot["id"], "prompt_id": prompt_id}), flush=True)
        record = wait_for_prompt(args.base_url, prompt_id, args.timeout_seconds)
        output_files = [
            item.get("filename")
            for output in record.get("outputs", {}).values()
            for values in output.values()
            if isinstance(values, list)
            for item in values
            if isinstance(item, dict) and item.get("filename")
        ]
        receipt.update(outputs=output_files, status="generated_review_required", completed_at=time.time())
        save_receipts(args.receipt, receipts)
        print(json.dumps({"event": "completed", "shot": shot["id"], "prompt_id": prompt_id}), flush=True)
    if args.dry_run:
        args.dry_run.parent.mkdir(parents=True, exist_ok=True)
        args.dry_run.write_text(json.dumps(prepared_graphs, ensure_ascii=False, indent=2) + "\n")


if __name__ == "__main__":
    main()
