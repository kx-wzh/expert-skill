#!/usr/bin/env python3
"""
Schema helpers for the enterprise-expert-skill engine.

Manages metadata enrichment, artifact naming, and manifest generation.
Focused purely on expertise knowledge — no persona/character dimensions.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone

from expertise_presets import get_expertise_preset, normalize_expertise_type


SCHEMA_VERSION = "1"
PRIMARY_ARTIFACTS = (
    "SKILL.md",
    "expertise.md",
    "knowledge_graph.md",
    "heuristics.json",
    "manifest.json",
)

def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def build_identity_string(meta: dict) -> str:
    """Build a human-readable identity string from metadata."""
    preset = get_expertise_preset(meta.get("expertise_type", "troubleshooter"))
    profile = meta.get("profile", {})

    if isinstance(profile, str):
        parts = [profile.strip()]
    elif isinstance(profile, dict):
        parts = []
        for key in ("company", "level", "role", "domain"):
            value = profile.get(key, "")
            if value:
                parts.append(value)
    else:
        parts = []

    if not parts:
        return preset["identity_label"]

    identity = " · ".join(parts)
    expertise_label = preset["identity_label"]
    return f"{identity}（{expertise_label}）"


def build_artifact_names(meta: dict) -> dict:
    """Generate artifact names from the expertise preset."""
    preset = get_expertise_preset(meta.get("expertise_type", "troubleshooter"))
    slug = meta["slug"]
    prefix = preset["skill_name_prefix"]
    command_slug = slug.replace("_", "-")
    return {
        "combined_skill": "SKILL.md",
        "expertise_doc": "expertise.md",
        "knowledge_graph": "knowledge_graph.md",
        "heuristics": "heuristics.json",
        "manifest": "manifest.json",
        "latent_report": "latent_report.md",
        "interview_transcript": "interview_transcript.md",
        "combined_name": f"{prefix}_{slug}",
        "combined_command": f"expert-{command_slug}",
    }


def enrich_expert_meta(meta: dict, slug: str, expertise_type: str | None = None) -> dict:
    """Enrich metadata to the expert-skill schema."""
    result = deepcopy(meta)
    resolved_type = normalize_expertise_type(expertise_type or meta.get("expertise_type"))
    preset = get_expertise_preset(resolved_type)

    lifecycle = result.setdefault("lifecycle", {})
    generation = result.setdefault("generation", {})
    classification = result.setdefault("classification", {})

    result["schema_version"] = SCHEMA_VERSION
    result["slug"] = slug
    result["kind"] = result.get("kind") or "expert-skill"
    result["expertise_type"] = resolved_type
    result["preset"] = preset["prompt_bundle"]["preset"]

    display_name = result.get("display_name") or result.get("name") or slug
    result["display_name"] = display_name
    result["name"] = result.get("name") or display_name
    result["id"] = f"expert.{resolved_type}.{slug}"

    created_at = lifecycle.get("created_at") or now_iso()
    updated_at = lifecycle.get("updated_at") or created_at
    version = lifecycle.get("version") or "v1"

    classification.setdefault("expertise_type", resolved_type)
    classification.setdefault("knowledge_format", preset["knowledge_format"])
    classification.setdefault("execution_model", preset["execution_model"])
    classification.setdefault("language", "zh-CN")

    result["artifacts"] = {
        **build_artifact_names(result),
        **result.get("artifacts", {}),
    }

    generation.setdefault("engine", "expert-skill")
    generation.setdefault("expertise_type", resolved_type)
    generation.setdefault("preset", preset["prompt_bundle"]["preset"])
    generation.setdefault("prompt_bundle", preset["prompt_bundle"])
    generation.setdefault("created_from", result.get("knowledge_sources", []))

    lifecycle.setdefault("status", "active")
    lifecycle["created_at"] = created_at
    lifecycle["updated_at"] = updated_at
    lifecycle["version"] = version

    if not result.get("summary"):
        identity = build_identity_string(result)
        result["summary"] = f"{display_name}, {identity}"

    discovery = result.setdefault("discovery", {})
    discovery.setdefault("enabled", False)
    discovery.setdefault("status", "not_started")
    discovery.setdefault("interview_count", 0)
    discovery.setdefault("latent_variable_count", 0)
    discovery.setdefault("confidence_summary", {})

    return result


def build_manifest(meta: dict) -> dict:
    """Build a manifest for install and gallery flows."""
    artifacts = meta["artifacts"]
    manifest_artifacts = [
        artifacts["combined_skill"],
        artifacts["expertise_doc"],
        artifacts["knowledge_graph"],
        artifacts["heuristics"],
        "meta.json",
        artifacts["manifest"],
    ]
    capabilities = ["expertise"]
    discovery = meta.get("discovery", {})
    if discovery.get("enabled"):
        capabilities.append("discovery")
    if discovery.get("report_generated"):
        manifest_artifacts.append(artifacts.get("latent_report", "latent_report.md"))
    if discovery.get("transcript_generated"):
        manifest_artifacts.append(artifacts.get("interview_transcript", "interview_transcript.md"))
    return {
        "manifest_version": "1",
        "id": meta["id"],
        "kind": meta["kind"],
        "expertise_type": meta["expertise_type"],
        "preset": meta["preset"],
        "display_name": meta["display_name"],
        "entrypoints": {
            "default": artifacts["combined_skill"],
        },
        "artifacts": manifest_artifacts,
        "capabilities": capabilities,
        "engine": {
            "name": "expert-skill",
            "kind": "expert-skill",
            "expertise_type": meta["expertise_type"],
            "preset": meta["preset"],
            "prompt_bundle": meta.get("generation", {}).get("prompt_bundle", {}),
        },
        "install": {
            "compatible_runtimes": ["claude-code", "openclaw", "hermes", "codex"],
            "min_schema_version": SCHEMA_VERSION,
        },
    }
