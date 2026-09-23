#!/usr/bin/env python3
"""Resolve and validate workbench author and backend profiles."""

from __future__ import annotations

import argparse
import json
import os
from copy import deepcopy
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover - surfaced as an actionable validation error
    yaml = None


ROOT = Path(os.environ.get("MED_AUTOCAST_WORKSPACE_ROOT", Path(__file__).resolve().parents[1])).resolve()
WORKBENCH = ROOT / "workbench.yaml"


def load_yaml(path: Path) -> dict[str, Any]:
    if yaml is None:
        raise RuntimeError("PyYAML is required; install it with `python3 -m pip install pyyaml`.")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected a YAML mapping in {path}")
    return data


def workspace_path(value: str | Path, root: Path = ROOT) -> Path:
    path = Path(value)
    return path if path.is_absolute() else root / path


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    result = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = deepcopy(value)
    return result


def load_workbench(path: Path = WORKBENCH) -> dict[str, Any]:
    return load_yaml(path)


def series_paths(series_id: str, root: Path = ROOT) -> dict[str, Path]:
    workbench = load_workbench(root / "workbench.yaml")
    if series_id not in workbench.get("series", {}):
        raise ValueError(f"Unknown series {series_id!r}")
    series = workbench["series"][series_id]
    content = workspace_path(series.get("content_root", f"content/{series_id}"), root)
    production = workspace_path(series.get("production_root", f"productions/{series_id}"), root)
    return {
        "content_root": content,
        "production_root": production,
        "release_catalog": workspace_path(series.get("release_catalog", content / "06_release_catalog.yaml"), root),
        "publish_root": workspace_path(series.get("publish_root", f"publish/{series_id}"), root),
        "technical_qa": workspace_path(series.get("technical_qa", production / "series-final-qa.json"), root),
    }


def production_root_for(series_id: str | None, explicit: Path | None) -> Path:
    if series_id:
        registered = series_paths(series_id)["production_root"]
        if explicit and explicit.resolve() != registered.resolve():
            raise ValueError("--production-root conflicts with the selected series")
        return registered
    if explicit:
        return explicit.resolve()
    raise ValueError("Pass --series or --production-root")


def resolve_font(explicit: Path | None = None) -> Path:
    if explicit:
        font = explicit
    else:
        workbench = load_workbench()
        profile = load_yaml(active_profile_path("media_backends", workbench))
        value = os.environ.get("WORKBENCH_FONT") or profile.get("tools", {}).get("font")
        if not value:
            raise ValueError("Set WORKBENCH_FONT, deployment tools.font, or --font")
        font = workspace_path(os.path.expandvars(os.path.expanduser(value)))
    if not font.is_file():
        raise ValueError(f"Font not found: {font}")
    return font.resolve()


def active_profile_path(kind: str, workbench: dict[str, Any], root: Path = ROOT) -> Path:
    value = workbench.get("active_profiles", {}).get(kind)
    if not value:
        raise ValueError(f"workbench.yaml is missing active_profiles.{kind}")
    return workspace_path(value, root)


def load_author_profile(
    workbench: dict[str, Any] | None = None,
    profile_path: Path | None = None,
    series_id: str | None = None,
    root: Path = ROOT,
) -> tuple[Path, dict[str, Any]]:
    workbench = workbench or load_workbench(root / "workbench.yaml")
    series_profile = workbench.get("series", {}).get(series_id, {}).get("author_profile")
    if series_id and series_id not in workbench.get("series", {}):
        raise ValueError(f"Unknown series {series_id!r}")
    if profile_path:
        path = workspace_path(profile_path, root)
    elif series_profile:
        path = workspace_path(series_profile, root)
    else:
        path = active_profile_path("author", workbench, root)
    return path, load_yaml(path)


def load_backend_profile(
    workbench: dict[str, Any] | None = None,
    profile_path: Path | None = None,
    root: Path = ROOT,
) -> tuple[Path, dict[str, Any]]:
    workbench = workbench or load_workbench(root / "workbench.yaml")
    path = workspace_path(profile_path, root) if profile_path else active_profile_path("media_backends", workbench, root)
    profile = load_yaml(path)
    if profile.get("schema") != "medical_video_backend_profile/v1":
        raise ValueError(f"Unsupported backend profile schema in {path}")
    catalog_value = profile.get("catalog") or workbench.get("authorities", {}).get("backend_catalog")
    if not catalog_value:
        raise ValueError(f"Backend profile {path} does not reference a catalog")
    catalog_path = workspace_path(catalog_value, root)
    catalog = load_yaml(catalog_path)
    if catalog.get("schema") != "medical_video_backend_catalog/v1":
        raise ValueError(f"Unsupported backend catalog schema in {catalog_path}")
    definitions = catalog.get("definitions", {})
    effective: dict[str, Any] = {
        "schema": "medical_video_effective_backends/v1",
        "profile_id": profile.get("profile_id"),
        "profile_path": str(path),
        "catalog_path": str(catalog_path),
        "video": {},
        "audio": {},
        "policy": deepcopy(profile.get("policy", {})),
    }
    for media in ("video", "audio"):
        for instance_id, instance in profile.get(media, {}).items():
            definition_id = instance.get("definition")
            definition = definitions.get(media, {}).get(definition_id)
            if definition is None:
                raise ValueError(
                    f"Unknown {media} definition {definition_id!r} for instance {instance_id!r}"
                )
            merged = deep_merge(definition, {k: v for k, v in instance.items() if k != "definition"})
            merged["definition"] = definition_id
            effective[media][instance_id] = merged
    return path, effective


def validate(root: Path = ROOT, series_id: str | None = None) -> dict[str, Any]:
    workbench_path = root / "workbench.yaml"
    errors: list[str] = []
    assets: list[dict[str, Any]] = []
    try:
        workbench = load_workbench(workbench_path)
        author_path, author = load_author_profile(workbench=workbench, series_id=series_id, root=root)
        backend_path, backends = load_backend_profile(workbench=workbench, root=root)
    except Exception as exc:  # noqa: BLE001 - validator returns all available context
        return {"status": "failed", "errors": [f"{type(exc).__name__}: {exc}"]}

    registered_paths: dict[tuple[str, Path], str] = {}
    for registered_id in workbench.get("series", {}):
        for field, path in series_paths(registered_id, root).items():
            if field not in {"production_root", "technical_qa", "publish_root", "release_catalog"}:
                continue
            key = (field, path.resolve())
            if key in registered_paths:
                errors.append(f"series_path_shared:{field}:{registered_paths[key]}:{registered_id}")
            registered_paths[key] = registered_id

    if author.get("schema") != "medical_video_author_profile/v1":
        errors.append("unsupported_author_profile_schema")
    for field in ("profile_id", "display_name", "voice", "visual_identity", "visual_format"):
        if not author.get(field):
            errors.append(f"author_profile_missing:{field}")
    for field in ("requirement", "style", "animation_mode"):
        if not author.get("visual_format", {}).get(field):
            errors.append(f"author_visual_format_missing:{field}")
    if (
        author.get("visual_identity", {}).get("enabled")
        and not author.get("visual_identity", {}).get("character_reference")
    ):
        errors.append("author_visual_identity_reference_missing")
    for field_path, value in (
        ("voice.reference_audio", author.get("voice", {}).get("reference_audio")),
        ("visual_identity.character_reference", author.get("visual_identity", {}).get("character_reference")),
        ("brand.avatar_source", author.get("brand", {}).get("avatar_source")),
        ("audio_mix.background_music", author.get("audio_mix", {}).get("background_music")),
    ):
        if not value:
            continue
        path = workspace_path(value, root)
        exists = path.is_file()
        assets.append({"field": field_path, "path": str(path), "exists": exists})
        if not exists:
            errors.append(f"author_asset_missing:{field_path}")

    policy = backends.get("policy", {})
    for media in ("video", "audio"):
        default_id = policy.get(f"default_{media}")
        if not default_id:
            errors.append(f"backend_policy_missing:default_{media}")
        elif default_id not in backends.get(media, {}):
            errors.append(f"backend_default_unknown:{media}:{default_id}")
    preferred_audio_definition = author.get("voice", {}).get("preferred_backend_definition")
    available_audio_definitions = {
        spec.get("definition") for spec in backends.get("audio", {}).values()
    }
    if preferred_audio_definition and preferred_audio_definition not in available_audio_definitions:
        errors.append(
            f"author_preferred_audio_definition_unavailable:{preferred_audio_definition}"
        )

    return {
        "status": "passed" if not errors else "failed",
        "workbench": str(workbench_path),
        "author_profile": {
            "path": str(author_path),
            "profile_id": author.get("profile_id"),
            "display_name": author.get("display_name"),
            "series_id": series_id,
            "assets": assets,
        },
        "backend_profile": {
            "path": str(backend_path),
            "profile_id": backends.get("profile_id"),
            "default_video": policy.get("default_video"),
            "default_audio": policy.get("default_audio"),
            "video_instances": sorted(backends.get("video", {})),
            "audio_instances": sorted(backends.get("audio", {})),
        },
        "errors": errors,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("validate", "show"), nargs="?", default="validate")
    parser.add_argument("--series")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    if args.command == "validate":
        output = validate(series_id=args.series)
    else:
        workbench = load_workbench()
        author_path, author = load_author_profile(workbench=workbench, series_id=args.series)
        backend_path, backends = load_backend_profile(workbench=workbench)
        output = {
            "author_profile_path": str(author_path),
            "author_profile": author,
            "backend_profile_path": str(backend_path),
            "backend_profile": backends,
        }
    print(json.dumps(output, ensure_ascii=False, indent=2 if args.pretty else None))
    if output.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
