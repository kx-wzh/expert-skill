#!/usr/bin/env python3
"""
Unified pipeline runner for the P2-P7 expert knowledge discovery flow.

Commands:
  status  --slug SLUG  Show current pipeline progress and next action.
  next    --slug SLUG  Auto-run the next phase's prompt generation step.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

_TOOL_DIR = Path(__file__).parent

_PHASES: list[dict] = [
    {
        "from_status": ["not_started"],
        "label": "P2",
        "name": "前置研究",
        "tool": "pre_researcher.py",
        "prompt_file": "pre_research_prompt.md",
        "output_file": "expert_profile.json",
        "auto_run": False,
        "run_hint": (
            "python tools/pre_researcher.py"
            " --slug {slug} --base-dir {base_dir}"
            " --name 姓名 --expertise-type 类型"
            " [--title 职称] [--domain 领域] [--years 年数]"
        ),
        "parse_hint": (
            "python tools/pre_researcher.py"
            " --slug {slug} --base-dir {base_dir}"
            " --parse-output <AI输出文件路径>"
        ),
    },
    {
        "from_status": ["profile_ready"],
        "label": "P2.5",
        "name": "能力蓝图",
        "tool": "blueprint_builder.py",
        "prompt_file": "expert_blueprint_prompt.md",
        "output_file": "expert_blueprint.json",
        "auto_run": True,
        "parse_hint": (
            "python tools/blueprint_builder.py"
            " --slug {slug} --base-dir {base_dir}"
            " --parse-output <AI输出文件路径>"
        ),
    },
    {
        "from_status": ["blueprint_ready"],
        "label": "P3",
        "name": "隐性变量",
        "tool": "latent_variable_builder.py",
        "prompt_file": "latent_variable_prompt.md",
        "output_file": "latent_variables.json",
        "auto_run": True,
        "parse_hint": (
            "python tools/latent_variable_builder.py"
            " --slug {slug} --base-dir {base_dir}"
            " --parse-output <AI输出文件路径>"
        ),
    },
    {
        "from_status": ["variables_ready"],
        "label": "P4",
        "name": "三元组生成",
        "tool": "triplet_generator.py",
        "prompt_file": "triplet_builder_prompt.md",
        "output_file": "triplet_groups.json",
        "auto_run": True,
        "parse_hint": (
            "python tools/triplet_generator.py"
            " --slug {slug} --base-dir {base_dir}"
            " --parse-output <AI输出文件路径>"
        ),
    },
    {
        "from_status": ["triplets_ready", "interview_in_progress"],
        "label": "P5",
        "name": "访谈会话",
        "tool": "interview_session.py",
        "prompt_file": None,
        "output_file": "interview_transcript.json",
        "auto_run": False,
        "run_hint": (
            "python tools/interview_session.py"
            " --slug {slug} --base-dir {base_dir}"
        ),
        "parse_hint": None,
    },
    {
        "from_status": ["interview_completed"],
        "label": "P6",
        "name": "访谈分析",
        "tool": "interview_analyzer.py",
        "prompt_file": "interview_analyzer_prompt.md",
        "output_file": "interview_analysis.json",
        "auto_run": True,
        "parse_hint": (
            "python tools/interview_analyzer.py"
            " --slug {slug} --base-dir {base_dir}"
            " --parse-output <AI输出文件路径>"
        ),
    },
    {
        "from_status": ["analysis_ready"],
        "label": "P7",
        "name": "技能写入",
        "tool": "skill_writer.py",
        "prompt_file": None,
        "output_file": None,
        "auto_run": False,
        "run_hint": (
            "python tools/skill_writer.py"
            " --slug {slug} --base-dir {base_dir}"
            " --latent-report discovery/latent_report.md"
        ),
        "parse_hint": None,
    },
]


def _read_meta(base_dir: str, slug: str) -> dict:
    meta_path = Path(base_dir) / slug / "meta.json"
    if not meta_path.exists():
        return {}
    try:
        return json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}


def _get_status(meta: dict) -> str:
    return meta.get("discovery", {}).get("status", "not_started") or "not_started"


def _get_current_phase(status: str) -> dict | None:
    for phase in _PHASES:
        if status in phase["from_status"]:
            return phase
    return None


def _is_done(phase: dict, discovery_dir: Path, status: str) -> bool:
    if phase["label"] == "P7":
        return status == "merged"
    output_file = phase.get("output_file")
    return bool(output_file and (discovery_dir / output_file).exists())


def cmd_status(args: argparse.Namespace) -> int:
    meta = _read_meta(args.base_dir, args.slug)
    status = _get_status(meta)
    discovery_dir = Path(args.base_dir) / args.slug / "discovery"

    print(f"专家 Slug : {args.slug}")
    print(f"流程状态  : {status}")
    print()

    for phase in _PHASES:
        done = _is_done(phase, discovery_dir, status)
        is_current = status in phase["from_status"]
        if done:
            marker = "[完成]"
        elif is_current:
            marker = "[当前]"
        else:
            marker = "[ 待  ]"
        print(f"  {marker}  {phase['label']:4s}  {phase['name']}")

    print()
    current = _get_current_phase(status)
    if current:
        if current["auto_run"]:
            print(
                f"下一步：python tools/pipeline.py next"
                f" --slug {args.slug} --base-dir {args.base_dir}"
            )
        else:
            run_hint = current.get("run_hint", "")
            if run_hint:
                print(f"下一步：{run_hint.format(slug=args.slug, base_dir=args.base_dir)}")
    elif status == "merged":
        print("流程已完成。")
    elif status == "aborted":
        print("流程已中止。")

    return 0


def cmd_next(args: argparse.Namespace) -> int:
    meta = _read_meta(args.base_dir, args.slug)
    status = _get_status(meta)
    phase = _get_current_phase(status)

    if not phase:
        if status == "merged":
            print("流程已完成，无需继续。")
        elif status == "aborted":
            print("流程已中止。")
        else:
            print(f"未知状态：{status}")
        return 0

    print(f"当前阶段：{phase['label']} {phase['name']}")
    print()

    if phase["auto_run"]:
        tool_path = _TOOL_DIR / phase["tool"]
        cmd = [sys.executable, str(tool_path), "--slug", args.slug, "--base-dir", args.base_dir]
        result = subprocess.run(cmd)
        if result.returncode != 0:
            return result.returncode

        if phase.get("prompt_file"):
            prompt_path = Path(args.base_dir) / args.slug / "discovery" / phase["prompt_file"]
            print(f"\nPrompt 文件：{prompt_path}")

        print("\n后续步骤：")
        print("  1. 将上方 prompt 文件内容发送给 AI")
        parse_hint = phase.get("parse_hint")
        if parse_hint:
            print("  2. 将 AI 输出保存到文件，然后运行：")
            print(f"     {parse_hint.format(slug=args.slug, base_dir=args.base_dir)}")
    else:
        run_hint = phase.get("run_hint", "")
        if run_hint:
            print("请运行：")
            print(f"  {run_hint.format(slug=args.slug, base_dir=args.base_dir)}")
        parse_hint = phase.get("parse_hint")
        if parse_hint:
            print("\n完成后，解析 AI 输出：")
            print(f"  {parse_hint.format(slug=args.slug, base_dir=args.base_dir)}")

    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P2-P7 流程管理工具")
    sub = parser.add_subparsers(dest="command")

    def _add_common(p: argparse.ArgumentParser) -> None:
        p.add_argument("--slug", required=True, help="专家 slug")
        p.add_argument("--base-dir", default="./skills/expert", dest="base_dir", help="专家技能存储根目录")

    status_p = sub.add_parser("status", help="查看当前流程状态")
    _add_common(status_p)
    status_p.set_defaults(func=cmd_status)

    next_p = sub.add_parser("next", help="运行下一阶段的 prompt 生成步骤")
    _add_common(next_p)
    next_p.set_defaults(func=cmd_next)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 1

    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
