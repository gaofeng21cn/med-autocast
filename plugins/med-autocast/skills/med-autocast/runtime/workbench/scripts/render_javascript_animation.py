#!/usr/bin/env python3
"""Run a declared JavaScript animation project locally and verify its output."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from check_animation_assets import check_assets


def run(command: list[str], cwd: Path, *, capture_output: bool = False):
    env = dict(os.environ)
    runtime_root = Path(__file__).resolve().parents[1]
    env['MED_AUTOCAST_PLAYWRIGHT_MODULE'] = (runtime_root / 'scripts/playwright_runtime.mjs').as_uri()
    try:
        return subprocess.run(
            command,
            cwd=cwd,
            check=True,
            env=env,
            capture_output=capture_output,
            text=capture_output,
        )
    except subprocess.CalledProcessError as exc:
        if capture_output:
            if exc.stdout:
                print(exc.stdout, end='')
            if exc.stderr:
                print(exc.stderr, end='', file=sys.stderr)
        raise SystemExit(
            "JS 渲染失败，请查看上方错误。项目自身 import 'playwright' 需要项目 npm install；"
            "使用工作区共享依赖时，入口应动态 import(process.env.MED_AUTOCAST_PLAYWRIGHT_MODULE)。"
            "缺少 Chromium 时重跑工作区 setup_workbench.sh。"
        ) from exc


def renderer_selection_report(
    requested_style_id: str | None,
    requested_renderer_id: str | None,
    renderer_runtime: dict,
) -> dict:
    renderer_runtime = renderer_runtime if isinstance(renderer_runtime, dict) else {}
    requested_style_id = requested_style_id or renderer_runtime.get('requested_style_id')
    actual_style_id = renderer_runtime.get('style_id')
    actual_renderer_id = renderer_runtime.get('renderer_id')
    debts = []
    if requested_style_id and not actual_style_id:
        debts.append({
            'code': 'style_realization_unreported',
            'requested': requested_style_id,
            'actual': None,
            'owner_stage': 'visual-review',
            'blocks_stage_progress': False,
        })
    elif requested_style_id and actual_style_id != requested_style_id:
        debts.append({
            'code': 'style_realization_mismatch',
            'requested': requested_style_id,
            'actual': actual_style_id,
            'owner_stage': 'story-directing',
            'blocks_stage_progress': False,
        })
    if requested_renderer_id and actual_renderer_id != requested_renderer_id:
        debts.append({
            'code': 'renderer_selection_mismatch',
            'requested': requested_renderer_id,
            'actual': actual_renderer_id,
            'owner_stage': 'media-production',
            'blocks_stage_progress': False,
        })
    return {
        'requested_style_id': requested_style_id,
        'actual_style_id': actual_style_id,
        'style_match': (actual_style_id == requested_style_id) if requested_style_id and actual_style_id else None,
        'style_realization_reported': bool(actual_style_id),
        'requested_renderer_id': requested_renderer_id,
        'actual_renderer_id': actual_renderer_id,
        'renderer_match': actual_renderer_id == requested_renderer_id if requested_renderer_id else None,
        'quality_debt': debts,
    }


def asset_admission_quality_debt(admission: dict) -> list[dict]:
    pending = admission.get("pending", []) if isinstance(admission, dict) else []
    if not pending:
        return []
    return [{
        "code": "asset_review_pending",
        "owner_stage": "visual-review",
        "blocks_stage_progress": False,
        "blocks_quality_export": True,
        "details": pending,
    }]


def write_attempt_diagnostic(
    *,
    project: Path,
    output: Path | None,
    preview_output: Path | None,
    admission: dict,
    requested_style_id: str | None,
    requested_renderer_id: str | None,
    reason: str,
    failure_code: str,
) -> dict:
    renderer_selection = renderer_selection_report(
        requested_style_id, requested_renderer_id, {}
    )
    output_created = bool(output and output.is_file())
    diagnostic = {
        "schema": "medical_video_render_attempt_diagnostic/v1",
        "status": "output_unverified_with_quality_debt" if output_created else "not_rendered_with_quality_debt",
        "backend": "javascript_animation",
        "project": str(project),
        "output_target": str(output) if output else None,
        "asset_admission": admission,
        "renderer_selection": renderer_selection,
        "quality_debt": [
            {
                "code": failure_code,
                "owner_stage": "media-production",
                "blocks_stage_progress": False,
                "blocks_quality_export": True,
                "detail": reason[:2000],
            },
            *asset_admission_quality_debt(admission),
            *renderer_selection["quality_debt"],
        ],
        "release_eligible": False,
        "output_created": output_created,
    }
    receipt_path = None
    if preview_output is not None:
        receipt_path = preview_output / "preview.json"
    elif output is not None:
        receipt_path = output.with_suffix(".receipt.json")
    if receipt_path is not None:
        receipt_path.parent.mkdir(parents=True, exist_ok=True)
        if not receipt_path.exists():
            receipt_path.write_text(
                json.dumps(diagnostic, ensure_ascii=False, indent=2) + "\n"
            )
            diagnostic["diagnostic_receipt"] = str(receipt_path)
        else:
            diagnostic["diagnostic_receipt"] = None
            diagnostic["quality_debt"].append({
                "code": "diagnostic_receipt_path_already_exists",
                "owner_stage": "media-production",
                "blocks_stage_progress": False,
                "blocks_quality_export": True,
                "detail": str(receipt_path),
            })
    print(json.dumps(diagnostic, ensure_ascii=False))
    return diagnostic


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project-root", type=Path, required=True)
    parser.add_argument("--render-entry", default="work/render_frames.mjs")
    parser.add_argument("--mux-entry", default="work/mux.mjs")
    parser.add_argument("--fps", type=int, default=24)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--html-entry", default="index.html")
    parser.add_argument("--audio", type=Path, help="共享渲染入口使用的最终旁白（可为已混音音轨）")
    parser.add_argument("--width", type=int, default=1280)
    parser.add_argument("--height", type=int, default=720)
    parser.add_argument("--asset-manifest", type=Path, default=Path("asset_manifest.json"))
    parser.add_argument("--requested-style-id")
    parser.add_argument("--requested-renderer-id")
    parser.add_argument("--start", type=float)
    parser.add_argument("--end", type=float)
    parser.add_argument("--check-only", action="store_true")
    parser.add_argument("--preview", action="store_true", help="Capture storyboard poses and contact sheet without encoding MP4")
    parser.add_argument("--preview-output", type=Path, help="Directory for preview evidence")
    parser.add_argument("--review-candidate", action="store_true",
                        help="Allow pending assets in a non-release review candidate; rejected or invalid assets produce a diagnostic")
    args = parser.parse_args()
    if any(shutil.which(tool) is None for tool in ("node", "ffmpeg", "ffprobe")):
        raise SystemExit("需要 Node.js 20+ 和 ffprobe；请先运行 bash scripts/setup_workbench.sh")
    project = args.project_root.resolve()
    if args.preview and args.output:
        raise SystemExit("--preview 使用 --preview-output 指定目录，不能同时传 --output")
    output = args.output.resolve() if args.output else project / "out" / "video.mp4"
    if not args.preview and not args.check_only and output.exists():
        raise SystemExit("输出已存在，请使用新的修订路径")
    preview_output = (
        args.preview_output.resolve()
        if args.preview and args.preview_output
        else project / "qa" / "preview" if args.preview else None
    )
    try:
        admission = check_assets(project / args.asset_manifest)
    except (ValueError, OSError, TypeError, KeyError, AttributeError) as exc:
        admission = {
            "status": "blocked",
            "manifest": str((project / args.asset_manifest).resolve()),
            "error": str(exc),
            "domain_quality_approved": False,
        }
    if args.check_only:
        print(json.dumps(admission, ensure_ascii=False))
        return
    if admission.get("error") or (
        admission.get("status") != "passed" and not args.review_candidate
    ):
        write_attempt_diagnostic(
            project=project,
            output=None if args.preview else output,
            preview_output=preview_output,
            admission=admission,
            requested_style_id=args.requested_style_id,
            requested_renderer_id=args.requested_renderer_id,
            reason=admission.get("error") or "素材审查仍有待处理项；未生成可交付视频。",
            failure_code="asset_admission_unresolved",
        )
        return
    admission["render_mode"] = "review_candidate" if args.review_candidate else "approved_assets"
    admission["release_eligible"] = False
    if args.preview:
        output_dir = preview_output
        config = {"project_root": str(project), "entry": args.html_entry,
                  "output": str(output_dir), "width": args.width, "height": args.height,
                  "start": args.start, "end": args.end}
        try:
            with tempfile.TemporaryDirectory(prefix="med-animation-preview-") as temporary:
                config_path = Path(temporary) / "preview.json"
                config_path.write_text(json.dumps(config))
                run(["node", str(Path(__file__).with_name("preview_local_animation.mjs")), str(config_path)], project)
        except (SystemExit, OSError, subprocess.CalledProcessError) as exc:
            report_path = output_dir / "preview.json"
            if report_path.is_file():
                report = json.loads(report_path.read_text())
                report["status"] = "preview_attempted_with_quality_debt"
                report["asset_admission"] = admission
                report["quality_debt"] = [
                    *report.get("quality_debt", []),
                    *asset_admission_quality_debt(admission),
                    {
                        "code": "animation_preview_failed",
                        "owner_stage": "media-production",
                        "blocks_stage_progress": False,
                        "blocks_quality_export": True,
                        "detail": str(exc)[:2000],
                    },
                ]
                report["release_eligible"] = False
                report["output_created"] = bool(report.get("frames"))
                report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
                print(json.dumps(report, ensure_ascii=False))
            else:
                write_attempt_diagnostic(
                    project=project,
                    output=None,
                    preview_output=output_dir,
                    admission=admission,
                    requested_style_id=args.requested_style_id,
                    requested_renderer_id=args.requested_renderer_id,
                    reason=str(exc) or "JavaScript 动画预览未能完成。",
                    failure_code="animation_preview_failed",
                )
            return
        report_path = output_dir / "preview.json"
        if report_path.is_file():
            report = json.loads(report_path.read_text())
            report["renderer_selection"] = renderer_selection_report(
                args.requested_style_id,
                args.requested_renderer_id,
                report.get("renderer_runtime", {}),
            )
            report["asset_admission"] = admission
            report["quality_debt"] = [
                *asset_admission_quality_debt(admission),
                *report["renderer_selection"]["quality_debt"],
            ]
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
        else:
            report = {
                "schema": "medical_video_render_attempt_diagnostic/v1",
                "status": "preview_attempted_with_quality_debt",
                "output": str(output_dir),
                "asset_admission": admission,
                "quality_debt": [
                    *asset_admission_quality_debt(admission),
                    {
                    "code": "preview_receipt_missing",
                    "owner_stage": "visual-review",
                    "blocks_stage_progress": False,
                    },
                ],
                "release_eligible": False,
                "output_created": False,
            }
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
            print(json.dumps(report, ensure_ascii=False))
        return
    render_entry = project / args.render_entry
    mux_entry = project / args.mux_entry
    renderer_runtime = {}
    try:
        if args.audio:
            config = {"project_root": str(project), "entry": args.html_entry,
                      "audio": str(args.audio.resolve()), "output": str(output),
                      "fps": args.fps, "width": args.width, "height": args.height}
            with tempfile.TemporaryDirectory(prefix="med-animation-") as temporary:
                config_path = Path(temporary) / "render.json"
                config_path.write_text(json.dumps(config))
                result = run(
                    ["node", str(Path(__file__).with_name("render_local_animation.mjs")), str(config_path)],
                    project,
                    capture_output=True,
                )
                if result and result.stdout.strip():
                    render_info = json.loads(result.stdout.strip().splitlines()[-1])
                    renderer_runtime = render_info.get("renderer_runtime", {})
        else:
            if not project.is_dir() or not render_entry.is_file() or not mux_entry.is_file():
                raise SystemExit("通用渲染请提供 --audio 与 index.html；自定义项目需提供 render/mux 入口")
            run(["node", str(render_entry), f"--fps={args.fps}"], project)
            run(["node", str(mux_entry)], project)
        if not output.is_file():
            raise SystemExit(f"JavaScript renderer did not create output: {output}")
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type", "-of", "json", str(output)],
            check=True,
            capture_output=True,
            text=True,
        )
        metadata = json.loads(probe.stdout)
    except (SystemExit, subprocess.CalledProcessError, OSError, json.JSONDecodeError) as exc:
        diagnostic = write_attempt_diagnostic(
            project=project,
            output=output,
            preview_output=None,
            admission=admission,
            requested_style_id=args.requested_style_id,
            requested_renderer_id=args.requested_renderer_id,
            reason=str(exc) or "JavaScript 动画渲染未能完成或验证。",
            failure_code="animation_render_failed",
        )
        return
    renderer_selection = renderer_selection_report(
        args.requested_style_id,
        args.requested_renderer_id,
        renderer_runtime,
    )
    receipt = {"status": "rendered", "backend": "javascript_animation", "output": str(output),
               "metadata": metadata, "asset_admission": admission,
               "renderer_selection": renderer_selection,
               "quality_debt": [
                   *asset_admission_quality_debt(admission),
                   *renderer_selection["quality_debt"],
               ],
               "release_eligible": False}
    output.with_suffix(".receipt.json").write_text(json.dumps(receipt, ensure_ascii=False, indent=2))
    print(json.dumps(receipt, ensure_ascii=False))


if __name__ == "__main__":
    main()
