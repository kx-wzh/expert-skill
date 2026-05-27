#!/usr/bin/env python3
"""
Triplet generator for the P4 discovery phase.

Reads latent_variables.json and expert_profile.json, assembles the
triplet_builder prompt, and optionally parses AI output to produce
triplet_groups.json and interview_script.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from discovery_schema import (
    format_prompt,
    parse_json_or_yaml,
    read_expert_blueprint,
    read_expert_profile,
    resolve_expertise_type,
    validate_triplet_group,
)

PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "discovery" / "triplet_builder.md"


# ---------------------------------------------------------------------------
# Input helpers
# ---------------------------------------------------------------------------

def read_latent_variables(base_dir: str, slug: str) -> list[dict]:
    path = Path(base_dir) / slug / "discovery" / "latent_variables.json"
    if not path.exists():
        raise FileNotFoundError(
            f"latent_variables.json not found at {path}\n"
            "Run latent_variable_builder.py --parse-output first (P3 must complete before P4)."
        )
    return json.loads(path.read_text(encoding="utf-8"))


def filter_target_variables(
    variables: list[dict],
    target_ids: list[str] | None = None,
) -> list[dict]:
    """Keep only high/medium testability candidates, then optionally filter by id."""
    filtered = [v for v in variables if v.get("testability") in ("high", "medium")]
    if target_ids:
        id_set = set(target_ids)
        filtered = [v for v in filtered if v.get("id") in id_set]
    return filtered


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def assemble_prompt(
    template: str,
    name: str,
    expertise_type: str,
    domain: str,
    target_variables_json: str,
    expert_profile_json: str,
    domain_context_json: str,
    known_decisions_json: str,
    expert_blueprint_json: str = "（未提供）",
    decision_scenarios_json: str = "[]",
) -> str:
    return format_prompt(
        template,
        name=name,
        expertise_type=expertise_type,
        domain=domain,
        target_variables_json=target_variables_json,
        expert_profile_json=expert_profile_json,
        domain_context_json=domain_context_json,
        known_decisions_json=known_decisions_json,
        expert_blueprint_json=expert_blueprint_json,
        decision_scenarios_json=decision_scenarios_json,
    )


# ---------------------------------------------------------------------------
# A/B overlap calculation
# ---------------------------------------------------------------------------

def _to_bigrams(text: str) -> set[str]:
    text = text.strip()
    if len(text) < 2:
        return set()
    return {text[i: i + 2] for i in range(len(text) - 1)}


def compute_ab_overlap(group: dict) -> float:
    """Compute character 2-gram Jaccard similarity between question_A and question_B texts."""
    text_a = group.get("question_A", {}).get("text", "")
    text_b = group.get("question_B", {}).get("text", "")
    bg_a = _to_bigrams(text_a)
    bg_b = _to_bigrams(text_b)
    if not bg_a and not bg_b:
        return 1.0
    if not bg_a or not bg_b:
        return 0.0
    intersection = len(bg_a & bg_b)
    union = len(bg_a | bg_b)
    return intersection / union if union > 0 else 0.0


# ---------------------------------------------------------------------------
# P4 quality gate
# ---------------------------------------------------------------------------

def check_p4_extra_quality_gate(groups: list[dict], target_ids: list[str]) -> list[str]:
    """P4 extra gate: coverage, hard overlap, quality_notes, conflict_added."""
    errors: list[str] = []
    covered = {g.get("target_variable") for g in groups}
    for tid in target_ids:
        if tid not in covered:
            errors.append(f"P4: 候选 {tid} 没有对应三联体组")
    for g in groups:
        if "ab_overlap_score" not in g:
            g["ab_overlap_score"] = compute_ab_overlap(g)
        if g.get("ab_overlap_score", 0) < 0.70:
            g["overlap_warning"] = True
        if g.get("overlap_warning"):
            score = g.get("ab_overlap_score", 0)
            errors.append(
                f"P4: 三联体组 {g.get('id')} A/B 重叠率不足 0.70"
                f"（得分 {score:.2f}）"
            )
        notes = g.get("quality_notes", {})
        for key in ("single_variable_control", "unpredictability", "decision_difference"):
            if not notes.get(key):
                errors.append(f"P4: 三联体组 {g.get('id')} 缺少 quality_notes.{key}")
        if not g.get("question_C", {}).get("conflict_added"):
            errors.append(f"P4: 三联体组 {g.get('id')} 缺少 question_C.conflict_added")
    return errors


# ---------------------------------------------------------------------------
# Interview script generation
# ---------------------------------------------------------------------------

def _role_for_group(group: dict, var_lookup: dict[str, dict]) -> str:
    """Assign an assembly role to a group based on its target variable."""
    var = var_lookup.get(group.get("target_variable", ""), {})
    if var.get("source_type") == "silent_topic":
        return "deep"
    if var.get("testability") == "medium":
        return "cooldown"
    return "core"


def _format_question(label: str, q: dict) -> str:
    lines = [f"### Question {label}", "", q.get("text", "（无内容）"), ""]
    probes = q.get("probes", {})
    if probes.get("primary"):
        lines += [f"**主追问**：{probes['primary']}", ""]
    followups = probes.get("followups", [])
    if followups:
        lines.append("**备用追问**：")
        for fu in followups:
            lines.append(f"- {fu}")
        lines.append("")
    reveals = q.get("expected_reveals", {})
    if reveals:
        lines.append("**预期揭示**：")
        if reveals.get("visible_rule"):
            lines.append(f"- 显性规则：{reveals['visible_rule']}")
        if reveals.get("latent_variable"):
            lines.append(f"- 隐性变量信号：{reveals['latent_variable']}")
        if reveals.get("priority_signal"):
            lines.append(f"- 优先级信号：{reveals['priority_signal']}")
        lines.append("")
    return "\n".join(lines)


def generate_interview_script(groups: list[dict], variables: list[dict]) -> str:
    """Generate a Markdown interview script ordered by assembly strategy."""
    var_lookup = {v.get("id", ""): v for v in variables}

    # Assign roles
    role_groups: dict[str, list[dict]] = {"opening": [], "core": [], "deep": [], "cooldown": []}
    for g in groups:
        role_groups[_role_for_group(g, var_lookup)].append(g)

    # Pick one opening: lowest priority high-testability, or first core
    core_and_deep = role_groups["core"] + role_groups["deep"]
    high_groups = [g for g in groups if var_lookup.get(g.get("target_variable", ""), {}).get("testability") == "high"]
    if high_groups:
        opening_group = min(high_groups, key=lambda g: var_lookup.get(g.get("target_variable", ""), {}).get("priority", 999))
        role_groups["opening"] = [opening_group]
        role_groups["core"] = [g for g in role_groups["core"] if g is not opening_group]
    elif core_and_deep:
        role_groups["opening"] = [core_and_deep[0]]
        role_groups["core"] = role_groups["core"][1:]

    # Sort core by target variable priority descending
    role_groups["core"].sort(
        key=lambda g: var_lookup.get(g.get("target_variable", ""), {}).get("priority", 0),
        reverse=True,
    )

    # Pick one cooldown from cooldown list, put rest back in core
    if len(role_groups["cooldown"]) > 1:
        role_groups["core"] += role_groups["cooldown"][:-1]
        role_groups["cooldown"] = role_groups["cooldown"][-1:]

    ordered: list[tuple[str, dict]] = []
    for g in role_groups["opening"]:
        ordered.append(("开场", g))
    for g in role_groups["core"]:
        ordered.append(("核心", g))
    for g in role_groups["deep"]:
        ordered.append(("深度", g))
    for g in role_groups["cooldown"]:
        ordered.append(("冷却", g))

    # Fallback: groups that didn't get a role
    assigned_ids = {id(g) for _, g in ordered}
    for g in groups:
        if id(g) not in assigned_ids:
            ordered.append(("核心", g))

    lines = [
        "# 访谈脚本草稿",
        "",
        "> ⚠️ 请不要提前告知专家题目编号或 AB 结构",
        "",
    ]
    for i, (role, g) in enumerate(ordered, 1):
        gid = g.get("id", f"tg_{i:03d}")
        label = g.get("target_variable_label", g.get("target_variable", ""))
        lines += [
            f"---",
            f"",
            f"## [{role}] {gid} — {label}",
            f"",
            f"**领域背景**：{g.get('domain_context', '')}",
            f"",
            f"**控制说明**：{g.get('control_notes', '')}",
            f"",
            f"> ⚠️ 请不要提前告知专家题目编号或 AB 结构",
            f"",
        ]
        for q_key, q_label in [("question_A", "A"), ("question_B", "B"), ("question_C", "C")]:
            q = g.get(q_key, {})
            if q:
                if q_key == "question_B" and q.get("variable_changed"):
                    lines.append(f"*（B 变化：{q['variable_changed']}）*")
                    lines.append("")
                if q_key == "question_C":
                    if q.get("variable_changed"):
                        lines.append(f"*（C 变化：{q['variable_changed']}）*")
                    if q.get("conflict_added"):
                        lines.append(f"*（冲突叠加：{q['conflict_added']}）*")
                    lines.append("")
                lines.append(_format_question(q_label, q))

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Meta update
# ---------------------------------------------------------------------------

def _update_meta_json(meta_path: Path, triplet_count: int) -> None:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    discovery = meta.setdefault("discovery", {})
    discovery["status"] = "triplets_ready"
    discovery["triplet_count"] = triplet_count
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P4 三联体生成工具：组装 prompt 并可选解析 AI 输出")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--base-dir", default="./skills/expert", dest="base_dir")
    parser.add_argument("--target-ids", nargs="+", metavar="ID", default=[], dest="target_ids",
                        help="只为指定候选 id 生成（默认：所有 high/medium 候选）")
    parser.add_argument("--parse-output", default="", metavar="FILE", dest="parse_output")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run")
    args = parser.parse_args(argv)

    if args.dry_run and args.parse_output:
        print("错误：--dry-run 与 --parse-output 不能同时使用", file=sys.stderr)
        return 1

    # Load template
    if not PROMPT_TEMPLATE_PATH.exists():
        print(f"错误：找不到 prompt 模板文件 {PROMPT_TEMPLATE_PATH}", file=sys.stderr)
        return 1
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    # Read inputs
    try:
        variables = read_latent_variables(args.base_dir, args.slug)
        profile = read_expert_profile(args.base_dir, args.slug)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    # Filter target variables
    target_vars = filter_target_variables(variables, args.target_ids or None)
    if not target_vars:
        print("警告：没有找到符合条件的目标候选（testability 为 high/medium）", file=sys.stderr)

    # Resolve identity info
    identity = profile.get("identity", {})
    name = identity.get("name", args.slug)
    domain = identity.get("domain", "")
    expertise_type = resolve_expertise_type(args.base_dir, args.slug)
    try:
        blueprint = read_expert_blueprint(args.base_dir, args.slug)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    expert_blueprint_json = (
        json.dumps({"expert_blueprint": blueprint}, ensure_ascii=False, indent=2)
        if blueprint is not None
        else "（未提供）"
    )
    decision_scenarios_json = json.dumps(
        (blueprint or {}).get("decision_scenarios", []),
        ensure_ascii=False,
        indent=2,
    )

    # Assemble prompt
    prompt = assemble_prompt(
        template=template,
        name=name,
        expertise_type=expertise_type,
        domain=domain,
        target_variables_json=json.dumps(target_vars, ensure_ascii=False, indent=2),
        expert_profile_json=json.dumps(profile, ensure_ascii=False, indent=2),
        domain_context_json=json.dumps(profile.get("domain_context", {}), ensure_ascii=False, indent=2),
        known_decisions_json=json.dumps(profile.get("known_decisions", []), ensure_ascii=False, indent=2),
        expert_blueprint_json=expert_blueprint_json,
        decision_scenarios_json=decision_scenarios_json,
    )

    if args.dry_run:
        print(prompt)
        return 0

    # Write prompt file
    discovery_dir = Path(args.base_dir) / args.slug / "discovery"
    discovery_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = discovery_dir / "triplet_builder_prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"[OK] prompt written: {prompt_file}")

    if not args.parse_output:
        return 0

    # Parse output
    output_path = Path(args.parse_output)
    if not output_path.exists():
        print(f"错误：输出文件不存在：{output_path}", file=sys.stderr)
        return 1

    groups = parse_json_or_yaml(output_path, "triplet_groups")
    if not isinstance(groups, list):
        print(f"错误：解析结果不是列表，得到 {type(groups)}", file=sys.stderr)
        return 1

    # Per-group schema validation
    schema_errors: list[str] = []
    for g in groups:
        errs = validate_triplet_group(g)
        for e in errs:
            schema_errors.append(f"  [{g.get('id', '?')}] {e}")
    if schema_errors:
        print("错误：三联体 schema 校验不通过，triplet_groups.json 不保存：", file=sys.stderr)
        for e in schema_errors:
            print(e, file=sys.stderr)
        return 1

    # Compute A/B overlap for each group. This is a hard gate because the design
    # depends on surface similarity for single-variable control.
    for g in groups:
        score = compute_ab_overlap(g)
        g["ab_overlap_score"] = score
        if score < 0.70:
            g["overlap_warning"] = True

    # P4 extra quality gate
    target_ids_for_gate = [v["id"] for v in target_vars]
    gate_errors = check_p4_extra_quality_gate(groups, target_ids_for_gate)
    if gate_errors:
        print("错误：P4 质量门不通过，triplet_groups.json 不保存：", file=sys.stderr)
        for e in gate_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # Save triplet_groups.json
    groups_path = discovery_dir / "triplet_groups.json"
    groups_path.write_text(json.dumps(groups, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[OK] triplet_groups.json saved ({len(groups)} groups): {groups_path}")

    # Generate interview script
    script = generate_interview_script(groups, variables)
    script_path = discovery_dir / "interview_script.md"
    script_path.write_text(script, encoding="utf-8")
    print(f"[OK] interview_script.md generated: {script_path}")

    # Update meta.json
    meta_path = Path(args.base_dir) / args.slug / "meta.json"
    if meta_path.exists():
        _update_meta_json(meta_path, len(groups))
        print(f"[OK] meta.json updated (discovery.status=triplets_ready, triplet_count={len(groups)})")
    else:
        print("Note: meta.json not found, discovery status not written")

    return 0


if __name__ == "__main__":
    sys.exit(main())
