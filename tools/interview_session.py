#!/usr/bin/env python3
"""
Interview session tool for the P5 discovery phase.

Guides an operator through the A→B→C interview protocol for each triplet group,
records expert answers and signals, and produces interview_transcript.json/.md.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_FUZZY_LANGUAGE_DEFAULT_PROBE = "你感觉的线索是什么？"
_VALID_CAMERA_SIGNALS = {
    "noticed",
    "hesitated",
    "boundary_invented",
    "contradiction",
    "pushback",
    "fuzzy_language",
}
_VALID_CAMERA_CONFIDENCE = {"high", "medium", "low"}
_VALID_ANSWER_INPUT_MODES = {"manual_cli", "streaming_text"}
_FRAME_REFERENCE_MARKERS = (
    "frame_path",
    "/tmp/expert-skill-camera",
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
)


# ---------------------------------------------------------------------------
# Testable helper functions
# ---------------------------------------------------------------------------

def get_next_layer(records: list[dict], triplet_id: str) -> str:
    """Return the next layer ('A', 'B', 'C') for a triplet, or 'done' if all complete."""
    done = {r["question_layer"] for r in records if r["triplet_id"] == triplet_id}
    for layer in ("A", "B", "C"):
        if layer not in done:
            return layer
    return "done"


def build_interview_record(
    triplet_id: str,
    target_variable: str,
    layer: str,
    question_text: str,
    expert_answer: str,
    followup_asked: str,
    followup_answer: str,
    signals_observed: list[str],
    probe_suggestion: str,
    probe_adopted: bool | None,
    probe_modified_text: str | None,
    operator_notes: str,
    answer_input_mode: str = "manual_cli",
    camera_assist_enabled: bool = False,
    camera_suggestions: list[dict] | None = None,
) -> dict:
    """Build a single interview record dict."""
    return {
        "triplet_id": triplet_id,
        "target_variable": target_variable,
        "question_layer": layer,
        "question_text": question_text,
        "expert_answer": expert_answer,
        "followup_asked": followup_asked,
        "followup_answer": followup_answer,
        "signals_observed": signals_observed,
        "probe_suggestion": probe_suggestion,
        "probe_adopted": probe_adopted,
        "probe_modified_text": probe_modified_text,
        "operator_notes": operator_notes,
        "answer_input_mode": answer_input_mode,
        "camera_assist_enabled": camera_assist_enabled,
        "camera_suggestions": camera_suggestions,
    }


def build_camera_suggestion(
    signal: str,
    confidence: str,
    reason: str,
    suggested_probe: str,
    accepted: bool = False,
    final_probe: str = "",
) -> dict:
    """Build a camera-assisted probe suggestion dict."""
    return {
        "signal": signal,
        "confidence": confidence,
        "reason": reason,
        "suggested_probe": suggested_probe,
        "accepted": accepted,
        "final_probe": final_probe,
    }


def suggest_probe_for_signals(question: dict, signals: list[str]) -> dict:
    """Map observed signals to suggested probe texts. Returns {signal: probe_text}."""
    triggers = question.get("probes", {}).get("signal_triggers", {})
    result: dict[str, str] = {}
    for sig in signals:
        if sig in triggers:
            result[sig] = triggers[sig]
        elif sig == "fuzzy_language":
            result[sig] = _FUZZY_LANGUAGE_DEFAULT_PROBE
    return result


def write_breakpoint(
    discovery_dir: Path,
    next_triplet_id: str,
    next_layer: str,
    completed_triplets: list[str],
) -> None:
    """Write interview_breakpoint.json with current position."""
    bp = {
        "next_triplet_id": next_triplet_id,
        "next_layer": next_layer,
        "completed_triplets": completed_triplets,
        "next_action": (
            f"continue_{next_layer}_or_skip" if next_layer else "triplet_complete"
        ),
    }
    (discovery_dir / "interview_breakpoint.json").write_text(
        json.dumps(bp, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def _contains_frame_reference(value) -> bool:
    if isinstance(value, str):
        return any(marker in value for marker in _FRAME_REFERENCE_MARKERS)
    if isinstance(value, dict):
        return any(
            _contains_frame_reference(k) or _contains_frame_reference(v)
            for k, v in value.items()
        )
    if isinstance(value, list):
        return any(_contains_frame_reference(item) for item in value)
    return False


def validate_camera_suggestions(record: dict) -> list[str]:
    """Validate camera assistance fields for a single transcript record."""
    errors: list[str] = []
    tid = record.get("triplet_id", "?")
    layer = record.get("question_layer", "?")

    answer_input_mode = record.get("answer_input_mode")
    if answer_input_mode is not None and answer_input_mode not in _VALID_ANSWER_INPUT_MODES:
        errors.append(
            f"P5: 三联体 {tid} {layer} 层 answer_input_mode 非法：{answer_input_mode}"
        )

    camera_suggestions = record.get("camera_suggestions")
    if camera_suggestions is not None and not isinstance(camera_suggestions, list):
        errors.append(f"P5: 三联体 {tid} {layer} 层 camera_suggestions must be list")
        camera_suggestions = []
    elif camera_suggestions is None:
        camera_suggestions = []

    signals_observed = set(record.get("signals_observed", []))
    for index, suggestion in enumerate(camera_suggestions):
        field_prefix = f"camera_suggestions[{index}]"
        if not isinstance(suggestion, dict):
            errors.append(f"P5: 三联体 {tid} {layer} 层 {field_prefix} must be dict")
            continue

        signal = suggestion.get("signal")
        if signal not in _VALID_CAMERA_SIGNALS:
            errors.append(
                f"P5: 三联体 {tid} {layer} 层 {field_prefix}.signal 非法：{signal}"
            )

        confidence = suggestion.get("confidence")
        if confidence not in _VALID_CAMERA_CONFIDENCE:
            errors.append(
                f"P5: 三联体 {tid} {layer} 层 {field_prefix}.confidence 非法：{confidence}"
            )

        if not isinstance(suggestion.get("suggested_probe"), str):
            errors.append(
                f"P5: 三联体 {tid} {layer} 层 {field_prefix}.suggested_probe must be string"
            )

        if suggestion.get("accepted") is True and signal not in signals_observed:
            errors.append(
                f"P5: 三联体 {tid} {layer} 层 accepted camera signal must be present in signals_observed"
            )

    if _contains_frame_reference(record):
        errors.append(f"P5: 三联体 {tid} {layer} 层 must not contain frame paths")

    return errors


def check_p5_quality_gate(records: list[dict]) -> list[str]:
    """Validate interview records. Returns list of error strings (empty = pass)."""
    errors: list[str] = []

    # Track layers in insertion order to detect duplicates and ordering violations
    triplet_layer_order: dict[str, list[str]] = {}
    triplet_records: dict[str, dict[str, dict]] = {}

    for r in records:
        tid = r.get("triplet_id", "?")
        layer = r.get("question_layer", "?")
        triplet_layer_order.setdefault(tid, [])
        triplet_records.setdefault(tid, {})

        if layer in triplet_records[tid]:
            errors.append(f"P5: 三联体 {tid} 出现重复层级 {layer}")
        else:
            triplet_layer_order[tid].append(layer)
            triplet_records[tid][layer] = r
        errors.extend(validate_camera_suggestions(r))

    for tid, ordered_layers in triplet_layer_order.items():
        layers = triplet_records[tid]

        # Check A→B→C ordering
        abc_in_order = [l for l in ordered_layers if l in ("A", "B", "C")]
        expected_order = [l for l in ("A", "B", "C") if l in layers]
        if abc_in_order != expected_order:
            errors.append(
                f"P5: 三联体 {tid} 层级顺序不正确（应为 A→B→C，"
                f"实际为 {'→'.join(abc_in_order) or '（无）'}）"
            )

        # Check A/B/C completeness and per-record fields
        for layer in ("A", "B", "C"):
            if layer not in layers:
                errors.append(f"P5: 三联体 {tid} 缺少 {layer} 层记录")
                continue
            r = layers[layer]
            if not r.get("expert_answer", "").strip():
                errors.append(f"P5: 三联体 {tid} {layer} 层 expert_answer 为空或只含空白")
            if "signals_observed" not in r:
                errors.append(f"P5: 三联体 {tid} {layer} 层缺少 signals_observed 字段")
                continue
            signals = r.get("signals_observed", [])
            if signals:
                if not r.get("probe_suggestion"):
                    errors.append(f"P5: 三联体 {tid} {layer} 层有信号但 probe_suggestion 为空")
                if r.get("probe_adopted") is None:
                    errors.append(f"P5: 三联体 {tid} {layer} 层有信号但 probe_adopted 为 null")

        # Check at least one complete followup round per triplet
        has_followup = any(
            r.get("followup_asked", "").strip() and r.get("followup_answer", "").strip()
            for r in layers.values()
        )
        if not has_followup:
            errors.append(
                f"P5: 三联体 {tid} 缺少至少一轮完整追问记录"
                f"（需要至少一条记录 followup_asked 和 followup_answer 均非空）"
            )

    return errors


# ---------------------------------------------------------------------------
# Interactive layer runner
# ---------------------------------------------------------------------------

def _collect_multiline(input_fn) -> str:
    """Collect multi-line input ending with a line containing only '/done'."""
    lines: list[str] = []
    while True:
        line = input_fn("")
        if line.strip() == "/done":
            break
        lines.append(line)
    return "\n".join(lines)


def run_one_layer(
    group: dict,
    layer: str,
    input_fn,
    print_fn,
) -> dict:
    """Conduct the interview for one question layer. Returns a record dict."""
    q_key = f"question_{layer}"
    question = group.get(q_key, {})
    triplet_id = group.get("id", "?")
    target_variable = group.get("target_variable", "")

    print_fn(f"\n{'=' * 60}")
    print_fn(f"[三联体 {triplet_id}]  问题 {layer}")
    print_fn("=" * 60)
    print_fn(question.get("text", "（题目文本缺失）"))
    print_fn("\n(请记录专家回答，输入完成后单独一行输入 /done)")
    expert_answer = _collect_multiline(input_fn)

    probes = question.get("probes", {})
    primary_probe = probes.get("primary", "")
    print_fn(f"\n推荐追问：{primary_probe}")
    followup_asked = primary_probe
    print_fn("(输入追问记录，直接回车跳过)")
    followup_answer = input_fn("").strip()

    print_fn("\n信号标注（空格分隔，直接回车跳过）：")
    print_fn("可选：noticed / hesitated / boundary_invented / contradiction / pushback / fuzzy_language")
    sig_input = input_fn("").strip()
    signals = [s.strip() for s in sig_input.split() if s.strip()] if sig_input else []

    probe_suggestion = ""
    probe_adopted: bool | None = None
    probe_modified_text: str | None = None

    if signals:
        suggestions = suggest_probe_for_signals(question, signals)
        if suggestions:
            for sig, text in suggestions.items():
                print_fn(f"\n[{sig}] 建议追问：{text}")
            probe_suggestion = next(iter(suggestions.values()))
            print_fn("\n是否采用建议追问？(y=采用 / n=不采用 / modify=修改)")
            choice = input_fn("").strip().lower()
            if choice == "y":
                probe_adopted = True
            elif choice == "n":
                probe_adopted = False
            elif choice == "modify":
                probe_adopted = True
                probe_modified_text = input_fn("").strip()

    print_fn("操作者备注（直接回车跳过）：")
    operator_notes = input_fn("").strip()

    return build_interview_record(
        triplet_id=triplet_id,
        target_variable=target_variable,
        layer=layer,
        question_text=question.get("text", ""),
        expert_answer=expert_answer,
        followup_asked=followup_asked,
        followup_answer=followup_answer,
        signals_observed=signals,
        probe_suggestion=probe_suggestion,
        probe_adopted=probe_adopted,
        probe_modified_text=probe_modified_text,
        operator_notes=operator_notes,
    )


def run_triplet_interview(
    group: dict,
    discovery_dir: Path,
    records: list[dict],
    completed_triplets: list[str],
    force_start_layer: str | None = None,
    input_fn=None,
    print_fn=None,
    persist_records_fn=None,
) -> list[dict]:
    """Run the A→B→C interview for one triplet group. Returns newly created records.

    If force_start_layer is provided and doesn't match get_next_layer(), raises ValueError.
    """
    if input_fn is None:
        input_fn = input
    if print_fn is None:
        print_fn = print

    triplet_id = group.get("id", "?")
    expected_layer = get_next_layer(records, triplet_id)

    if force_start_layer is not None and force_start_layer != expected_layer:
        raise ValueError(
            f"三联体 {triplet_id} 期望从 {expected_layer} 层开始，"
            f"但尝试从 {force_start_layer} 层开始（不允许跳层）"
        )

    start_layer = expected_layer
    if start_layer == "done":
        print_fn(f"三联体 {triplet_id} 已完成，跳过。")
        return []

    new_records: list[dict] = []
    for layer in ("A", "B", "C"):
        if layer < start_layer:
            continue
        record = run_one_layer(group, layer, input_fn, print_fn)
        new_records.append(record)

        all_records = records + new_records
        next_l = get_next_layer(all_records, triplet_id)
        done_now = completed_triplets + ([triplet_id] if next_l == "done" else [])
        write_breakpoint(
            discovery_dir,
            next_triplet_id=triplet_id,
            next_layer=next_l if next_l != "done" else "",
            completed_triplets=done_now,
        )
        if persist_records_fn is not None:
            persist_records_fn(all_records)

    return new_records


# ---------------------------------------------------------------------------
# Transcript generation
# ---------------------------------------------------------------------------

def generate_transcript_md(records: list[dict], groups: list[dict]) -> str:
    """Render interview records as a readable Markdown document."""
    group_labels = {g.get("id", ""): g.get("target_variable_label", g.get("target_variable", "")) for g in groups}
    lines = ["# 访谈记录", ""]

    by_triplet: dict[str, dict[str, dict]] = {}
    for r in records:
        tid = r.get("triplet_id", "?")
        layer = r.get("question_layer", "?")
        by_triplet.setdefault(tid, {})[layer] = r

    for tid, layers in by_triplet.items():
        label = group_labels.get(tid, tid)
        lines += [f"## 三联体 {tid} — {label}", ""]
        for layer in ("A", "B", "C"):
            r = layers.get(layer)
            if not r:
                continue
            lines += [
                f"### 问题 {layer}", "",
                f"**题目**：{r.get('question_text', '')}", "",
                f"**专家回答**：{r.get('expert_answer', '')}", "",
            ]
            if r.get("followup_asked"):
                lines += [f"**追问**：{r['followup_asked']}", ""]
            if r.get("followup_answer"):
                lines += [f"**追问回答**：{r['followup_answer']}", ""]
            sigs = r.get("signals_observed", [])
            if sigs:
                lines += [f"**信号**：{', '.join(sigs)}", ""]
            if r.get("probe_suggestion"):
                lines += [f"**建议追问**：{r['probe_suggestion']}", ""]
            if r.get("probe_adopted") is not None:
                adopted_str = "已采用" if r["probe_adopted"] else "未采用"
                if r.get("probe_modified_text"):
                    adopted_str += f"（修改为：{r['probe_modified_text']}）"
                lines += [f"**采用情况**：{adopted_str}", ""]
            if r.get("operator_notes"):
                lines += [f"**操作者备注**：{r['operator_notes']}", ""]
            lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Meta update
# ---------------------------------------------------------------------------

def _update_meta_status(meta_path: Path, status: str) -> None:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return
    meta.setdefault("discovery", {})["status"] = status
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None, input_fn=None, print_fn=None) -> int:
    parser = argparse.ArgumentParser(description="P5 访谈记录工具")
    parser.add_argument("--slug", required=True)
    parser.add_argument("--base-dir", default="./skills/expert", dest="base_dir")
    parser.add_argument("--triplet-id", default="", dest="triplet_id",
                        help="只记录指定三联体（默认全部）")
    parser.add_argument("--resume", action="store_true",
                        help="从上次中断点继续")
    parser.add_argument("--dry-run", action="store_true", dest="dry_run",
                        help="打印访谈脚本但不写文件，不进入交互")
    args = parser.parse_args(argv)

    if args.triplet_id and args.resume:
        print("错误：--triplet-id 与 --resume 不能同时使用", file=sys.stderr)
        return 1

    _print = print_fn or print
    _input = input_fn or input

    discovery_dir = Path(args.base_dir) / args.slug / "discovery"
    groups_path = discovery_dir / "triplet_groups.json"
    if not groups_path.exists():
        print(f"错误：找不到 triplet_groups.json：{groups_path}", file=sys.stderr)
        return 1
    all_groups: list[dict] = json.loads(groups_path.read_text(encoding="utf-8"))

    # Dry-run: print script and exit
    if args.dry_run:
        for g in all_groups:
            gid = g.get("id", "?")
            _print(f"\n{'='*60}")
            _print(f"[{gid}] {g.get('target_variable_label', g.get('target_variable', ''))}")
            _print("=" * 60)
            for layer, q_key in [("A", "question_A"), ("B", "question_B"), ("C", "question_C")]:
                q = g.get(q_key, {})
                _print(f"\n--- 问题 {layer} ---")
                _print(q.get("text", ""))
                _print(f"推荐追问：{q.get('probes', {}).get('primary', '')}")
        return 0

    # Filter groups by --triplet-id
    target_groups = [g for g in all_groups if g.get("id") == args.triplet_id] if args.triplet_id else all_groups

    # Load existing records and breakpoint
    transcript_path = discovery_dir / "interview_transcript.json"
    records: list[dict] = []
    completed_triplets: list[str] = []

    if args.resume:
        bp_path = discovery_dir / "interview_breakpoint.json"
        if not bp_path.exists():
            print("错误：找不到 interview_breakpoint.json，无法 --resume", file=sys.stderr)
            return 1
        bp = json.loads(bp_path.read_text(encoding="utf-8"))
        completed_triplets = bp.get("completed_triplets", [])
        resume_triplet_id = bp.get("next_triplet_id", "")
        resume_layer = bp.get("next_layer") or None
        if transcript_path.exists():
            records = json.loads(transcript_path.read_text(encoding="utf-8"))
    else:
        resume_triplet_id = ""
        resume_layer = None

    if args.resume and resume_triplet_id:
        matching_index = next(
            (i for i, g in enumerate(target_groups) if g.get("id") == resume_triplet_id),
            None,
        )
        if matching_index is None:
            print(f"错误：断点中的三联体不存在：{resume_triplet_id}", file=sys.stderr)
            return 1
        target_groups = target_groups[matching_index:]

    # Create discovery dir if needed
    discovery_dir.mkdir(parents=True, exist_ok=True)

    # Update meta to interview_in_progress at start
    meta_path = Path(args.base_dir) / args.slug / "meta.json"
    if meta_path.exists():
        _update_meta_status(meta_path, "interview_in_progress")

    # Run sessions
    for group in target_groups:
        gid = group.get("id", "?")
        if gid in completed_triplets:
            continue
        if get_next_layer(records, gid) == "done":
            completed_triplets.append(gid)
            continue
        force_start_layer = resume_layer if args.resume and gid == resume_triplet_id else None

        def _persist_records(current_records: list[dict]) -> None:
            transcript_path.write_text(
                json.dumps(current_records, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        new_recs = run_triplet_interview(
            group, discovery_dir, records, completed_triplets,
            force_start_layer=force_start_layer,
            input_fn=_input, print_fn=_print,
            persist_records_fn=_persist_records,
        )
        records.extend(new_recs)
        if get_next_layer(records, gid) == "done":
            if gid not in completed_triplets:
                completed_triplets.append(gid)

        # Save transcript after each triplet as a final guard. The per-layer
        # persistence above is what makes --resume robust after interruption.
        transcript_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")

    # Generate Markdown transcript
    md_path = discovery_dir / "interview_transcript.md"
    md_path.write_text(generate_transcript_md(records, all_groups), encoding="utf-8")

    # Check if all groups are done
    all_done = all(get_next_layer(records, g.get("id", "")) == "done" for g in all_groups)

    # P5 quality gate and final status update
    if all_done and not args.triplet_id:
        gate_errors = check_p5_quality_gate(records)
        if gate_errors:
            _print("\n⚠️  P5 质量门未通过：")
            for e in gate_errors:
                _print(f"  - {e}")
            _print("discovery.status 保持 interview_in_progress")
        else:
            if meta_path.exists():
                _update_meta_status(meta_path, "interview_completed")
            _print("\n✓ 所有三联体访谈完成，P5 质量门通过，status → interview_completed")
    else:
        _print(f"\n访谈进行中（已完成 {len(completed_triplets)}/{len(all_groups)} 个三联体）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
