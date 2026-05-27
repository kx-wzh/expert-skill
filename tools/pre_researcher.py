#!/usr/bin/env python3
"""
Pre-researcher tool for the P2 discovery phase.

Reads expert materials, assembles the pre_research prompt,
and optionally parses AI output to produce expert_profile.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from discovery_schema import build_expert_profile, format_prompt, parse_json_or_yaml, validate_expert_profile

PROMPT_TEMPLATE_PATH = Path(__file__).parent.parent / "prompts" / "discovery" / "pre_research.md"


def _extract_text_from_json(data: object) -> str:
    """Extract readable text from known collector JSON formats or fall back to dumps."""
    if isinstance(data, dict) and "messages" in data:
        # Feishu / DingTalk format
        parts: list[str] = []
        for msg in data["messages"]:
            if not isinstance(msg, dict):
                continue
            content = msg.get("content", "")
            if isinstance(content, str):
                parts.append(content)
            elif content is not None:
                parts.append(json.dumps(content, ensure_ascii=False))
        return "\n".join(parts)

    if isinstance(data, dict) and "emails" in data:
        # Email parser format
        parts = []
        for email in data["emails"]:
            if not isinstance(email, dict):
                continue
            subject = email.get("subject", "")
            body = email.get("body", "")
            subject_text = subject if isinstance(subject, str) else (
                json.dumps(subject, ensure_ascii=False) if subject is not None else ""
            )
            body_text = body if isinstance(body, str) else (
                json.dumps(body, ensure_ascii=False) if body is not None else ""
            )
            combined = "\n".join(filter(None, [subject_text, body_text]))
            if combined:
                parts.append(combined)
        return "\n\n".join(parts)

    # Unknown format: dump as text
    return json.dumps(data, ensure_ascii=False, indent=2)


def read_material_file(path: Path) -> str:
    """Read a material file, auto-extracting text from known JSON collector formats."""
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(text)
            return _extract_text_from_json(data)
        except json.JSONDecodeError:
            return text
    return text


def read_materials(paths: list[Path]) -> str:
    """Merge multiple material files into a single labelled text block."""
    parts: list[str] = []
    for p in paths:
        content = read_material_file(p)
        parts.append(f"--- {p.name} ---\n{content}")
    return "\n\n".join(parts)


def assemble_prompt(
    template: str,
    name: str,
    title: str,
    domain: str,
    years: str,
    expertise_type: str,
    materials_text: str,
    open_research: str = "",
    expertise_description: str = "",
    domain_background: str = "",
) -> str:
    return format_prompt(
        template,
        name=name,
        title=title or "（未填写）",
        domain=domain or "（未填写）",
        years=years or "（未填写）",
        expertise_type=expertise_type,
        materials=materials_text or "（未提供）",
        open_research=open_research or "（未提供）",
        expertise_description=expertise_description or "（未填写）",
        domain_background=domain_background or "（未填写）",
    )


def check_p2_quality_gate(profile: dict) -> list[str]:
    """P2 quality gate: must pass before saving expert_profile.json"""
    errors: list[str] = []
    if len(profile.get("visible_knowledge", [])) < 3:
        errors.append("P2: visible_knowledge 不足 3 条")
    if len(profile.get("known_decisions", [])) < 2:
        errors.append("P2: known_decisions 不足 2 条")
    if len(profile.get("suspected_gaps", [])) < 3:
        errors.append("P2: suspected_gaps 不足 3 条")
    ctx = profile.get("domain_context", {})
    for key in ("key_challenges", "common_pitfalls", "methodology_clashes"):
        if not ctx.get(key):
            errors.append(f"P2: domain_context.{key} 不能为空")
    return errors




def _update_meta_json(meta_path: Path) -> None:
    """Update the discovery block in an existing meta.json."""
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    discovery = meta.setdefault("discovery", {})
    discovery["enabled"] = True
    discovery["status"] = "profile_ready"
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2 前置研究工具：组装先验知识画像 prompt 并可选解析 AI 输出")
    parser.add_argument("--slug", required=True, help="专家 slug（确定存储路径）")
    parser.add_argument("--name", required=True, help="专家姓名")
    parser.add_argument("--expertise-type", required=True, dest="expertise_type", help="专长类型")
    parser.add_argument("--title", default="", help="职称")
    parser.add_argument("--domain", default="", help="领域")
    parser.add_argument("--years", default="", help="从业年数")
    parser.add_argument("--expertise-description", default="", dest="expertise_description", help="专长描述文本")
    parser.add_argument("--domain-background", default="", dest="domain_background", help="领域背景文本")
    parser.add_argument("--materials", nargs="+", metavar="FILE", default=[], help="材料文件列表（.txt/.md/.json）")
    parser.add_argument("--open-research", default="", metavar="FILE", dest="open_research", help="开放搜索补充文件")
    parser.add_argument("--base-dir", default="./skills/expert", dest="base_dir", help="专家技能存储根目录")
    parser.add_argument("--parse-output", default="", metavar="FILE", dest="parse_output", help="解析 AI 输出文件，通过质量门后保存 expert_profile.json")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run", help="仅打印组装好的 prompt，不写入任何文件")
    args = parser.parse_args(argv)

    if args.dry_run and args.parse_output:
        print("错误：--dry-run 与 --parse-output 不能同时使用", file=sys.stderr)
        return 1

    # Load prompt template
    if not PROMPT_TEMPLATE_PATH.exists():
        print(f"错误：找不到 prompt 模板文件 {PROMPT_TEMPLATE_PATH}", file=sys.stderr)
        return 1
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")

    # Read materials
    material_paths = [Path(f) for f in args.materials]
    for p in material_paths:
        if not p.exists():
            print(f"错误：材料文件不存在：{p}", file=sys.stderr)
            return 1
    materials_text = read_materials(material_paths) if material_paths else ""

    # Read optional open-research file
    open_research_text = ""
    if args.open_research:
        or_path = Path(args.open_research)
        if not or_path.exists():
            print(f"错误：开放搜索文件不存在：{or_path}", file=sys.stderr)
            return 1
        open_research_text = or_path.read_text(encoding="utf-8")

    # Assemble prompt
    prompt = assemble_prompt(
        template=template,
        name=args.name,
        title=args.title,
        domain=args.domain,
        years=args.years,
        expertise_type=args.expertise_type,
        materials_text=materials_text,
        open_research=open_research_text,
        expertise_description=args.expertise_description,
        domain_background=args.domain_background,
    )

    if args.dry_run:
        print(prompt)
        return 0

    # Determine discovery directory
    discovery_dir = Path(args.base_dir) / args.slug / "discovery"
    discovery_dir.mkdir(parents=True, exist_ok=True)

    # Write assembled prompt file
    prompt_file = discovery_dir / "pre_research_prompt.md"
    prompt_file.write_text(prompt, encoding="utf-8")
    print(f"[OK] prompt written: {prompt_file}")

    # Parse output if requested
    if args.parse_output:
        output_path = Path(args.parse_output)
        if not output_path.exists():
            print(f"错误：输出文件不存在：{output_path}", file=sys.stderr)
            return 1

        profile_data = parse_json_or_yaml(output_path, "expert_profile")

        # Schema validation
        schema_errors = validate_expert_profile(profile_data)
        if schema_errors:
            print("错误：schema 验证不通过，expert_profile.json 不保存：", file=sys.stderr)
            for e in schema_errors:
                print(f"  - {e}", file=sys.stderr)
            return 1

        # P2 quality gate
        gate_errors = check_p2_quality_gate(profile_data)
        if gate_errors:
            print("错误：P2 质量门不通过，expert_profile.json 不保存：", file=sys.stderr)
            for e in gate_errors:
                print(f"  - {e}", file=sys.stderr)
            return 1

        # Build canonical profile
        identity = profile_data.get("identity", {})
        canonical = build_expert_profile(
            name=identity.get("name", ""),
            title=identity.get("title", ""),
            domain=identity.get("domain", ""),
            years_in_field=identity.get("years_in_field"),
            visible_knowledge=profile_data.get("visible_knowledge"),
            known_decisions=profile_data.get("known_decisions"),
            domain_context=profile_data.get("domain_context"),
            suspected_gaps=profile_data.get("suspected_gaps"),
        )

        # Save expert_profile.json
        profile_path = discovery_dir / "expert_profile.json"
        profile_path.write_text(json.dumps(canonical, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] expert_profile.json saved: {profile_path}")

        # Update meta.json if it exists
        meta_path = Path(args.base_dir) / args.slug / "meta.json"
        if meta_path.exists():
            _update_meta_json(meta_path)
            print("[OK] meta.json updated (discovery.enabled=true, discovery.status=profile_ready)")
        else:
            print("Note: meta.json not found, discovery status not written")

    return 0


if __name__ == "__main__":
    sys.exit(main())
