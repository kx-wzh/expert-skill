#!/usr/bin/env python3
"""
Latent variable builder for the P3 discovery phase.

Reads expert_profile.json, assembles the latent_variable prompt,
and optionally parses AI output to produce latent_variables.json.
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
    validate_latent_variable,
    validate_latent_variables_pool,
)

PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "discovery" / "latent_variable.md"

_TESTABILITY_RANK = {"high": 2, "medium": 1, "low": 0}


def assemble_prompt(
    template: str,
    name: str,
    expertise_type: str,
    expert_profile_json: str,
    expert_blueprint_json: str = "（未提供）",
) -> str:
    return format_prompt(
        template,
        name=name,
        expertise_type=expertise_type,
        expert_profile_json=expert_profile_json,
        expert_blueprint_json=expert_blueprint_json,
    )


def check_p3_extra_quality_gate(variables: list[dict]) -> list[str]:
    """P3 extra quality gate (business rules beyond schema validation).

    Checks:
    - At least one candidate has source_type == 'silent_topic'
    - Every candidate's priority is an integer in [1, 10]
    """
    errors: list[str] = []
    has_silent_topic = any(v.get("source_type") == "silent_topic" for v in variables)
    if not has_silent_topic:
        errors.append("P3: 至少需要 1 个 source_type 为 silent_topic 的候选（来自 suspected_gaps）")
    for v in variables:
        p = v.get("priority")
        vid = v.get("id", "?")
        if not isinstance(p, int) or isinstance(p, bool):
            errors.append(f"P3: 候选 {vid} 的 priority 必须是整数，当前值：{p!r}")
        elif not (1 <= p <= 10):
            errors.append(f"P3: 候选 {vid} 的 priority 必须在 1-10 范围内，当前值：{p}")
    return errors


def sort_candidates(variables: list[dict]) -> list[dict]:
    """Sort candidates by priority descending, then testability descending."""
    return sorted(
        variables,
        key=lambda v: (v.get("priority", 0), _TESTABILITY_RANK.get(v.get("testability", ""), 0)),
        reverse=True,
    )




def _update_meta_json(meta_path: Path, variable_count: int) -> None:
    """Update discovery fields in an existing meta.json."""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    discovery = meta.setdefault("discovery", {})
    current_status = discovery.get("status", "")
    if current_status and current_status != "profile_ready":
        print(
            f"警告：meta.json discovery.status 为 '{current_status}'，期望 'profile_ready'；"
            "继续更新但请检查流程是否正确。",
            file=sys.stderr,
        )
    discovery["status"] = "variables_ready"
    discovery["latent_variable_count"] = variable_count
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P3 隐性变量构建工具：组装 prompt 并可选解析 AI 输出")
    parser.add_argument("--slug", required=True, help="专家 slug")
    parser.add_argument("--base-dir", default="./skills/expert", dest="base_dir", help="专家技能存储根目录")
    parser.add_argument("--expertise-type", default="", dest="expertise_type", help="专长类型（可选，优先级高于 meta.json）")
    parser.add_argument("--parse-output", default="", metavar="FILE", dest="parse_output", help="解析 AI 输出文件，通过质量门后保存 latent_variables.json")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="仅打印 prompt，不写入任何文件")
    args = parser.parse_args(argv)

    if args.dry_run and args.parse_output:
        print("错误：--dry-run 与 --parse-output 不能同时使用", file=sys.stderr)
        return 1

    # Load prompt template
    if not PROMPT_TEMPLATE_PATH.exists():
        print(f"错误：找不到 prompt 模板文件 {PROMPT_TEMPLATE_PATH}", file=sys.stderr)
        return 1
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    # Read expert_profile.json
    try:
        profile = read_expert_profile(args.base_dir, args.slug)
    except FileNotFoundError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    # Resolve expertise_type
    expertise_type = resolve_expertise_type(args.base_dir, args.slug, args.expertise_type)
    if not args.expertise_type and expertise_type == "troubleshooter":
        print(
            "警告：未传 --expertise-type 且找不到 meta.json，默认使用 troubleshooter",
            file=sys.stderr,
        )

    # Assemble prompt
    name = profile.get("identity", {}).get("name", args.slug)
    profile_json_str = json.dumps(profile, ensure_ascii=False, indent=2)
    try:
        blueprint = read_expert_blueprint(args.base_dir, args.slug)
    except ValueError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    blueprint_json_str = (
        json.dumps({"expert_blueprint": blueprint}, ensure_ascii=False, indent=2)
        if blueprint is not None
        else "（未提供）"
    )
    prompt = assemble_prompt(
        template=template,
        name=name,
        expertise_type=expertise_type,
        expert_profile_json=profile_json_str,
        expert_blueprint_json=blueprint_json_str,
    )

    if args.dry_run:
        print(prompt)
        return 0

    # Write prompt file
    discovery_dir = Path(args.base_dir) / args.slug / "discovery"
    discovery_dir.mkdir(parents=True, exist_ok=True)
    prompt_file = discovery_dir / "latent_variable_prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"[OK] prompt written: {prompt_file}")

    # Parse output if requested
    if args.parse_output:
        output_path = Path(args.parse_output)
        if not output_path.exists():
            print(f"错误：输出文件不存在：{output_path}", file=sys.stderr)
            return 1

        variables = parse_json_or_yaml(output_path, "latent_variables")
        if not isinstance(variables, list):
            print(f"错误：解析结果不是列表，得到 {type(variables)}", file=sys.stderr)
            return 1

        # Per-candidate schema validation
        schema_errors: list[str] = []
        for var in variables:
            errs = validate_latent_variable(var)
            for e in errs:
                schema_errors.append(f"  [{var.get('id', '?')}] {e}")
        if schema_errors:
            print("错误：候选 schema 校验不通过，latent_variables.json 不保存：", file=sys.stderr)
            for e in schema_errors:
                print(e, file=sys.stderr)
            return 1

        # Pool quality gate (count + testability)
        pool_errors = validate_latent_variables_pool(variables)
        if pool_errors:
            print("错误：P3 候选池质量门不通过，latent_variables.json 不保存：", file=sys.stderr)
            for e in pool_errors:
                print(f"  - {e}", file=sys.stderr)
            return 1

        # P3 extra quality gate (silent_topic + priority range)
        extra_errors = check_p3_extra_quality_gate(variables)
        if extra_errors:
            print("错误：P3 专属质量门不通过，latent_variables.json 不保存：", file=sys.stderr)
            for e in extra_errors:
                print(f"  - {e}", file=sys.stderr)
            return 1

        # Sort and save
        sorted_vars = sort_candidates(variables)
        out_path = discovery_dir / "latent_variables.json"
        out_path.write_text(json.dumps(sorted_vars, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] latent_variables.json saved ({len(sorted_vars)} candidates): {out_path}")

        # Update meta.json if exists
        meta_path = Path(args.base_dir) / args.slug / "meta.json"
        if meta_path.exists():
            _update_meta_json(meta_path, len(sorted_vars))
            print(f"[OK] meta.json updated (discovery.status=variables_ready, latent_variable_count={len(sorted_vars)})")
        else:
            print("Note: meta.json not found, discovery status not written")

    return 0


if __name__ == "__main__":
    sys.exit(main())
