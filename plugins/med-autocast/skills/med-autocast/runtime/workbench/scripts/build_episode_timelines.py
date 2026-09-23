#!/usr/bin/env python3
"""Build reviewed subtitles and beat-aligned production plans for the series."""

import argparse
import difflib
import json
import re
from pathlib import Path

import yaml

from workbench_config import load_author_profile, load_backend_profile, production_root_for, series_paths


EPISODE_RE = re.compile(r"^(\d{2})_(.+)$")
LINE_END_PUNCTUATION_RE = re.compile(r"[，。；：、！？,.!?;:]+$")
LINE_START_PUNCTUATION_RE = re.compile(r"^[，。；：、！？,.!?;:]+")
ALIGNMENT_IGNORED_RE = re.compile(r"[\s，。；：、！？,.!?;:、“”‘’（）()《》<>\-�]+")
MAX_LINE_CHARS = 20
MAX_CAPTION_CHARS = 30
PROTECTED_TERMS: set[str] = set()
HANGING_LINE_END = set("的了和与或在把让是并仍需会可不更也就从向对为由及这那一")
HANGING_LINE_START = set("的了着过吗呢啊呀而且以及")
CONNECTOR_STARTS = (
    "但是", "但", "所以", "因此", "因为", "如果", "同时", "或者", "而是", "也不能",
    "并不", "并且", "需要", "不能", "不是", "还要", "也会", "也可能", "尤其", "反过来",
)
HANGING_LINE_STARTS = ("作为", "以及", "的获益", "的信息")


def visible_length(text: str) -> int:
    return len(re.sub(r"\s+", "", LINE_END_PUNCTUATION_RE.sub("", text)))


def strip_visual_line_punctuation(text: str) -> str:
    """A visual line break already carries the pause, so line-end marks are redundant."""
    return LINE_END_PUNCTUATION_RE.sub("", text.strip())


def alignment_text(text: str) -> str:
    return ALIGNMENT_IGNORED_RE.sub("", text).upper()


def splits_protected_term(text: str, position: int) -> bool:
    for match in re.finditer(r"[A-Za-z]+(?:-\d+)?", text):
        if match.start() < position < match.end():
            return True
    for term in PROTECTED_TERMS:
        cursor = text.find(term)
        while cursor >= 0:
            if cursor < position < cursor + len(term):
                return True
            cursor = text.find(term, cursor + 1)
    return False


def choose_break(text: str, minimum: int, maximum: int, target: float) -> int:
    candidates = []
    upper = min(maximum, len(text) - minimum)
    for position in range(minimum, upper + 1):
        if splits_protected_term(text, position):
            continue
        previous = text[position - 1]
        following = text[position]
        score = -abs(position - target) * 2
        if previous in "，；：、？！":
            score += 80
        if any(text.startswith(connector, position) for connector in CONNECTOR_STARTS):
            score += 28
        if previous in HANGING_LINE_END and not (previous == "的" and following.isascii() and following.isalpha()):
            score -= 45
        if following in HANGING_LINE_START or following in "，。；：、？！":
            score -= 45
        if any(text.startswith(fragment, position) for fragment in HANGING_LINE_STARTS):
            score -= 55
        candidates.append((score, position))
    if not candidates:
        raise ValueError(f"No natural subtitle boundary for: {text!r}")
    return max(candidates)[1]


def split_units(text: str, max_chars: int = MAX_CAPTION_CHARS) -> list[str]:
    text = re.sub(r"\s+", "", text).strip()
    sentences = re.findall(r"[^。！？；]+[。！？；]?", text)
    units: list[str] = []
    for sentence in sentences:
        if visible_length(sentence) <= max_chars:
            units.append(sentence)
            continue
        pieces = [piece for piece in re.split(r"(?<=[，；：])", sentence) if piece]
        current = ""
        for piece in pieces:
            if current and visible_length(current + piece) > max_chars:
                units.append(current)
                current = piece
            else:
                current += piece
        if current:
            units.append(current)

    normalized: list[str] = []
    for unit in units:
        remaining = unit
        while visible_length(remaining) > max_chars:
            split_at = choose_break(remaining, 8, max_chars, max_chars)
            normalized.append(remaining[:split_at])
            remaining = remaining[split_at:]
        if remaining:
            normalized.append(remaining)
    return normalized


def wrap_caption(text: str, line_limit: int = MAX_LINE_CHARS) -> str:
    text = re.sub(r"\s+", "", text).strip()
    if visible_length(text) <= line_limit:
        return strip_visual_line_punctuation(text)

    midpoint = len(text) / 2
    valid = [
        position for position in range(4, len(text) - 5)
        if visible_length(text[:position]) <= line_limit
        and visible_length(text[position:]) <= line_limit
    ]
    if not valid:
        raise ValueError(f"Caption cannot fit two lines: {text!r}")
    split_at = choose_break(text, min(valid), max(valid), midpoint)
    first = strip_visual_line_punctuation(text[:split_at])
    second = LINE_START_PUNCTUATION_RE.sub("", text[split_at:].strip())
    second = strip_visual_line_punctuation(second)
    return f"{first}\n{second}"


def timestamp(seconds: float) -> str:
    milliseconds = round(max(0.0, seconds) * 1000)
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    whole_seconds, milliseconds = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{whole_seconds:02d},{milliseconds:03d}"


def asr_character_times(beat_alignment: dict) -> tuple[str, list[tuple[float, float]]]:
    characters = []
    times = []
    for segment in beat_alignment.get("segments", []):
        for word in segment.get("words", []):
            normalized = alignment_text(word.get("word", ""))
            if not normalized:
                continue
            start = float(word["start"])
            end = float(word["end"])
            duration = max(0.001, end - start)
            for index, character in enumerate(normalized):
                characters.append(character)
                times.append(
                    (
                        start + duration * index / len(normalized),
                        start + duration * (index + 1) / len(normalized),
                    )
                )
    return "".join(characters), times


def align_approved_characters(approved: str, beat_alignment: dict, beat_duration: float) -> tuple[list[tuple[float, float]], float]:
    target = alignment_text(approved)
    observed, observed_times = asr_character_times(beat_alignment)
    if not target or not observed or not observed_times:
        raise ValueError("Whisper alignment contains no usable word timestamps")

    matcher = difflib.SequenceMatcher(None, target, observed, autojunk=False)
    mapped: list[tuple[float, float] | None] = [None] * len(target)
    matched = 0
    for target_start, observed_start, size in matcher.get_matching_blocks():
        for offset in range(size):
            mapped[target_start + offset] = observed_times[observed_start + offset]
            matched += 1

    anchors = [index for index, value in enumerate(mapped) if value is not None]
    if not anchors:
        raise ValueError("Approved narration has no acoustic anchors in Whisper output")
    for index, value in enumerate(mapped):
        if value is not None:
            continue
        previous = max((anchor for anchor in anchors if anchor < index), default=None)
        following = min((anchor for anchor in anchors if anchor > index), default=None)
        if previous is None:
            right = mapped[following][0]
            start = right * index / max(1, following)
            end = right * (index + 1) / max(1, following)
        elif following is None:
            left = mapped[previous][1]
            remaining = len(target) - previous - 1
            start = left + (beat_duration - left) * (index - previous - 1) / max(1, remaining)
            end = left + (beat_duration - left) * (index - previous) / max(1, remaining)
        else:
            left = mapped[previous][1]
            right = mapped[following][0]
            span = following - previous
            start = left + (right - left) * (index - previous - 1) / span
            end = left + (right - left) * (index - previous) / span
        mapped[index] = (max(0.0, start), min(beat_duration, max(start + 0.001, end)))
    return [value for value in mapped if value is not None], matched / len(target)


def build_cues(manifest: dict, alignment: dict | None = None) -> list[dict]:
    cues = []
    alignment_beats = {beat["id"]: beat for beat in alignment.get("beats", [])} if alignment else {}
    for beat in manifest["beats"]:
        units = split_units(beat["text"])
        unit_lengths = [len(alignment_text(unit)) for unit in units]
        if any(length == 0 for length in unit_lengths):
            raise ValueError(f"Empty subtitle unit in {beat['id']}")
        beat_start = float(beat["start"])
        beat_duration = float(beat["end"]) - beat_start
        char_times = None
        match_ratio = None
        if beat["id"] in alignment_beats:
            char_times, match_ratio = align_approved_characters(
                beat["text"], alignment_beats[beat["id"]], beat_duration
            )
        cursor_chars = 0
        for unit, unit_length in zip(units, unit_lengths):
            if char_times:
                start = beat_start + char_times[cursor_chars][0]
                end = beat_start + char_times[cursor_chars + unit_length - 1][1]
            else:
                start = beat_start + beat_duration * cursor_chars / sum(unit_lengths)
                end = beat_start + beat_duration * (cursor_chars + unit_length) / sum(unit_lengths)
            cues.append(
                {
                    "start": round(start, 6),
                    "end": round(end, 6),
                    "text": wrap_caption(unit),
                    "beat_id": beat["id"],
                    "timing_source": "whisper_word_alignment" if char_times else "character_ratio_fallback",
                    "alignment_match_ratio": round(match_ratio, 4) if match_ratio is not None else None,
                }
            )
            cursor_chars += unit_length
    return cues


def write_srt(cues: list[dict], target: Path) -> None:
    lines = []
    for index, cue in enumerate(cues, 1):
        lines.extend(
            [
                str(index),
                f"{timestamp(cue['start'])} --> {timestamp(cue['end'])}",
                cue["text"],
                "",
            ]
        )
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n".join(lines), encoding="utf-8")


def validate_cues(cues: list[dict], duration: float) -> None:
    if not cues:
        raise ValueError("No subtitle cues generated")
    previous_end = 0.0
    for cue in cues:
        if cue["start"] < previous_end - 0.002:
            raise ValueError(f"Subtitle overlap at {cue['start']:.3f}s")
        if cue["end"] <= cue["start"]:
            raise ValueError(f"Invalid subtitle range: {cue}")
        lines = cue["text"].splitlines()
        if len(lines) > 2 or any(visible_length(line) > MAX_LINE_CHARS for line in lines):
            raise ValueError(f"Subtitle layout exceeds limits: {cue['text']!r}")
        if any(LINE_END_PUNCTUATION_RE.search(line) for line in lines):
            raise ValueError(f"Visual line has trailing punctuation: {cue['text']!r}")
        previous_end = cue["end"]
    if previous_end > duration + 0.002:
        raise ValueError(f"Subtitles end at {previous_end:.3f}s, after audio ends at {duration:.3f}s")


def build_plan(
    episode_id: str,
    manifest: dict,
    cues: list[dict],
    alignment_used: bool,
    author: dict,
    video_backend: str,
    audio_backend: str,
) -> dict:
    timeline = []
    beats = manifest["beats"]
    for index, beat in enumerate(beats):
        visual_end = float(beats[index + 1]["start"]) if index + 1 < len(beats) else float(manifest["duration"])
        timeline.append(
            {
                "segment_id": beat["id"],
                "start": round(float(beat["start"]), 6),
                "end": round(visual_end, 6),
                "source": f"unassigned_{beat['id'].lower()}.mp4",
                "source_start": 0.0,
                "source_end": 14.0,
                "purpose": beat["title"],
                "shot_type": "director_to_assign",
                "topic_relation": beat["title"],
                "planning_status": "requires_capability_first_director_cut",
            }
        )
    visual_format = author["visual_format"]
    return {
        "schema": "video_production_plan/v2",
        "episode_id": episode_id,
        "delivery": {
            "visual_requirement": visual_format["requirement"],
            "visual_style": visual_format["style"],
            "animation_mode": visual_format["animation_mode"],
            "author_profile": author["profile_id"],
            "primary_video_backend": video_backend,
            "content_accuracy_owner": "reviewed_narration_and_subtitles",
            "generated_visual_contract": "relevant_noncontradictory_watchable",
            "visual_manifest": "visual_delivery_manifest.json",
            "static_animatic_allowed_as_final": False,
            "minimum_generative_duration_ratio": visual_format.get(
                "minimum_generative_duration_ratio", 0.5
            ),
            "maximum_static_duration_ratio": visual_format.get(
                "maximum_static_duration_ratio", 0.25
            ),
        },
        "director_contract": {
            "default_shot_seconds": visual_format["default_shot_seconds"],
            "simple_single_action_max_seconds": visual_format["simple_single_action_max_seconds"],
            "generative_video_roles": ["presenter", "patient_moment", "caregiver_action", "care_path"],
            "reviewed_insert_role": "reviewed_visual_insert",
            "literal_narration_rendering_required": False,
            "precise_anatomy_required_from_generator": False,
            "generated_text_allowed": False,
        },
        "format": {"width": 608, "height": 352, "fps": 24, "orientation": "landscape"},
        "audio": {
            "backend": audio_backend,
            "source": "audio/local_voice/index-tts25-narration.wav",
            "duration_seconds": round(float(manifest["duration"]), 6),
            "master_timeline": True,
        },
        "subtitles": {
            "source": "audio/local_voice/narration.srt",
            "cue_count": len(cues),
            "max_lines": 2,
            "max_characters_per_line": MAX_LINE_CHARS,
            "visible_line_end_punctuation": "removed",
            "timing": "whisper_word_alignment" if alignment_used else "character_ratio_fallback",
            "layout_owner": "narration.srt",
        },
        "visual_timeline": timeline,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--production-root", type=Path)
    parser.add_argument("--episode", action="append", help="Episode directory name; repeat to select multiple")
    parser.add_argument("--series")
    parser.add_argument("--subtitle-terms", type=Path)
    parser.add_argument("--author-profile", type=Path)
    parser.add_argument("--video-backend")
    parser.add_argument("--audio-backend")
    args = parser.parse_args()
    args.production_root = production_root_for(args.series, args.production_root)
    terms_path = args.subtitle_terms
    if terms_path is None and args.series:
        candidate = series_paths(args.series)["content_root"] / "subtitle_terms.yaml"
        terms_path = candidate if candidate.is_file() else None
    if terms_path:
        terms = yaml.safe_load(terms_path.read_text(encoding="utf-8"))["protected_terms"]
        if not isinstance(terms, list) or not all(isinstance(term, str) for term in terms):
            raise ValueError("protected_terms must be a list of strings")
        PROTECTED_TERMS.update(terms)

    _, author = load_author_profile(profile_path=args.author_profile, series_id=args.series)
    _, backends = load_backend_profile()
    video_backend = args.video_backend or backends.get("policy", {}).get("default_video")
    if video_backend not in backends.get("video", {}):
        raise SystemExit(f"Unknown video backend: {video_backend!r}")
    audio_backend = args.audio_backend or backends.get("policy", {}).get("default_audio")
    if audio_backend not in backends.get("audio", {}):
        raise SystemExit(f"Unknown default audio backend: {audio_backend!r}")

    selected = set(args.episode or [])
    results = []
    for episode_dir in sorted(args.production_root.iterdir()):
        if not EPISODE_RE.match(episode_dir.name) or (selected and episode_dir.name not in selected):
            continue
        manifest_path = episode_dir / "audio/local_voice/narration_beats.json"
        if not manifest_path.is_file():
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        alignment_path = episode_dir / "audio/local_voice/whisper-alignment.json"
        alignment = json.loads(alignment_path.read_text(encoding="utf-8")) if alignment_path.is_file() else None
        cues = build_cues(manifest, alignment)
        validate_cues(cues, float(manifest["duration"]))
        srt_path = episode_dir / "audio/local_voice/narration.srt"
        write_srt(cues, srt_path)
        plan = build_plan(
            episode_dir.name,
            manifest,
            cues,
            alignment is not None,
            author,
            video_backend,
            audio_backend,
        )
        (episode_dir / "production_plan.yaml").write_text(
            yaml.safe_dump(plan, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        results.append(
            {
                "episode": episode_dir.name,
                "duration": manifest["duration"],
                "cues": len(cues),
                "timing": "whisper_word_alignment" if alignment else "character_ratio_fallback",
            }
        )
    print(json.dumps(results, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
