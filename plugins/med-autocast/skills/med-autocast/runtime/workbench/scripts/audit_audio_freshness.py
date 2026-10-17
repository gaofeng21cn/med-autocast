#!/usr/bin/env python3
"""Check the byte bindings of every registered narration through publish.

This is a structural freshness check. It does not approve pronunciation or
replace the waveform lineage audit, but it makes the common failure mode
visible: a repaired source take exists while timing, mix, render, or the
user-facing MP4 still points at an older byte set.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import wave
from pathlib import Path

import yaml

from delivery_layout import locations


def sha(path: Path) -> str | None:
    if not path.is_file():
        return None
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_json(path: Path) -> dict:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def wav_duration(path: Path) -> float | None:
    if not path.is_file():
        return None
    try:
        with wave.open(str(path), "rb") as handle:
            return handle.getnframes() / handle.getframerate()
    except (OSError, EOFError, wave.Error, ZeroDivisionError):
        return None


def build_current(project: Path) -> tuple[bool, str | None]:
    """A matching old bundle/movie pair does not prove current source inputs."""
    from paper_project import assert_built
    try:
        assert_built(project)
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return False, str(exc)
    return True, None


def project_report(workspace: Path, series: str, episode: str, row: dict) -> dict:
    project = (workspace / row["project"]).resolve()
    project_data = read_json(project / "project.json")
    score = project / project_data.get("score", "score.json")
    voice = project / project_data.get("voice", "audio/narration-normalized.wav")
    audio = project / project_data.get("audio", "audio.wav")
    narration = project / "audio/narration_beats.json"
    timing = read_json(project / "audio/timing-receipt.json")
    mix = read_json(project / "audio/mix-receipt.json")
    current = read_json(project / "out/current.json")
    receipt = read_json(narration)

    voice_sha = sha(voice)
    score_sha = sha(score)
    audio_sha = sha(audio)
    bundle_sha = sha(project / "dist/film.js")
    build_inputs_current, build_diagnostic = build_current(project)
    current_path = Path(current.get("path", ""))
    if current_path and not current_path.is_absolute():
        current_path = project / current_path
    publish_path = locations(workspace, series, episode)["user"] / "video.mp4"

    source_flags: list[str] = []
    source_rows: list[dict] = []
    splice = receipt.get("splice") if isinstance(receipt.get("splice"), dict) else {}
    if splice.get("schema") != "narration_splice/v2":
        source_flags.append("legacy_or_missing_splice_receipt")
    for beat in receipt.get("beats", []):
        source = Path(str(beat.get("audio", "")))
        if not source.is_absolute():
            source = project / source
        actual_sha = sha(source)
        duration = wav_duration(source)
        expected = None
        if beat.get("start") is not None and beat.get("end") is not None:
            try:
                expected = float(beat["end"]) - float(beat["start"])
            except (TypeError, ValueError):
                expected = None
        flags = []
        if actual_sha is None:
            flags.append("missing_source_take")
        if beat.get("source_sha256") and actual_sha != beat.get("source_sha256"):
            flags.append("source_take_hash_mismatch")
        if beat.get("trimmed_head_seconds") not in (None, 0, 0.0):
            flags.append("source_head_was_trimmed")
        if beat.get("trimmed_tail_seconds") not in (None, 0, 0.0):
            flags.append("source_tail_was_trimmed")
        if duration is not None and expected is not None and abs(duration - expected) > 0.003:
            flags.append("beat_duration_does_not_match_source_take")
        if flags:
            source_flags.extend(f"{beat.get('id', '?')}:{flag}" for flag in flags)
        source_rows.append({
            "id": beat.get("id"),
            "source": str(source),
            "source_sha256": actual_sha,
            "declared_duration": expected,
            "actual_duration": duration,
            "flags": flags,
        })

    timing_current = bool(voice_sha and score_sha and
                          timing.get("voice_sha256") == voice_sha and
                          timing.get("score_sha256") == score_sha)
    mix_current = bool(voice_sha and score_sha and audio_sha and
                       mix.get("voice_sha256") == voice_sha and
                       mix.get("score_sha256") == score_sha and
                       mix.get("audio_sha256") == audio_sha)
    render_current = bool(
        build_inputs_current and current.get("status") == "rendered" and current_path.is_file() and
        current.get("sha256") == sha(current_path) and
        current.get("audio_sha256") == audio_sha and
        current.get("score_sha256") == score_sha and
        current.get("bundle_sha256") == bundle_sha
    )
    publish_current = bool(current_path.is_file() and publish_path.is_file() and
                           sha(current_path) == sha(publish_path))

    issues = list(source_flags)
    if not build_inputs_current:
        issues.append("build_inputs_stale_or_missing")
    if not timing_current:
        issues.append("timing_receipt_stale_or_missing")
    if not mix_current:
        issues.append("mix_stale_or_missing")
    if not render_current:
        issues.append("render_stale_or_missing")
    if not publish_current:
        issues.append("published_mp4_stale_or_missing")

    return {
        "series": series,
        "episode": episode,
        "project": str(project),
        "backend": receipt.get("backend"),
        "source_timeline": {
            "status": "bound" if not source_flags else "needs_repair",
            "splice_schema": splice.get("schema"),
            "voice_sha256": voice_sha,
            "duration": wav_duration(voice),
            "beats": source_rows,
        },
        "bindings": {
            "build_inputs_current": build_inputs_current,
            "build_diagnostic": build_diagnostic,
            "timing_current": timing_current,
            "mix_current": mix_current,
            "render_current": render_current,
            "publish_current": publish_current,
            "voice_sha256": voice_sha,
            "score_sha256": score_sha,
            "audio_sha256": audio_sha,
            "bundle_sha256": bundle_sha,
            "current_video": str(current_path) if current_path else None,
            "published_video": str(publish_path),
        },
        "issues": issues,
        "status": "publish_fresh" if not issues else "needs_refresh",
        "full_listening": "pending",
        "pronunciation_review": "pending",
        "note": "Byte freshness and source boundary checks do not approve pronunciation, tone, or medical meaning.",
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
        if args.series and series != args.series:
            continue
        for episode, row in (spec.get("episodes") or {}).items():
            if args.episode and episode != args.episode:
                continue
            if row.get("project"):
                details.append(project_report(workspace, series, episode, row))
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    summary = {
        "schema": "audio_freshness_audit/v1",
        "episodes_checked": len(details),
        "source_timeline_bound": sum(x["source_timeline"]["status"] == "bound" for x in details),
        "build_inputs_current": sum(x["bindings"]["build_inputs_current"] for x in details),
        "timing_current": sum(x["bindings"]["timing_current"] for x in details),
        "mix_current": sum(x["bindings"]["mix_current"] for x in details),
        "render_current": sum(x["bindings"]["render_current"] for x in details),
        "publish_current": sum(x["bindings"]["publish_current"] for x in details),
        "needs_refresh": sum(x["status"] != "publish_fresh" for x in details),
        "detail": details,
        "note": "This is a structural freshness audit; use audit_narration_lineage.py and human listening for signal and pronunciation review.",
    }
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: summary[k] for k in summary if k != "detail"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
