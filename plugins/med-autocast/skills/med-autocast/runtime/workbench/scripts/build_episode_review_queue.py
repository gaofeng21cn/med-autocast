#!/usr/bin/env python3
"""Build a non-blocking, per-episode review queue.

This command is deliberately a coordinator, not a quality scorer.  It reads
the current workbench registration and locates evidence needed by the audio
lineage and semantic visual reviews.  Missing evidence becomes a review task;
the command keeps enumerating other episodes and never labels a video passed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import yaml


def _path(base: Path, value: str | None) -> Path | None:
    if not value:
        return None
    path = Path(value)
    return path if path.is_absolute() else base / path


def _first_existing(*paths: Path | None) -> Path | None:
    for path in paths:
        if path is not None and path.is_file():
            return path
    return None


def inspect_episode(workspace: Path, series_id: str, episode_id: str, spec: dict) -> dict:
    project = _path(workspace, spec.get("project"))
    missing: list[str] = []
    tasks: list[str] = []
    audio_evidence_incomplete = False
    evidence: dict[str, str | None] = {
        "project": str(project) if project else None,
        "score": None,
        "directions": None,
        "narration_receipt": None,
        "current_media": None,
        "narration_prefix_audit": None,
    }
    prefix_audit = workspace / "work/audit-20261014/audio-asr/narration-prefix-review.json"
    if prefix_audit.is_file():
        evidence["narration_prefix_audit"] = str(prefix_audit)
    if project is None or not project.is_dir():
        missing.append("project")
        tasks.append("恢复或登记本集当前制作工程")
    else:
        score = _first_existing(project / "score.json", project / "score.yaml")
        directions = _first_existing(
            project / "scene_directions.json",
            project / "preproduction/scene_directions.json",
            project / "preproduction/DIRECTOR.md",
        )
        beats = project / "audio/narration_beats.json"
        narration_track = project / "audio/narration-normalized.wav"
        project_config = project / "project.json"
        mixed_track: Path | None = None
        if project_config.is_file():
            try:
                audio_name = json.loads(project_config.read_text(encoding="utf-8")).get("audio", "audio.wav")
                mixed_track = _path(project, audio_name)
            except (OSError, ValueError, TypeError):
                tasks.append("检查 project.json 的混音引用")
        current = project / "out/current.json"
        evidence["score"] = str(score) if score else None
        evidence["directions"] = str(directions) if directions else None
        evidence["narration_receipt"] = str(beats) if beats.is_file() else None
        audio_missing = []
        if beats.is_file():
            try:
                receipt = json.loads(beats.read_text(encoding="utf-8"))
                for beat in receipt.get("beats", []):
                    source = _path(project, beat.get("audio"))
                    if source is None or not source.is_file():
                        audio_missing.append(f"source_take:{beat.get('id', 'unknown')}")
            except (OSError, ValueError, TypeError):
                audio_missing.append("unreadable_narration_receipt")
        for label, path in (("normalized_narration", narration_track), ("mixed_audio", mixed_track)):
            if path is None or not path.is_file():
                audio_missing.append(label)
        if audio_missing:
            audio_evidence_incomplete = True
            tasks.append("补齐或定位音频链路文件：" + "、".join(audio_missing))
        if score is None:
            missing.append("score")
            tasks.append("补齐当前 Score，确认镜头和时码来源")
        if directions is None:
            missing.append("directions")
            tasks.append("补齐本集独立导演稿/镜头语义说明")
        if not beats.is_file():
            missing.append("narration_receipt")
            tasks.append("生成或登记逐段旁白回执，再做段首链路核对")
        current_path: Path | None = None
        if current.is_file():
            try:
                value = json.loads(current.read_text(encoding="utf-8")).get("path")
                current_path = _path(project, value)
            except (OSError, ValueError, TypeError):
                tasks.append("修复 out/current.json，使当前媒体指针可回读")
        if current_path is None or not current_path.is_file():
            missing.append("current_media")
            tasks.append("定位或生成当前候选媒体；不要把旧版或归档当作当前版")
        else:
            evidence["current_media"] = str(current_path)
    if "narration_receipt" not in missing:
        tasks.append("沿源 take → 拼接轨 → 归一化轨 → mix → MP4 做实际段首/接缝审计")
    if evidence["narration_prefix_audit"] is None:
        tasks.append("生成当前源 take 段首 ASR 定位表，并把疑似省略、术语和发音差异加入人工听辨队列")
    tasks.append("隐藏字幕和解释标签，逐镜反向读图并核对同期事实、关系、变化和可能误读")
    tasks.append("按需看首帧、切点、动作极值、结果状态、邻镜和正常速度连续窗口")
    tasks.append("分别记录无 BGM、最终混音和医学终审的真实覆盖；未听/未审保持 pending")
    status = "needs_input_repair" if missing else "candidate_ready_needs_episode_review"
    return {
        "series_id": series_id,
        "episode_id": episode_id,
        "project": str(project) if project else None,
        "status": status,
        "missing_inputs": missing,
        "next_tasks": tasks,
        "evidence": evidence,
        "semantic_review": "pending",
        "audio_lineage_review": "evidence_incomplete" if audio_evidence_incomplete or "narration_receipt" in missing else "pending",
        "continuous_motion_review": "pending",
        "full_listening": "pending",
        "medical_review": "pending",
        "release_eligible": False,
        "note": "队列只导航逐集证据，不评分、不批准、不阻断其他可消费工作",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--series", default="")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    config_path = workspace / "workbench.yaml"
    if not config_path.is_file():
        raise SystemExit(f"missing workbench config: {config_path}")
    config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    episodes: list[dict] = []
    for series_id, series in sorted((config.get("series") or {}).items()):
        if args.series and series_id != args.series:
            continue
        for episode_id, spec in sorted((series.get("episodes") or {}).items()):
            episodes.append(inspect_episode(workspace, series_id, episode_id, spec or {}))
    summary = {
        "episodes": len(episodes),
        "needs_input_repair": sum(row["status"] == "needs_input_repair" for row in episodes),
        "candidate_ready_needs_episode_review": sum(
            row["status"] == "candidate_ready_needs_episode_review" for row in episodes
        ),
        "semantic_review_approved_by_this_tool": 0,
        "audio_review_approved_by_this_tool": 0,
    }
    report = {
        "schema": "episode_review_queue/v1",
        "summary": summary,
        "episodes": episodes,
        "method": "current registration and evidence locator only; no quality scoring or approval",
    }
    output = args.output or workspace / "work/episode-review-queue.json"
    output = output if output.is_absolute() else workspace / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown = output.with_suffix(".md")
    lines = [
        "# 逐集复核队列",
        "",
        "本表只登记每集当前证据和下一步任务，不把工程检查、元数据或未覆盖范围当作通过。",
        "",
        f"共 {summary['episodes']} 集；需补输入 {summary['needs_input_repair']} 集；可进入逐集审片 {summary['candidate_ready_needs_episode_review']} 集。",
        "",
        "| 系列 | 集数 | 状态 | 缺项 | 下一步 |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in episodes:
        missing = "、".join(row["missing_inputs"]) or "—"
        task = row["next_tasks"][0] if row["next_tasks"] else "逐集审片"
        lines.append(f"| {row['series_id']} | {row['episode_id']} | {row['status']} | {missing} | {task} |")
    markdown.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"summary": summary, "json": str(output), "markdown": str(markdown)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
