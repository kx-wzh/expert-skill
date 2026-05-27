#!/usr/bin/env python3
"""
Discovery schema helpers for the latent knowledge mining pipeline.

Defines data structures and validation for all discovery pipeline intermediates:
expert profiles, latent variable candidates, triplet question groups, and analysis outputs.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path


DISCOVERY_STATUSES = (
    "not_started",
    "profile_ready",
    "blueprint_ready",
    "variables_ready",
    "triplets_ready",
    "interview_in_progress",
    "interview_completed",
    "analysis_ready",
    "merged",
    "aborted",
)

_VALID_SOURCE_TYPES = {"comparison_gap", "domain_disagreement", "silent_topic", "rule_boundary"}
_VALID_TESTABILITY = {"high", "medium", "low"}


def build_expert_profile(
    name: str,
    title: str = "",
    domain: str = "",
    years_in_field: int | None = None,
    visible_knowledge: list[dict] | None = None,
    known_decisions: list[dict] | None = None,
    domain_context: dict | None = None,
    suspected_gaps: list[dict] | None = None,
) -> dict:
    """Build a prior knowledge profile for an expert.

    visible_knowledge items: {"rule": "...", "source": "..."}
    known_decisions items:   {"case": "...", "context": "...", "decision": "...", "source": "..."}
    suspected_gaps items:    {"gap": "...", "reason": "..."}
    """
    default_ctx: dict = {
        "key_challenges": [],
        "common_pitfalls": [],
        "methodology_clashes": [],
    }
    merged_ctx = {**default_ctx, **(domain_context or {})}
    return {
        "identity": {
            "name": name,
            "title": title,
            "domain": domain,
            "years_in_field": years_in_field,
        },
        "visible_knowledge": visible_knowledge or [],
        "known_decisions": known_decisions or [],
        "domain_context": merged_ctx,
        "suspected_gaps": suspected_gaps or [],
    }


def build_latent_variable(
    id: str,
    label: str,
    source_type: str,  # "comparison_gap" | "domain_disagreement" | "silent_topic" | "rule_boundary"
    evidence_from_profile: str,
    hypothesized_variable: dict,  # {"name": "...", "description": "...", "why_latent": "..."}
    testability: str,  # "high" | "medium" | "low"
    priority: int = 0,
) -> dict:
    """Build a latent variable candidate entry."""
    return {
        "id": id,
        "label": label,
        "source_type": source_type,
        "evidence_from_profile": evidence_from_profile,
        "hypothesized_variable": hypothesized_variable,
        "testability": testability,
        "priority": priority,
    }


def build_triplet_group(
    target_variable: str,
    domain_context: str,
    question_a: dict,
    question_b: dict,
    question_c: dict,
    control_notes: str = "",
) -> dict:
    """Build a triplet question group targeting a latent variable.

    Each question dict follows the structure:
      {
        "text": "...",
        "variable_changed": "...",   # question_b/c only
        "conflict_added": "...",     # question_c only
        "probes": {
          "primary": "...",
          "followups": ["..."],
          "signal_triggers": {
            "noticed": "...", "hesitated": "...", "boundary_invented": "...",
            "contradiction": "...", "pushback": "...",
          },
        },
        "expected_reveals": {
          "visible_rule": "...",
          "latent_variable": "...",
          "priority_signal": "...",
        },
      }
    """
    return {
        "target_variable": target_variable,
        "domain_context": domain_context,
        "question_A": question_a,
        "question_B": question_b,
        "question_C": question_c,
        "control_notes": control_notes,
    }


def build_triplet_analysis(
    triplet_id: str,
    baseline_rule: str,
    awareness_state: str,  # "explicit" | "semi_latent" | "deep_latent"
    priority_topology: dict,
    latent_findings: list[dict],
    confidence: str,  # "high" | "medium" | "low"
    invalidated_candidates: list[str] | None = None,
    evidence: dict | None = None,  # {"triplet_id", "layer", "expert_quote", "confidence_reason"}
) -> dict:
    """Build a triplet analysis result."""
    return {
        "triplet_id": triplet_id,
        "baseline_rule": baseline_rule,
        "awareness_state": awareness_state,
        "priority_topology": priority_topology,
        "latent_findings": latent_findings,
        "confidence": confidence,
        "invalidated_candidates": invalidated_candidates or [],
        "evidence": evidence or {},
    }


def build_expert_blueprint(
    identity_summary: dict,
    domain_summary: str,
    primary_workflows: list[dict],
    decision_scenarios: list[dict],
    knowledge_shape: dict,
    reasoning_framework: list[dict],
    tacit_knowledge_targets: list[dict],
    type_match: dict,
    generation_strategy: dict,
    evidence: list[str],
    scope_boundaries: list[dict] | None = None,
) -> dict:
    """Build an expert capability blueprint for blueprint-first creation."""
    return {
        "identity_summary": identity_summary,
        "domain_summary": domain_summary,
        "primary_workflows": primary_workflows,
        "decision_scenarios": decision_scenarios,
        "knowledge_shape": knowledge_shape,
        "reasoning_framework": reasoning_framework,
        "tacit_knowledge_targets": tacit_knowledge_targets,
        "type_match": type_match,
        "generation_strategy": generation_strategy,
        "scope_boundaries": scope_boundaries or [],
        "evidence": evidence,
    }


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------

def validate_expert_blueprint(blueprint: dict) -> list[str]:
    """Validate an expert blueprint dict. Returns a list of error strings."""
    errors: list[str] = []
    for field in (
        "identity_summary",
        "domain_summary",
        "primary_workflows",
        "decision_scenarios",
        "knowledge_shape",
        "reasoning_framework",
        "tacit_knowledge_targets",
        "type_match",
        "generation_strategy",
        "scope_boundaries",
        "evidence",
    ):
        if field not in blueprint:
            errors.append(f"{field} is required")

    if not isinstance(blueprint.get("identity_summary", {}), dict):
        errors.append("identity_summary must be a dict")
    if not blueprint.get("domain_summary"):
        errors.append("domain_summary is required")

    workflows = blueprint.get("primary_workflows", [])
    if not isinstance(workflows, list):
        errors.append("primary_workflows must be a list")
    elif len(workflows) < 2:
        errors.append(f"primary_workflows must contain at least 2 items, got {len(workflows)}")

    scenarios = blueprint.get("decision_scenarios", [])
    if not isinstance(scenarios, list):
        errors.append("decision_scenarios must be a list")
    elif len(scenarios) < 3:
        errors.append(f"decision_scenarios must contain at least 3 items, got {len(scenarios)}")

    targets = blueprint.get("tacit_knowledge_targets", [])
    if not isinstance(targets, list):
        errors.append("tacit_knowledge_targets must be a list")
    elif len(targets) < 5:
        errors.append(f"tacit_knowledge_targets must contain at least 5 items, got {len(targets)}")

    knowledge_shape = blueprint.get("knowledge_shape", {})
    if not isinstance(knowledge_shape, dict):
        errors.append("knowledge_shape must be a dict")
    elif not knowledge_shape.get("primary"):
        errors.append("knowledge_shape.primary is required")

    type_match = blueprint.get("type_match", {})
    if not isinstance(type_match, dict):
        errors.append("type_match must be a dict")
    else:
        if not type_match.get("recommended_type"):
            errors.append("type_match.recommended_type is required")
        confidence = type_match.get("confidence")
        if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
            errors.append("type_match.confidence must be a number")
        elif not (0 <= confidence <= 1):
            errors.append("type_match.confidence must be between 0 and 1")

    strategy = blueprint.get("generation_strategy", {})
    if not isinstance(strategy, dict):
        errors.append("generation_strategy must be a dict")
    else:
        if strategy.get("mode") not in ("preset", "generic"):
            errors.append("generation_strategy.mode must be 'preset' or 'generic'")
        sections = strategy.get("output_sections", [])
        if not isinstance(sections, list) or not sections:
            errors.append("generation_strategy.output_sections must be a non-empty list")
        if not strategy.get("heuristics_shape"):
            errors.append("generation_strategy.heuristics_shape is required")

    evidence = blueprint.get("evidence", [])
    if not isinstance(evidence, list) or not evidence:
        errors.append("evidence must be a non-empty list")
    return errors


def resolve_blueprint_type_match(
    blueprint: dict,
    available_types: list[str],
    confidence_threshold: float = 0.75,
) -> dict:
    """Resolve blueprint type matching into an effective type and generation mode."""
    type_match = blueprint.get("type_match", {})
    strategy = blueprint.get("generation_strategy", {})
    recommended = str(type_match.get("recommended_type", "custom") or "custom")
    confidence = type_match.get("confidence", 0)
    if not isinstance(confidence, (int, float)) or isinstance(confidence, bool):
        confidence = 0

    can_use_preset = (
        recommended in available_types
        and recommended != "custom"
        and confidence >= confidence_threshold
    )
    if can_use_preset:
        return {
            "effective_type": recommended,
            "generation_mode": "preset",
            "type_match_confidence": confidence,
            "type_match_overridden": False,
        }
    return {
        "effective_type": "custom",
        "generation_mode": "generic",
        "type_match_confidence": confidence,
        "type_match_overridden": recommended != "custom" or strategy.get("mode") != "generic",
    }


def validate_expert_profile(profile: dict) -> list[str]:
    """Validate an expert profile dict. Returns a list of error strings (empty = valid)."""
    errors: list[str] = []
    identity = profile.get("identity", {})
    if not isinstance(identity, dict) or not identity.get("name"):
        errors.append("identity.name is required")
    for field in ("visible_knowledge", "known_decisions", "suspected_gaps"):
        if field not in profile:
            errors.append(f"{field} is required")
        elif not isinstance(profile[field], list):
            errors.append(f"{field} must be a list")
    if "domain_context" not in profile:
        errors.append("domain_context is required")
    else:
        ctx = profile["domain_context"]
        if not isinstance(ctx, dict):
            errors.append("domain_context must be a dict")
        else:
            for key in ("key_challenges", "common_pitfalls", "methodology_clashes"):
                if key not in ctx:
                    errors.append(f"domain_context.{key} is required")
    return errors


def validate_latent_variable(var: dict) -> list[str]:
    """Validate a latent variable candidate. Returns a list of error strings."""
    errors: list[str] = []
    for field in ("id", "label", "source_type", "evidence_from_profile", "hypothesized_variable", "testability"):
        if not var.get(field):
            errors.append(f"{field} is required")
    source_type = var.get("source_type", "")
    if source_type and source_type not in _VALID_SOURCE_TYPES:
        errors.append(f"source_type must be one of {sorted(_VALID_SOURCE_TYPES)}, got '{source_type}'")
    testability = var.get("testability", "")
    if testability and testability not in _VALID_TESTABILITY:
        errors.append(f"testability must be one of {sorted(_VALID_TESTABILITY)}, got '{testability}'")
    hyp = var.get("hypothesized_variable")
    if isinstance(hyp, dict):
        for key in ("name", "description", "why_latent"):
            if not hyp.get(key):
                errors.append(f"hypothesized_variable.{key} is required")
    elif hyp is not None:
        errors.append("hypothesized_variable must be a dict")
    return errors


def _validate_probes(probes: dict, question_label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(probes, dict):
        errors.append(f"{question_label}.probes must be a dict")
        return errors
    if not probes.get("primary"):
        errors.append(f"{question_label}.probes.primary is required")
    if "followups" not in probes:
        errors.append(f"{question_label}.probes.followups is required")
    triggers = probes.get("signal_triggers", {})
    if not isinstance(triggers, dict):
        errors.append(f"{question_label}.probes.signal_triggers must be a dict")
    return errors


def _validate_expected_reveals(reveals: dict, question_label: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(reveals, dict):
        errors.append(f"{question_label}.expected_reveals must be a dict")
        return errors
    for key in ("visible_rule", "latent_variable", "priority_signal"):
        if key not in reveals:
            errors.append(f"{question_label}.expected_reveals.{key} is required")
    return errors


def validate_triplet_group(triplet: dict) -> list[str]:
    """Validate a triplet group. Returns a list of error strings."""
    errors: list[str] = []
    if not triplet.get("target_variable"):
        errors.append("target_variable is required")
    if not triplet.get("domain_context"):
        errors.append("domain_context is required")
    for q_key in ("question_A", "question_B", "question_C"):
        q = triplet.get(q_key, {})
        if not isinstance(q, dict):
            errors.append(f"{q_key} must be a dict")
            continue
        if not q.get("text"):
            errors.append(f"{q_key}.text is required")
        if "probes" not in q:
            errors.append(f"{q_key}.probes is required")
        else:
            errors.extend(_validate_probes(q["probes"], q_key))
        if "expected_reveals" not in q:
            errors.append(f"{q_key}.expected_reveals is required")
        else:
            errors.extend(_validate_expected_reveals(q["expected_reveals"], q_key))
    return errors


def validate_latent_variables_pool(variables: list[dict]) -> list[str]:
    """Validate the full pool of latent variable candidates.

    Checks: count 5-12, at least 3 with high or medium testability.
    """
    errors: list[str] = []
    count = len(variables)
    if count < 5:
        errors.append(f"Pool must have at least 5 variables, got {count}")
    elif count > 12:
        errors.append(f"Pool must have at most 12 variables, got {count}")
    high_medium = sum(1 for v in variables if v.get("testability") in ("high", "medium"))
    if high_medium < 3:
        errors.append(
            f"At least 3 variables must have high or medium testability, got {high_medium}"
        )
    return errors


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def get_discovery_dir(base_dir: str, slug: str) -> Path:
    """Return the discovery intermediates directory: {base_dir}/{slug}/discovery/"""
    return Path(base_dir) / slug / "discovery"


def get_discovery_file_path(base_dir: str, slug: str, filename: str) -> Path:
    """Return the full path to a specific discovery intermediate file."""
    return get_discovery_dir(base_dir, slug) / filename


_YAML_IMPORT_ERROR_MSG = (
    "错误：输入文件不是有效 JSON，且 PyYAML 未安装。\n"
    "请安装 PyYAML（pip install pyyaml）以支持 YAML 输入，"
    "或将 AI 输出保存为 JSON 格式后重试。"
)


def format_prompt(template: str, **kwargs: str) -> str:
    """Replace {key} placeholders in template with corresponding kwargs values."""
    for key, value in kwargs.items():
        template = template.replace(f"{{{key}}}", value)
    return template


def parse_json_or_yaml(path: Path, root_key: str | None = None):
    """Read path as JSON or YAML; if root_key given and result is a dict, unwrap that key."""
    text = path.read_text(encoding="utf-8")

    def _unwrap(data):
        if root_key is not None and isinstance(data, dict):
            return data.get(root_key, data)
        return data

    try:
        return _unwrap(json.loads(text))
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # type: ignore
        return _unwrap(yaml.safe_load(text))
    except ImportError:
        print(_YAML_IMPORT_ERROR_MSG, file=sys.stderr)
        sys.exit(1)
    except Exception as exc:
        print(f"错误：无法解析输出文件（{exc}）", file=sys.stderr)
        sys.exit(1)


def read_expert_profile(base_dir: str, slug: str) -> dict:
    path = get_discovery_file_path(base_dir, slug, "expert_profile.json")
    if not path.exists():
        raise FileNotFoundError(
            f"expert_profile.json not found at {path}\n"
            "Run pre_researcher.py --parse-output first (P2 must complete before P3)."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def read_expert_blueprint(base_dir: str, slug: str) -> dict | None:
    path = get_discovery_file_path(base_dir, slug, "expert_blueprint.json")
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"expert_blueprint.json is invalid JSON at {path}: {exc}") from exc


def resolve_expertise_type(base_dir: str, slug: str, explicit_type: str = "") -> str:
    if explicit_type:
        return explicit_type
    meta_path = Path(base_dir) / slug / "meta.json"
    if meta_path.exists():
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            if meta.get("expertise_type"):
                return meta["expertise_type"]
        except (json.JSONDecodeError, OSError):
            pass
    return "troubleshooter"
