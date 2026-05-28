#!/usr/bin/env python3
"""
Interview analyzer tool for the P6 discovery phase.

Reads interview_transcript.json and triplet_groups.json, assembles an analysis
prompt for AI, and parses AI output into interview_analysis.json + latent_report.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

PROMPT_TEMPLATE_PATH = (
    Path(__file__).parent.parent / "prompts" / "discovery" / "interview_analyzer.md"
)

_VALID_AWARENESS_STATES = {"explicit", "semi_latent", "deep_latent"}
_VALID_CONFIDENCE = {"high", "medium", "low"}
_CONFIDENCE_ORDER = {"high": 0, "medium": 1, "low": 2}


# ---------------------------------------------------------------------------
# Local schema validator (does not use discovery_schema.validate_triplet_analysis)
# ---------------------------------------------------------------------------

def check_triplet_analysis_schema(analysis: dict) -> list[str]:
    """Validate a single triplet analysis result. Returns error strings (empty = valid).

    Implemented locally — does not depend on discovery_schema.py.
    """
    errors: list[str] = []
    for field in (
        "triplet_id", "baseline_rule", "awareness_state",
        "priority_topology", "latent_findings", "confidence",
    ):
        if field not in analysis:
            errors.append(f"triplet analysis: missing field '{field}'")
    state = analysis.get("awareness_state", "")
    if state and state not in _VALID_AWARENESS_STATES:
        errors.append(f"triplet analysis: awareness_state invalid value '{state}'")
    conf = analysis.get("confidence", "")
    if conf and conf not in _VALID_CONFIDENCE:
        errors.append(f"triplet analysis: confidence invalid value '{conf}'")
    findings = analysis.get("latent_findings", [])
    if not isinstance(findings, list):
        errors.append("triplet analysis: latent_findings must be a list")
    else:
        for i, f in enumerate(findings):
            if not f.get("confidence"):
                errors.append(f"triplet analysis: finding[{i}] missing confidence")
            ev = f.get("evidence", {})
            if not isinstance(ev, dict) or not ev.get("expert_quote"):
                errors.append(f"triplet analysis: finding[{i}] missing evidence.expert_quote")
    return errors


# ---------------------------------------------------------------------------
# P6 quality gate
# ---------------------------------------------------------------------------

def _is_camera_only_evidence(finding: dict) -> bool:
    evidence = finding.get("evidence", {})
    quote = str(evidence.get("expert_quote", "")).strip().lower()
    reason = str(evidence.get("confidence_reason", "")).strip().lower()
    if not quote:
        return False
    quote_markers = (
        "camera_suggestion",
        "camera_suggestions",
        "摄像头建议",
        "only camera",
        "camera-only",
        "仅凭摄像头",
    )
    reason_only_markers = (
        "only camera",
        "camera-only",
        "仅凭摄像头",
    )
    return any(marker in quote for marker in quote_markers) or any(
        marker in reason for marker in reason_only_markers
    )


def check_p6_quality_gate(
    result: dict,
    transcript: list[dict],
    triplet_groups: list[dict] | None = None,
) -> tuple[list[str], list[str]]:
    """P6 gate: result completeness, per-triplet evidence, boundary map coverage.

    Returns: (errors, warnings)
    """
    errors: list[str] = []
    warnings: list[str] = []

    analyses = result.get("triplet_analyses", [])
    if not analyses:
        errors.append("P6: triplet_analyses 不能为空")

    expected_triplet_ids: set[str] = {
        r.get("triplet_id", "")
        for r in transcript
        if r.get("triplet_id")
    }
    if triplet_groups is not None:
        expected_triplet_ids.update(
            g.get("id", "")
            for g in triplet_groups
            if g.get("id")
        )
    analysis_triplet_ids = [
        a.get("triplet_id", "")
        for a in analyses
        if a.get("triplet_id")
    ]
    seen: set[str] = set()
    duplicate_ids: set[str] = set()
    for tid in analysis_triplet_ids:
        if tid in seen:
            duplicate_ids.add(tid)
        seen.add(tid)
    for tid in sorted(expected_triplet_ids - set(analysis_triplet_ids)):
        errors.append(f"P6: 三联体 {tid} 缺少分析结果")
    for tid in sorted(duplicate_ids):
        errors.append(f"P6: 三联体 {tid} 出现重复分析结果")

    cross = result.get("cross_analysis", {})
    sections = result.get("report_sections", {})

    if not isinstance(cross, dict):
        errors.append("P6: cross_analysis 必须是对象")
        cross = {}
    if not isinstance(sections, dict):
        errors.append("P6: report_sections 必须是对象")
        sections = {}

    for key in ("confirmed_variables", "inconsistent_variables", "priority_topology", "boundary_map"):
        if key not in cross:
            errors.append(f"P6: cross_analysis.{key} 缺失")
    for key in ("discovered_variables", "priority_topology", "boundary_map", "suspected_bias", "open_questions"):
        if key not in sections:
            errors.append(f"P6: report_sections.{key} 缺失")

    for a in analyses:
        tid = a.get("triplet_id", "?")
        for field in ("baseline_rule", "awareness_state", "priority_topology", "confidence"):
            if not a.get(field):
                errors.append(f"P6: 三联体 {tid} 缺少 {field}")
        for f in a.get("latent_findings", []):
            if not f.get("confidence"):
                errors.append(f"P6: 三联体 {tid} 的 finding 缺少 confidence")
            ev = f.get("evidence", {})
            if not ev.get("expert_quote"):
                errors.append(f"P6: 三联体 {tid} 的 finding 缺少 evidence.expert_quote")
            if _is_camera_only_evidence(f):
                errors.append(f"P6: 三联体 {tid} 的 finding 包含 camera-only evidence")
        state = a.get("awareness_state", "")
        if state and state not in ("explicit", "semi_latent", "deep_latent"):
            errors.append(f"P6: 三联体 {tid} 的 awareness_state 非法值 '{state}'")
        conf = a.get("confidence", "")
        if conf and conf not in ("high", "medium", "low"):
            errors.append(f"P6: 三联体 {tid} 的 confidence 非法值 '{conf}'")

    bi_triplets = {
        r.get("triplet_id")
        for r in transcript
        if "boundary_invented" in r.get("signals_observed", [])
    }
    boundary_entries = cross.get("boundary_map", [])
    covered = {
        item.get("triplet_id")
        for item in boundary_entries
        if isinstance(item, dict)
    }
    missing = sorted(tid for tid in bi_triplets if tid and tid not in covered)
    if missing:
        errors.append(
            "P6: 以下包含 boundary_invented 信号的三联体未进入 cross_analysis.boundary_map: "
            + ", ".join(missing)
        )

    return errors, warnings


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------

def generate_latent_report_md(result: dict) -> str:
    """Render the P6 analysis result as a structured Markdown report."""
    cross = result.get("cross_analysis", {}) or {}
    sections = result.get("report_sections", {}) or {}
    lines: list[str] = ["# 隐性知识分析报告", ""]

    # 1. Discovered variables — sorted high → medium → low
    lines += ["## 发现的隐性变量", ""]
    all_findings: list[dict] = []
    for a in result.get("triplet_analyses", []):
        for f in a.get("latent_findings", []):
            all_findings.append(f)
    all_findings.sort(key=lambda f: _CONFIDENCE_ORDER.get(f.get("confidence", "low"), 2))

    if all_findings:
        for f in all_findings:
            conf = f.get("confidence", "")
            ftype = f.get("type", "")
            content = f.get("content", "")
            lines.append(f"- **[{conf}]** [{ftype}] {content}")
            ev = f.get("evidence", {})
            tid = ev.get("triplet_id", "")
            layer = ev.get("layer", "")
            quote = ev.get("expert_quote", "")
            if tid or quote:
                lines.append(f"  > 来源：[{tid} {layer}] 「{quote}」")
            lines.append("")
    else:
        lines += ["（无发现）", ""]

    # 2. Priority topology
    lines += ["## 隐性优先级拓扑", ""]
    topo = sections.get("priority_topology", [])
    if topo:
        for item in topo:
            if isinstance(item, str):
                lines.append(f"- {item}")
            else:
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    else:
        lines.append("（待分析）")
    lines.append("")

    # 3. Global boundary map — merge cross_analysis and report_sections
    lines += ["## 全局边界地图", ""]
    bmap: list = list(cross.get("boundary_map", []))
    seen = set()
    for item in sections.get("boundary_map", []):
        key = json.dumps(item, ensure_ascii=False, sort_keys=True)
        if key not in seen:
            seen.add(key)
            bmap.append(item)
    if bmap:
        for item in bmap:
            if isinstance(item, str):
                lines.append(f"- {item}")
            else:
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    else:
        lines.append("（无边界发明信号记录）")
    lines.append("")

    # 4. Suspected bias
    lines += ["## 疑似误判区", ""]
    bias = sections.get("suspected_bias", [])
    if bias:
        for item in bias:
            if isinstance(item, str):
                lines.append(f"- {item}")
            else:
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    else:
        lines.append("（无）")
    lines.append("")

    # 5. Open questions
    lines += ["## 未解问题", ""]
    oq = sections.get("open_questions", [])
    if oq:
        for item in oq:
            if isinstance(item, str):
                lines.append(f"- {item}")
            else:
                lines.append(f"- {json.dumps(item, ensure_ascii=False)}")
    else:
        lines.append("（无）")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Prompt assembly
# ---------------------------------------------------------------------------

def assemble_prompt(
    template: str,
    name: str,
    expertise_type: str,
    triplet_groups_json: str,
    interview_transcript_json: str,
) -> str:
    """Replace template placeholders with actual values."""
    return (
        template
        .replace("{name}", name)
        .replace("{expertise_type}", expertise_type)
        .replace("{triplet_groups_json}", triplet_groups_json)
        .replace("{interview_transcript_json}", interview_transcript_json)
    )


# ---------------------------------------------------------------------------
# Output file parser
# ---------------------------------------------------------------------------

def _parse_output_file(output_path: Path) -> dict:
    text = output_path.read_text(encoding="utf-8")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    try:
        import yaml  # noqa: PLC0415
        data = yaml.safe_load(text)
        if isinstance(data, dict):
            return data
    except ImportError:
        pass
    raise ValueError(f"无法解析文件 {output_path}：不是有效的 JSON 或 YAML")


# ---------------------------------------------------------------------------
# Meta update
# ---------------------------------------------------------------------------

def _update_meta_json(meta_path: Path, latent_finding_count: int) -> None:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    d = meta.setdefault("discovery", {})
    if d.get("status") != "analysis_ready":
        d["status"] = "analysis_ready"
    d["analysis_completed"] = True
    d["latent_finding_count"] = latent_finding_count
    d["report_generated"] = True
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P6 访谈分析工具")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--base-dir", default="./skills/expert", dest="base_dir")
    parser.add_argument("--parse-output", default="", dest="parse_output",
                        help="解析 AI 分析输出文件路径")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="打印 prompt 但不写文件")
    args = parser.parse_args(argv)

    if args.dry_run and args.parse_output:
        print("错误：--dry-run 与 --parse-output 不能同时使用", file=sys.stderr)
        return 1

    discovery_dir = Path(args.base_dir) / args.slug / "discovery"

    # Read required input files
    transcript_path = discovery_dir / "interview_transcript.json"
    if not transcript_path.exists():
        print(f"错误：找不到 interview_transcript.json：{transcript_path}", file=sys.stderr)
        return 1
    transcript: list[dict] = json.loads(transcript_path.read_text(encoding="utf-8"))

    groups_path = discovery_dir / "triplet_groups.json"
    if not groups_path.exists():
        print(f"错误：找不到 triplet_groups.json：{groups_path}", file=sys.stderr)
        return 1
    groups: list[dict] = json.loads(groups_path.read_text(encoding="utf-8"))

    # Read expert identity from expert_profile.json
    name = args.slug
    expertise_type = ""
    profile_path = discovery_dir / "expert_profile.json"
    if profile_path.exists():
        try:
            profile = json.loads(profile_path.read_text(encoding="utf-8"))
            identity = profile.get("identity", {})
            name = identity.get("name", args.slug) or args.slug
            expertise_type = identity.get("title", "") or ""
        except (json.JSONDecodeError, OSError):
            pass

    # Assemble prompt
    template = PROMPT_TEMPLATE_PATH.read_text(encoding="utf-8")
    prompt = assemble_prompt(
        template, name, expertise_type,
        json.dumps(groups, ensure_ascii=False, indent=2),
        json.dumps(transcript, ensure_ascii=False, indent=2),
    )

    if args.dry_run:
        print(prompt)
        return 0

    # Save prompt
    discovery_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = discovery_dir / "interview_analyzer_prompt.md"
    prompt_path.write_text(prompt, encoding="utf-8")
    print(f"✓ 分析 prompt 已保存：{prompt_path}")

    if not args.parse_output:
        return 0

    # Parse AI output
    output_path = Path(args.parse_output)
    if not output_path.exists():
        print(f"错误：找不到输出文件：{output_path}", file=sys.stderr)
        return 1

    try:
        result = _parse_output_file(output_path)
    except ValueError as e:
        print(f"错误：{e}", file=sys.stderr)
        return 1

    # Per-triplet schema validation
    schema_errors: list[str] = []
    for a in result.get("triplet_analyses", []):
        schema_errors.extend(check_triplet_analysis_schema(a))
    if schema_errors:
        print("Schema 校验失败：", file=sys.stderr)
        for e in schema_errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    # P6 quality gate
    errors, warnings = check_p6_quality_gate(result, transcript, groups)
    for w in warnings:
        print(f"⚠️  {w}")
    if errors:
        print("\nP6 质量门未通过：")
        for e in errors:
            print(f"  - {e}")
        return 1

    # Count findings
    latent_finding_count = sum(
        len(a.get("latent_findings", []))
        for a in result.get("triplet_analyses", [])
    )

    # Save full analysis
    analysis_path = discovery_dir / "interview_analysis.json"
    analysis_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    # Save flattened latent_findings.json for P7
    all_findings = [
        f
        for a in result.get("triplet_analyses", [])
        for f in a.get("latent_findings", [])
    ]
    findings_path = discovery_dir / "latent_findings.json"
    findings_path.write_text(json.dumps(all_findings, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate Markdown report
    report_md = generate_latent_report_md(result)
    report_path = discovery_dir / "latent_report.md"
    report_path.write_text(report_md, encoding="utf-8")

    # Update meta
    meta_path = Path(args.base_dir) / args.slug / "meta.json"
    if meta_path.exists():
        _update_meta_json(meta_path, latent_finding_count)

    print(f"✓ 完整分析已保存：{analysis_path}")
    print(f"✓ 隐性知识发现已保存：{findings_path}")
    print(f"✓ 分析报告已生成：{report_path}")
    print(f"  发现隐性知识：{latent_finding_count} 条")

    return 0


if __name__ == "__main__":
    sys.exit(main())
