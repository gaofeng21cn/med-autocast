#!/usr/bin/env python3
"""Audit narration binding from source takes through the user delivery.

This is a read-only Progress First diagnostic. It distinguishes byte binding
from pronunciation, tone, continuous listening, and medical approval.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import math
import wave
from pathlib import Path

import yaml

from delivery_layout import locations


METHOD = "receipt_sha256_binding_read_only_v1"


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def wav_duration(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / handle.getframerate()
    except (OSError, wave.Error, ZeroDivisionError):
        return None


def _path(project: Path, value: str, default: str) -> Path:
    raw = value or default
    path = Path(raw)
    return path if path.is_absolute() else project / path


def _beat_time(beat: dict, key: str, flags: list[str]) -> float | None:
    """Incomplete model-authored metadata is a diagnostic, not a batch failure."""
    value = beat.get(key)
    if value is None:
        flags.append(f"missing_beat_{key}")
        return None
    try:
        number = float(value) if not isinstance(value, bool) else math.nan
    except (TypeError, ValueError, OverflowError):
        number = math.nan
    if not math.isfinite(number) or number < 0:
        flags.append(f"invalid_beat_{key}")
        return None
    return number


def inspect_episode(workspace: Path, series: str, episode: str, row: dict) -> dict:
    project = (workspace / row["project"]).resolve()
    project_data = read_json(project / "project.json")
    score = _path(project, project_data.get("score"), "score.json")
    voice = _path(project, project_data.get("voice"), "audio/narration-normalized.wav")
    audio = _path(project, project_data.get("audio"), "audio.wav")
    narration_path = project / "audio/narration_beats.json"
    narration = read_json(narration_path)
    timing = read_json(project / "audio/timing-receipt.json")
    mix = read_json(project / "audio/mix-receipt.json")
    current = read_json(project / "out/current.json")
    bundle = project / "dist/film.js"

    current_raw = current.get("path")
    current_path = Path(current_raw) if isinstance(current_raw, str) and current_raw else None
    if current_path and not current_path.is_absolute():
        current_path = project / current_path
    publish_path = locations(workspace, series, episode)["user"] / "video.mp4"

    source_issues: list[str] = []
    source_rows: list[dict] = []
    splice = narration.get("splice") if isinstance(narration.get("splice"), dict) else {}
    beats = narration.get("beats")
    if not isinstance(beats, list) or not beats:
        source_issues.append("missing_or_invalid_beats")
        beats = []
    for index, beat in enumerate(beats):
        if not isinstance(beat, dict):
            flag = "invalid_beat_metadata"
            source_rows.append({
                "id": None, "index": index, "source": None,
                "source_sha256": None, "declared_duration": None,
                "actual_duration": None, "flags": [flag],
            })
            source_issues.append(f"beat[{index}]:{flag}")
            continue
        source = Path(str(beat.get("audio", "")))
        if not source.is_absolute():
            source = project / source
        actual_sha = sha(source)
        duration = wav_duration(source)
        flags: list[str] = []
        start = _beat_time(beat, "start", flags)
        end = _beat_time(beat, "end", flags)
        declared_duration = None
        if start is not None and end is not None:
            if end > start:
                declared_duration = end - start
            else:
                flags.append("nonpositive_beat_duration")
        if actual_sha is None:
            flags.append("missing_source_take")
        if beat.get("source_sha256") and actual_sha != beat.get("source_sha256"):
            flags.append("source_take_hash_mismatch")
        source_rows.append({
            "id": beat.get("id"),
            "source": str(source),
            "source_sha256": actual_sha,
            "declared_duration": declared_duration,
            "actual_duration": duration,
            "flags": flags,
        })
        source_issues.extend(f"{beat.get('id', '?')}:{flag}" for flag in flags)

    voice_sha, score_sha, audio_sha, bundle_sha = map(sha, (voice, score, audio, bundle))
    narration_sha = sha(narration_path)
    source_bound = bool(
        voice_sha and sha(project / "audio/narration.wav") and
        splice.get("normalized_sha256") == voice_sha and
        splice.get("raw_sha256") == sha(project / "audio/narration.wav") and
        not source_issues
    )
    source_policy = "current" if splice.get("schema") == "narration_splice/v2" and splice.get("policy") == "resample_correctly_preserve_all_source_samples" else "legacy_or_unknown"

    timing_bound = bool(
        voice_sha and score_sha and
        timing.get("voice_sha256") == voice_sha and
        timing.get("score_sha256") == score_sha
    )
    mix_bound = bool(
        voice_sha and score_sha and audio_sha and
        mix.get("voice_sha256") == voice_sha and
        mix.get("score_sha256") == score_sha and
        mix.get("audio_sha256") == audio_sha
    )
    render_bound = bool(
        current.get("status") == "rendered" and current_path and current_path.is_file() and
        current.get("sha256") == sha(current_path) and
        current.get("audio_sha256") == audio_sha and
        current.get("score_sha256") == score_sha and
        current.get("bundle_sha256") == bundle_sha
    )
    published_sha = sha(publish_path)
    current_sha = sha(current_path) if current_path else None
    publish_bound = bool(current_sha and published_sha and current_sha == published_sha)

    issues = list(source_issues)
    if not source_bound:
        issues.append("source_binding_stale_or_missing")
    if source_policy != "current":
        issues.append("source_splice_policy_legacy_or_unknown")
    if not timing_bound:
        issues.append("timing_binding_stale_or_missing")
    if not mix_bound:
        issues.append("mix_binding_stale_or_missing")
    if not render_bound:
        issues.append("render_binding_stale_or_missing")
    stale_reasons: list[str] = []
    if not publish_path.is_file():
        stale_reasons.append("published_mp4_missing")
    elif not current_path or not current_path.is_file():
        stale_reasons.append("current_render_missing")
    elif current_sha != published_sha:
        stale_reasons.append("published_mp4_sha_mismatch")
    if stale_reasons:
        issues.extend(stale_reasons)

    return {
        "schema": "audio_delivery_binding/v1",
        "generated_at": _timestamp(),
        "method": METHOD,
        "series": series,
        "episode": episode,
        "project": str(project),
        "source": {
            "bound": source_bound,
            "policy": source_policy,
            "splice_schema": splice.get("schema"),
            "narration_beats_sha256": narration_sha,
            "voice_sha256": voice_sha,
            "duration": wav_duration(voice),
            "beats": source_rows,
        },
        "bindings": {
            "timing_bound": timing_bound,
            "mix_bound": mix_bound,
            "render_bound": render_bound,
            "publish_bound": publish_bound,
            "voice_sha256": voice_sha,
            "score_sha256": score_sha,
            "audio_sha256": audio_sha,
            "bundle_sha256": bundle_sha,
            "current_video": str(current_path) if current_path else None,
            "current_video_sha256": current_sha,
            "published_video": str(publish_path),
            "published_video_sha256": published_sha,
        },
        "stale_publish": bool(stale_reasons),
        "stale_publish_reasons": stale_reasons,
        "issues": issues,
        "status": "publish_fresh" if not issues else "attention_required",
        "full_listening": "pending",
        "pronunciation_review": "pending",
        "tone_consistency": "pending",
        "medical_review": "pending",
        "note": "字节绑定和源段边界不等于发音、语气、完整听感或医学终审；本审计只读且不阻断 Progress First。",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path.cwd())
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--series")
    parser.add_argument("--episode")
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    config = yaml.safe_load((workspace / "workbench.yaml").read_text(encoding="utf-8")) or {}
    details = []
    for series, spec in (config.get("series") or {}).items():
        if args.series and args.series != series:
            continue
        for episode, row in (spec.get("episodes") or {}).items():
            if args.episode and args.episode != episode:
                continue
            if row.get("project"):
                details.append(inspect_episode(workspace, series, episode, row))
    summary = {
        "schema": "audio_delivery_binding_batch/v1",
        "generated_at": _timestamp(),
        "method": METHOD,
        "episodes_checked": len(details),
        "source_bound": sum(x["source"]["bound"] for x in details),
        "timing_bound": sum(x["bindings"]["timing_bound"] for x in details),
        "mix_bound": sum(x["bindings"]["mix_bound"] for x in details),
        "render_bound": sum(x["bindings"]["render_bound"] for x in details),
        "publish_bound": sum(x["bindings"]["publish_bound"] for x in details),
        "stale_publish": sum(x["stale_publish"] for x in details),
        "attention_required": sum(x["status"] != "publish_fresh" for x in details),
        "detail": details,
        "note": "只读结构审计；请另行执行 waveform lineage、正常速度完整听辨、发音/语气和医学终审。",
    }
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in summary.items() if key != "detail"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
