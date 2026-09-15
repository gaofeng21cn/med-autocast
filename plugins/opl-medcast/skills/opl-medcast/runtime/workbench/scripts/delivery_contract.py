#!/usr/bin/env python3
"""Shared delivery gates for animation sources and release eligibility."""

import json
import subprocess
from pathlib import Path


GENERATIVE_ANIMATION_CLASS = "generative_animation"
LEGACY_HAND_DRAWN_ANIMATION_CLASS = "generative_hand_drawn_animation"
LEGACY_H3_ANIMATION_CLASS = "minimax_h3_hand_drawn_animation"
GENERATIVE_ANIMATION_CLASSES = {
    GENERATIVE_ANIMATION_CLASS,
    LEGACY_HAND_DRAWN_ANIMATION_CLASS,
    LEGACY_H3_ANIMATION_CLASS,
}
DETERMINISTIC_ANIMATION_CLASS = "deterministic_animation"
LEGACY_DETERMINISTIC_ANIMATION_CLASS = "deterministic_hand_drawn_animation"
DETERMINISTIC_ANIMATION_CLASSES = {
    DETERMINISTIC_ANIMATION_CLASS,
    LEGACY_DETERMINISTIC_ANIMATION_CLASS,
}
FINAL_ANIMATION_CLASSES = GENERATIVE_ANIMATION_CLASSES | DETERMINISTIC_ANIMATION_CLASSES
ALLOWED_STATIC_CLASS = "reviewed_visual_insert"
FORBIDDEN_FINAL_STRATEGIES = {"reviewed_keyframe_stable_hold", "static_loop"}
MAX_STATIC_SEGMENT_RATIO = 0.25
MIN_GENERATIVE_DURATION_RATIO = 0.50
LEGACY_ANIMATION_MODE = "hand_drawn_patient_explainer_animation"
LEGACY_VISUAL_STYLE = "hand_drawn_medical_explainer"
REQUIRED_MOTION_REVIEW = "approved_watchable_motion"
REQUIRED_ALIGNMENT_REVIEW = "approved_audio_visual_alignment"


def resolve_visual_source(episode_dir: Path, source: str) -> Path:
    candidate = Path(source)
    if candidate.is_absolute():
        return candidate
    if candidate.parent != Path("."):
        project_candidate = episode_dir.parent.parent / candidate
        if project_candidate.exists():
            return project_candidate
    return episode_dir / "candidates" / candidate.name


def sampled_frame_hashes(video: Path) -> list[str]:
    result = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-i", str(video),
            "-map", "0:v:0", "-vf", "fps=1", "-f", "framemd5", "-",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.rsplit(",", 1)[-1].strip() for line in result.stdout.splitlines() if line and not line.startswith("#")]


def animation_gate(episode_dir: Path, plan: dict) -> dict:
    delivery = plan.get("delivery", {})
    manifest_name = delivery.get("visual_manifest", "visual_delivery_manifest.json")
    manifest_path = episode_dir / manifest_name
    violations: list[str] = []

    visual_requirement = delivery.get("visual_requirement")
    if not visual_requirement:
        violations.append("missing_visual_requirement")
    expected_animation_mode = delivery.get("animation_mode") or LEGACY_ANIMATION_MODE
    expected_visual_style = delivery.get("visual_style") or LEGACY_VISUAL_STYLE
    minimum_generative_ratio = float(
        delivery.get("minimum_generative_duration_ratio", MIN_GENERATIVE_DURATION_RATIO)
    )
    maximum_static_ratio = float(
        delivery.get("maximum_static_duration_ratio", MAX_STATIC_SEGMENT_RATIO)
    )
    primary_backend = delivery.get("primary_video_backend")
    legacy_primary_generator = delivery.get("primary_generator")
    if not primary_backend and not legacy_primary_generator:
        violations.append("missing_primary_video_backend")
    if delivery.get("static_animatic_allowed_as_final") is not False:
        violations.append("static_animatic_final_prohibition_missing")

    legacy_manifest_path = episode_dir / "controlled_visual_manifest.json"
    if legacy_manifest_path.is_file():
        legacy = json.loads(legacy_manifest_path.read_text(encoding="utf-8"))
        if legacy.get("strategy") in FORBIDDEN_FINAL_STRATEGIES or legacy.get("motion") == "none":
            violations.append("legacy_static_fallback_manifest_present")

    manifest = None
    requires_alignment_review = False
    requires_backend_trace = False
    if not manifest_path.is_file():
        violations.append("missing_visual_delivery_manifest")
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        requires_alignment_review = manifest.get("schema") in {
            "medical_video_visual_delivery/v3",
            "medical_video_visual_delivery/v4",
        }
        requires_backend_trace = manifest.get("schema") == "medical_video_visual_delivery/v4"
        if manifest.get("delivery_class") != "final_animation":
            violations.append("visual_manifest_not_final_animation")
        if manifest.get("review_status") != "approved":
            violations.append("visual_animation_not_reviewed")
        if manifest.get("release_eligible") is not True:
            violations.append("visual_manifest_not_release_eligible")
        if manifest.get("visual_style") != expected_visual_style:
            violations.append("visual_manifest_style_mismatch")
        if manifest.get("animation_mode") != expected_animation_mode:
            violations.append("visual_manifest_animation_mode_mismatch")
        style_review = manifest.get("visual_style_review", manifest.get("hand_drawn_style_review"))
        if style_review != "approved":
            violations.append("visual_style_not_reviewed")
        if manifest.get("viewer_engagement_review") != "approved":
            violations.append("viewer_engagement_not_reviewed")
        if manifest.get("noncontradiction_review") != "approved":
            violations.append("visual_noncontradiction_not_reviewed")
        if requires_alignment_review and manifest.get("audio_visual_alignment_review") != "approved":
            violations.append("audio_visual_alignment_not_reviewed")
        manifest_backend = manifest.get("primary_video_backend")
        manifest_legacy_generator = manifest.get("primary_generator")
        if primary_backend:
            if manifest_backend != primary_backend:
                violations.append("visual_manifest_primary_backend_mismatch")
        elif manifest_legacy_generator != legacy_primary_generator:
            violations.append("visual_manifest_primary_generator_mismatch")
        author_profile = delivery.get("author_profile")
        if author_profile and manifest.get("author_profile") != author_profile:
            violations.append("visual_manifest_author_profile_mismatch")
        if delivery.get("brand_identity_policy") or plan.get("director_contract", {}).get("brand_identity_policy"):
            if manifest.get("brand_identity_match") != "approved_against_sole_brand_reference":
                violations.append("brand_identity_not_approved")
        if plan.get("director_contract", {}).get("episode_visual_delta"):
            if manifest.get("episode_visual_delta") != "approved_against_previous_episode":
                violations.append("episode_visual_delta_not_approved")
        if manifest.get("strategy") in FORBIDDEN_FINAL_STRATEGIES or manifest.get("motion") == "none":
            violations.append("static_fallback_cannot_be_final")

    timeline = plan.get("visual_timeline", [])
    manifest_segments = {
        item.get("segment_id"): item
        for item in (manifest or {}).get("segments", [])
        if item.get("segment_id")
    }
    static_segments = []
    animated_segments = []
    generative_segments = []
    deterministic_segments = []
    source_evidence = []
    generative_duration = 0.0
    deterministic_duration = 0.0
    static_duration = 0.0
    timeline_duration = 0.0
    for item in timeline:
        segment_id = item["segment_id"]
        duration = max(0.0, float(item.get("end", 0.0)) - float(item.get("start", 0.0)))
        timeline_duration += duration
        source = resolve_visual_source(episode_dir, item["source"])
        declared = manifest_segments.get(segment_id)
        declared_class = declared.get("visual_class") if declared else None
        if declared is None:
            violations.append(f"visual_manifest_segment_missing:{segment_id}")
        elif Path(declared.get("source", "")).name != source.name:
            violations.append(f"visual_manifest_source_mismatch:{segment_id}")
        elif declared_class not in FINAL_ANIMATION_CLASSES | {ALLOWED_STATIC_CLASS}:
            violations.append(f"unsupported_visual_class:{segment_id}")
        elif declared_class in FINAL_ANIMATION_CLASSES and declared.get("motion_review") != REQUIRED_MOTION_REVIEW:
            violations.append(f"watchable_motion_not_approved:{segment_id}")
        elif requires_alignment_review and declared.get("audio_visual_alignment_review") != REQUIRED_ALIGNMENT_REVIEW:
            violations.append(f"audio_visual_alignment_not_approved:{segment_id}")
        elif (
            requires_backend_trace
            and declared_class in GENERATIVE_ANIMATION_CLASSES
            and not declared.get("backend_id")
        ):
            violations.append(f"generative_backend_not_recorded:{segment_id}")
        elif declared_class in DETERMINISTIC_ANIMATION_CLASSES and declared.get("supporting_explainer_only") is not True:
            violations.append(f"deterministic_animation_not_declared_supporting:{segment_id}")

        if not source.is_file():
            violations.append(f"visual_source_missing:{segment_id}")
            source_evidence.append({"segment_id": segment_id, "source": str(source), "status": "missing"})
            continue
        hashes = sampled_frame_hashes(source)
        distinct = len(set(hashes))
        media_is_static = bool(hashes) and distinct == 1
        if not hashes:
            violations.append(f"visual_source_has_no_sampled_frames:{segment_id}")
        if media_is_static:
            static_segments.append(segment_id)
            static_duration += duration
            if declared_class != ALLOWED_STATIC_CLASS:
                violations.append(f"undeclared_static_source:{segment_id}")
        else:
            animated_segments.append(segment_id)
            if declared_class in GENERATIVE_ANIMATION_CLASSES:
                generative_segments.append(segment_id)
                generative_duration += duration
            if declared_class in DETERMINISTIC_ANIMATION_CLASSES:
                deterministic_segments.append(segment_id)
                deterministic_duration += duration
            if declared_class == ALLOWED_STATIC_CLASS:
                violations.append(f"declared_static_source_is_not_static:{segment_id}")
        source_evidence.append(
            {
                "segment_id": segment_id,
                "source": str(source),
                "visual_class": declared_class,
                "sampled_frames": len(hashes),
                "distinct_sampled_frames": distinct,
                "timeline_duration_seconds": round(duration, 6),
                "status": "static" if media_is_static else "moving",
            }
        )

    static_ratio = static_duration / timeline_duration if timeline_duration else 1.0
    generative_duration_ratio = (
        generative_duration / timeline_duration if timeline_duration else 0.0
    )
    deterministic_duration_ratio = (
        deterministic_duration / timeline_duration if timeline_duration else 0.0
    )
    if not timeline:
        violations.append("empty_visual_timeline")
    if not animated_segments:
        violations.append("no_animated_visual_segments")
    if not generative_segments:
        violations.append("no_generative_animation_segments")
    if generative_duration_ratio < minimum_generative_ratio:
        violations.append("generative_animation_not_primary_by_duration")
    if static_ratio > maximum_static_ratio:
        violations.append("static_duration_ratio_exceeds_limit")

    return {
        "status": "passed" if not violations else "failed",
        "requirement": visual_requirement,
        "visual_style": expected_visual_style,
        "animation_mode": expected_animation_mode,
        "primary_video_backend": primary_backend,
        "primary_generator": legacy_primary_generator,
        "manifest": str(manifest_path),
        "animated_segments": animated_segments,
        "generative_segments": generative_segments,
        "deterministic_supporting_segments": deterministic_segments,
        "static_segments": static_segments,
        "static_segment_ratio": round(static_ratio, 6),
        "maximum_static_segment_ratio": maximum_static_ratio,
        "generative_duration_ratio": round(generative_duration_ratio, 6),
        "minimum_generative_duration_ratio": minimum_generative_ratio,
        "deterministic_supporting_duration_ratio": round(deterministic_duration_ratio, 6),
        "source_evidence": source_evidence,
        "violations": sorted(set(violations)),
    }


def release_eligible(report: dict) -> bool:
    return (
        report.get("status") == "delivery_qa_passed_visual_and_medical_review_required"
        and report.get("delivery_class") == "final_animation"
        and report.get("animation_gate", {}).get("status") == "passed"
    )
