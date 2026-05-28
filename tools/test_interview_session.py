#!/usr/bin/env python3
"""Tests for tools/interview_session.py"""

import json
import sys
import threading
import time
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import interview_session as iss

# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------

SAMPLE_GROUP = {
    "id": "tg_001",
    "target_variable": "lv_001",
    "target_variable_label": "测试变量",
    "question_A": {
        "text": "A题目",
        "probes": {
            "primary": "A追问",
            "signal_triggers": {
                "noticed": "你看出来什么不同让你改了判断？",
                "hesitated": "你在衡量什么？",
            },
        },
    },
    "question_B": {
        "text": "B题目",
        "probes": {
            "primary": "B追问",
            "signal_triggers": {},
        },
    },
    "question_C": {
        "text": "C题目",
        "probes": {
            "primary": "C追问",
            "signal_triggers": {},
        },
    },
}

SAMPLE_GROUP_2 = {
    "id": "tg_002",
    "target_variable": "lv_002",
    "target_variable_label": "第二变量",
    "question_A": {"text": "A2题目", "probes": {"primary": "A2追问", "signal_triggers": {}}},
    "question_B": {"text": "B2题目", "probes": {"primary": "B2追问", "signal_triggers": {}}},
    "question_C": {"text": "C2题目", "probes": {"primary": "C2追问", "signal_triggers": {}}},
}


def make_input_fn(*responses):
    """Return an input_fn that yields responses in order."""
    it = iter(responses)
    def _input(prompt=""):
        return next(it)
    return _input


def layer_inputs(answer="专家回答", followup="", signals="", notes="",
                 probe_choice=None, modified_text=None):
    """Build input sequence for one question layer.

    Sequence:
      answer, /done, followup, signals[, probe_choice[, modified_text]], notes
    probe_choice is only included when signals is non-empty and probe_choice is given.
    """
    seq = [answer, "/done", followup, signals]
    if signals.strip() and probe_choice is not None:
        seq.append(probe_choice)
        if probe_choice == "modify" and modified_text is not None:
            seq.append(modified_text)
    seq.append(notes)
    return seq


def setup_discovery_dir(tmp_path, groups, meta=None, slug="expert_a"):
    """Create minimal discovery dir structure for testing main()."""
    base = tmp_path / "skills" / "expert"
    discovery = base / slug / "discovery"
    discovery.mkdir(parents=True)
    (discovery / "triplet_groups.json").write_text(
        json.dumps(groups, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    if meta is not None:
        meta_path = base / slug / "meta.json"
        meta_path.write_text(
            json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    return base, discovery


def _full_session_inputs(group_count=1):
    """Return inputs for `group_count` groups, each with 3 layers.

    Layer A includes a non-empty followup so the P5 quality gate
    (at least one complete followup per triplet) is satisfied.
    """
    seq = []
    for _ in range(group_count):
        seq += layer_inputs(answer="回答A", followup="追问回答A")
        seq += layer_inputs(answer="回答B")
        seq += layer_inputs(answer="回答C")
    return seq


# ---------------------------------------------------------------------------
# 1. test_dry_run_prints_script_does_not_write
# ---------------------------------------------------------------------------

def test_dry_run_prints_script_does_not_write(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP])
    printed = []
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base), "--dry-run"],
        print_fn=printed.append,
        input_fn=None,
    )
    assert ret == 0
    text = "\n".join(str(x) for x in printed)
    assert "A题目" in text
    assert "B题目" in text
    assert "C题目" in text
    assert not (discovery / "interview_transcript.json").exists()
    assert not (discovery / "interview_breakpoint.json").exists()


# ---------------------------------------------------------------------------
# 2. test_session_enforces_abc_order
# ---------------------------------------------------------------------------

def test_session_enforces_abc_order(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP])
    with pytest.raises(ValueError, match="跳层"):
        iss.run_triplet_interview(
            SAMPLE_GROUP, discovery, [], [],
            force_start_layer="B",
            input_fn=make_input_fn(),
            print_fn=lambda x: None,
        )


# ---------------------------------------------------------------------------
# 3. test_signal_annotation_maps_to_probe
# ---------------------------------------------------------------------------

def test_signal_annotation_maps_to_probe():
    probes = iss.suggest_probe_for_signals(SAMPLE_GROUP["question_A"], ["noticed"])
    assert "noticed" in probes
    assert probes["noticed"] == "你看出来什么不同让你改了判断？"


# ---------------------------------------------------------------------------
# 4. test_probe_adopted_recorded
# ---------------------------------------------------------------------------

def test_probe_adopted_recorded():
    inputs = layer_inputs(answer="专家回答A", signals="noticed", probe_choice="y")
    record = iss.run_one_layer(
        SAMPLE_GROUP, "A",
        make_input_fn(*inputs),
        lambda x: None,
    )
    assert record["probe_adopted"] is True
    assert record["probe_modified_text"] is None


# ---------------------------------------------------------------------------
# 5. test_probe_not_adopted_recorded
# ---------------------------------------------------------------------------

def test_probe_not_adopted_recorded():
    inputs = layer_inputs(answer="专家回答A", signals="noticed", probe_choice="n")
    record = iss.run_one_layer(
        SAMPLE_GROUP, "A",
        make_input_fn(*inputs),
        lambda x: None,
    )
    assert record["probe_adopted"] is False


# ---------------------------------------------------------------------------
# 6. test_probe_modified_text_recorded
# ---------------------------------------------------------------------------

def test_probe_modified_text_recorded():
    inputs = layer_inputs(
        answer="专家回答A", signals="noticed",
        probe_choice="modify", modified_text="自定义追问文本",
    )
    record = iss.run_one_layer(
        SAMPLE_GROUP, "A",
        make_input_fn(*inputs),
        lambda x: None,
    )
    assert record["probe_adopted"] is True
    assert record["probe_modified_text"] == "自定义追问文本"


# ---------------------------------------------------------------------------
# 7. test_breakpoint_written_after_each_layer
# ---------------------------------------------------------------------------

def test_breakpoint_written_after_each_layer(tmp_path):
    discovery = tmp_path / "discovery"
    discovery.mkdir()

    iss.write_breakpoint(discovery, "tg_001", "B", [])

    bp_path = discovery / "interview_breakpoint.json"
    assert bp_path.exists()
    bp = json.loads(bp_path.read_text(encoding="utf-8"))
    assert bp["next_triplet_id"] == "tg_001"
    assert bp["next_layer"] == "B"
    assert bp["completed_triplets"] == []


# ---------------------------------------------------------------------------
# 8. test_resume_skips_completed_triplets
# ---------------------------------------------------------------------------

def test_resume_skips_completed_triplets(tmp_path):
    groups = [SAMPLE_GROUP, SAMPLE_GROUP_2]
    base, discovery = setup_discovery_dir(tmp_path, groups, meta={"discovery": {}})

    # Populate transcript with tg_001 fully done
    pre_records = [
        {
            "triplet_id": "tg_001", "target_variable": "lv_001",
            "question_layer": layer, "question_text": f"{layer}题",
            "expert_answer": "已有回答", "followup_asked": "", "followup_answer": "",
            "signals_observed": [], "probe_suggestion": "",
            "probe_adopted": None, "probe_modified_text": None, "operator_notes": "",
        }
        for layer in ("A", "B", "C")
    ]
    (discovery / "interview_transcript.json").write_text(
        json.dumps(pre_records), encoding="utf-8"
    )
    (discovery / "interview_breakpoint.json").write_text(
        json.dumps({
            "next_triplet_id": "tg_002",
            "next_layer": "A",
            "completed_triplets": ["tg_001"],
            "next_action": "continue_A_or_skip",
        }),
        encoding="utf-8",
    )

    # Inputs only for tg_002 (A + B + C)
    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base), "--resume"],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    transcript = json.loads(
        (discovery / "interview_transcript.json").read_text(encoding="utf-8")
    )
    assert sum(1 for r in transcript if r["triplet_id"] == "tg_002") == 3


# ---------------------------------------------------------------------------
# 9. test_triplet_id_filter
# ---------------------------------------------------------------------------

def test_triplet_id_filter(tmp_path):
    groups = [SAMPLE_GROUP, SAMPLE_GROUP_2]
    base, discovery = setup_discovery_dir(tmp_path, groups, meta={"discovery": {}})

    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base), "--triplet-id", "tg_001"],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    transcript = json.loads(
        (discovery / "interview_transcript.json").read_text(encoding="utf-8")
    )
    triplet_ids = {r["triplet_id"] for r in transcript}
    assert "tg_001" in triplet_ids
    assert "tg_002" not in triplet_ids


# ---------------------------------------------------------------------------
# 10. test_triplet_id_and_resume_conflict
# ---------------------------------------------------------------------------

def test_triplet_id_and_resume_conflict(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP])
    ret = iss.main(
        argv=[
            "--slug", "expert_a", "--base-dir", str(base),
            "--triplet-id", "tg_001", "--resume",
        ],
        input_fn=make_input_fn(),
        print_fn=lambda x: None,
    )
    assert ret == 1


# ---------------------------------------------------------------------------
# 11. test_transcript_json_saved
# ---------------------------------------------------------------------------

def test_transcript_json_saved(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base)],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    json_path = discovery / "interview_transcript.json"
    assert json_path.exists()
    transcript = json.loads(json_path.read_text(encoding="utf-8"))
    assert len(transcript) == 3  # A, B, C for tg_001


# ---------------------------------------------------------------------------
# 12. test_transcript_md_generated
# ---------------------------------------------------------------------------

def test_transcript_md_generated(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base)],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    md_path = discovery / "interview_transcript.md"
    assert md_path.exists()
    content = md_path.read_text(encoding="utf-8")
    assert "# 访谈记录" in content
    assert "tg_001" in content


# ---------------------------------------------------------------------------
# 13. test_p5_quality_gate_passes
# ---------------------------------------------------------------------------

def test_p5_quality_gate_passes():
    records = [
        {
            "triplet_id": "tg_001",
            "question_layer": "A",
            "expert_answer": "有效回答",
            "followup_asked": "这是怎么想到的？",
            "followup_answer": "有具体经历支撑",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "有效回答",
            "followup_asked": "",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
        {
            "triplet_id": "tg_001",
            "question_layer": "C",
            "expert_answer": "有效回答",
            "followup_asked": "",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
    ]
    errors = iss.check_p5_quality_gate(records)
    assert errors == []


# ---------------------------------------------------------------------------
# 14. test_p5_quality_gate_fails_missing_layer
# ---------------------------------------------------------------------------

def test_p5_quality_gate_fails_missing_layer():
    records = [
        {"triplet_id": "tg_001", "question_layer": "A", "expert_answer": "回答", "signals_observed": []},
        {"triplet_id": "tg_001", "question_layer": "B", "expert_answer": "回答", "signals_observed": []},
        # C layer intentionally omitted
    ]
    errors = iss.check_p5_quality_gate(records)
    assert any("C" in e for e in errors)


# ---------------------------------------------------------------------------
# 15. test_p5_quality_gate_fails_probe_adopted_null
# ---------------------------------------------------------------------------

def test_p5_quality_gate_fails_probe_adopted_null():
    records = [
        {
            "triplet_id": "tg_001",
            "question_layer": layer,
            "expert_answer": "回答",
            "signals_observed": ["noticed"],
            "probe_suggestion": "追问文本",
            "probe_adopted": None,  # must be True/False when signals exist
        }
        for layer in ("A", "B", "C")
    ]
    errors = iss.check_p5_quality_gate(records)
    assert any("probe_adopted" in e for e in errors)


# ---------------------------------------------------------------------------
# 16. test_partial_triplet_does_not_mark_analysis_ready
# ---------------------------------------------------------------------------

def test_partial_triplet_does_not_mark_analysis_ready(tmp_path):
    groups = [SAMPLE_GROUP, SAMPLE_GROUP_2]
    meta = {"discovery": {"status": "triplets_ready"}}
    base, discovery = setup_discovery_dir(tmp_path, groups, meta=meta)

    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base), "--triplet-id", "tg_001"],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    meta_data = json.loads((base / "expert_a" / "meta.json").read_text(encoding="utf-8"))
    assert meta_data["discovery"]["status"] not in ("analysis_ready", "interview_completed")


# ---------------------------------------------------------------------------
# 17. test_fuzzy_language_uses_default_probe
# ---------------------------------------------------------------------------

def test_fuzzy_language_uses_default_probe():
    probes = iss.suggest_probe_for_signals(SAMPLE_GROUP["question_A"], ["fuzzy_language"])
    assert "fuzzy_language" in probes
    assert probes["fuzzy_language"] == "你感觉的线索是什么？"


# ---------------------------------------------------------------------------
# 18. test_resume_uses_next_layer_from_breakpoint
# ---------------------------------------------------------------------------

def test_resume_uses_next_layer_from_breakpoint(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})

    # Transcript has A layer done; breakpoint says next is B
    pre_records = [{
        "triplet_id": "tg_001", "target_variable": "lv_001",
        "question_layer": "A", "question_text": "A题目",
        "expert_answer": "已有回答", "followup_asked": "", "followup_answer": "",
        "signals_observed": [], "probe_suggestion": "",
        "probe_adopted": None, "probe_modified_text": None, "operator_notes": "",
    }]
    (discovery / "interview_transcript.json").write_text(
        json.dumps(pre_records), encoding="utf-8"
    )
    (discovery / "interview_breakpoint.json").write_text(
        json.dumps({
            "next_triplet_id": "tg_001",
            "next_layer": "B",
            "completed_triplets": [],
            "next_action": "continue_B_or_skip",
        }),
        encoding="utf-8",
    )

    # Only B and C inputs needed (A is already recorded).
    # B includes a followup answer so the P5 gate (one complete followup per triplet) passes.
    inputs = layer_inputs(answer="回答B", followup="追问回答B") + layer_inputs(answer="回答C")
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base), "--resume"],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    transcript = json.loads(
        (discovery / "interview_transcript.json").read_text(encoding="utf-8")
    )
    layers = {r["question_layer"] for r in transcript if r["triplet_id"] == "tg_001"}
    assert layers == {"A", "B", "C"}


# ---------------------------------------------------------------------------
# 19. test_run_triplet_persists_after_each_layer
# ---------------------------------------------------------------------------

def test_run_triplet_persists_after_each_layer(tmp_path):
    discovery = tmp_path / "discovery"
    discovery.mkdir()
    snapshots = []

    inputs = layer_inputs(answer="回答A") + layer_inputs(answer="回答B") + layer_inputs(answer="回答C")
    new_records = iss.run_triplet_interview(
        SAMPLE_GROUP,
        discovery,
        [],
        [],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
        persist_records_fn=lambda records: snapshots.append([r["question_layer"] for r in records]),
    )

    assert [r["question_layer"] for r in new_records] == ["A", "B", "C"]
    assert snapshots == [["A"], ["A", "B"], ["A", "B", "C"]]


# ---------------------------------------------------------------------------
# 20. test_quality_gate_fails_empty_expert_answer
# ---------------------------------------------------------------------------

def test_quality_gate_fails_empty_expert_answer():
    records = [
        {
            "triplet_id": "tg_001",
            "question_layer": layer,
            "expert_answer": "  " if layer == "B" else "有效回答",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        }
        for layer in ("A", "B", "C")
    ]
    errors = iss.check_p5_quality_gate(records)
    assert any("expert_answer" in e for e in errors)


# ---------------------------------------------------------------------------
# 21. test_record_uses_target_variable_field
# ---------------------------------------------------------------------------

def test_record_uses_target_variable_field():
    record = iss.build_interview_record(
        triplet_id="tg_001",
        target_variable="lv_001",
        layer="A",
        question_text="题目",
        expert_answer="回答",
        followup_asked="",
        followup_answer="",
        signals_observed=[],
        probe_suggestion="",
        probe_adopted=None,
        probe_modified_text=None,
        operator_notes="",
    )
    assert "target_variable" in record
    assert "target_variable_id" not in record
    assert record["target_variable"] == "lv_001"


# ---------------------------------------------------------------------------
# 21. test_interview_completed_is_valid_discovery_status
# ---------------------------------------------------------------------------

def test_interview_completed_is_valid_discovery_status():
    import discovery_schema as ds
    assert "interview_completed" in ds.DISCOVERY_STATUSES


# ---------------------------------------------------------------------------
# 22. test_interview_completion_sets_interview_completed_status
# ---------------------------------------------------------------------------

def test_interview_completion_sets_interview_completed_status(tmp_path):
    base, discovery = setup_discovery_dir(
        tmp_path, [SAMPLE_GROUP], meta={"discovery": {"status": "triplets_ready"}}
    )
    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base)],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    meta_data = json.loads((base / "expert_a" / "meta.json").read_text(encoding="utf-8"))
    assert meta_data["discovery"]["status"] == "interview_completed"


# ---------------------------------------------------------------------------
# 23. test_p5_quality_gate_fails_when_no_followup_recorded
# ---------------------------------------------------------------------------

def test_p5_quality_gate_fails_when_no_followup_recorded():
    records = [
        {
            "triplet_id": "tg_001",
            "question_layer": layer,
            "expert_answer": "有效回答",
            "followup_asked": "",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        }
        for layer in ("A", "B", "C")
    ]
    errors = iss.check_p5_quality_gate(records)
    assert any("追问" in e for e in errors), f"Expected followup error, got: {errors}"


# ---------------------------------------------------------------------------
# 24. test_p5_quality_gate_fails_when_followup_answer_empty
# ---------------------------------------------------------------------------

def test_p5_quality_gate_fails_when_followup_answer_empty():
    # followup_asked is non-empty but followup_answer is empty in all records
    records = [
        {
            "triplet_id": "tg_001",
            "question_layer": layer,
            "expert_answer": "有效回答",
            "followup_asked": "这是怎么想到的？",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        }
        for layer in ("A", "B", "C")
    ]
    errors = iss.check_p5_quality_gate(records)
    assert any("追问" in e for e in errors), f"Expected followup error, got: {errors}"


# ---------------------------------------------------------------------------
# 25. test_p5_quality_gate_fails_when_layers_out_of_order
# ---------------------------------------------------------------------------

def test_p5_quality_gate_fails_when_layers_out_of_order():
    # B appears before A — violates A→B→C ordering requirement
    records = [
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "回答B",
            "followup_asked": "追问",
            "followup_answer": "回答",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
        {
            "triplet_id": "tg_001",
            "question_layer": "A",
            "expert_answer": "回答A",
            "followup_asked": "",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
        {
            "triplet_id": "tg_001",
            "question_layer": "C",
            "expert_answer": "回答C",
            "followup_asked": "",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
    ]
    errors = iss.check_p5_quality_gate(records)
    assert any("顺序" in e for e in errors), f"Expected ordering error, got: {errors}"


# ---------------------------------------------------------------------------
# 26. test_p5_quality_gate_fails_duplicate_layer
# ---------------------------------------------------------------------------

def test_p5_quality_gate_fails_duplicate_layer():
    # A appears twice
    records = [
        {
            "triplet_id": "tg_001",
            "question_layer": "A",
            "expert_answer": "回答A（第一次）",
            "followup_asked": "追问",
            "followup_answer": "回答",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
        {
            "triplet_id": "tg_001",
            "question_layer": "A",
            "expert_answer": "回答A（重复）",
            "followup_asked": "",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "回答B",
            "followup_asked": "",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
        {
            "triplet_id": "tg_001",
            "question_layer": "C",
            "expert_answer": "回答C",
            "followup_asked": "",
            "followup_answer": "",
            "signals_observed": [],
            "probe_suggestion": "",
            "probe_adopted": None,
        },
    ]
    errors = iss.check_p5_quality_gate(records)
    assert any("重复" in e for e in errors), f"Expected duplicate-layer error, got: {errors}"


# ---------------------------------------------------------------------------
# Camera assistance schema tests
# ---------------------------------------------------------------------------

def _camera_record(**overrides):
    record = {
        "triplet_id": "tg_001",
        "target_variable": "lv_001",
        "question_layer": "A",
        "question_text": "题目",
        "expert_answer": "有效回答",
        "followup_asked": "这是怎么想到的？",
        "followup_answer": "因为我先看边界条件",
        "signals_observed": ["hesitated"],
        "probe_suggestion": "你在衡量什么？",
        "probe_adopted": True,
        "probe_modified_text": None,
        "operator_notes": "",
        "answer_input_mode": "manual_cli",
        "camera_assist_enabled": True,
        "camera_suggestions": [
            {
                "signal": "hesitated",
                "confidence": "medium",
                "reason": "专家回答时出现明显停顿，可能正在权衡边界条件",
                "suggested_probe": "你在衡量什么？",
                "accepted": True,
                "final_probe": "你在衡量什么？",
            }
        ],
    }
    record.update(overrides)
    return record


def _complete_camera_records(record):
    records = []
    for layer in ("A", "B", "C"):
        item = dict(record)
        item["question_layer"] = layer
        item["question_text"] = f"{layer}题目"
        if layer != "A":
            item["followup_asked"] = ""
            item["followup_answer"] = ""
            item["signals_observed"] = []
            item["probe_suggestion"] = ""
            item["probe_adopted"] = None
            item["camera_suggestions"] = []
        records.append(item)
    return records


def test_build_record_supports_camera_fields():
    record = iss.build_interview_record(
        triplet_id="tg_001",
        target_variable="lv_001",
        layer="A",
        question_text="题目",
        expert_answer="回答",
        followup_asked="追问",
        followup_answer="追问回答",
        signals_observed=["hesitated"],
        probe_suggestion="你在衡量什么？",
        probe_adopted=True,
        probe_modified_text=None,
        operator_notes="",
        answer_input_mode="manual_cli",
        camera_assist_enabled=True,
        camera_suggestions=[
            iss.build_camera_suggestion(
                signal="hesitated",
                confidence="medium",
                reason="专家回答时出现明显停顿",
                suggested_probe="你在衡量什么？",
                accepted=True,
                final_probe="你在衡量什么？",
            )
        ],
    )
    assert record["answer_input_mode"] == "manual_cli"
    assert record["camera_assist_enabled"] is True
    assert record["camera_suggestions"][0]["signal"] == "hesitated"


def test_p5_quality_gate_accepts_valid_camera_suggestions():
    errors = iss.check_p5_quality_gate(_complete_camera_records(_camera_record()))
    assert errors == []


def test_p5_quality_gate_rejects_invalid_camera_signal():
    bad = _camera_record(camera_suggestions=[
        {
            "signal": "angry",
            "confidence": "medium",
            "reason": "情绪标签不能直接作为访谈信号",
            "suggested_probe": "你在衡量什么？",
            "accepted": False,
            "final_probe": "",
        }
    ])
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("camera_suggestions[0].signal" in e for e in errors)


def test_p5_quality_gate_rejects_invalid_camera_confidence():
    bad = _camera_record(camera_suggestions=[
        {
            "signal": "hesitated",
            "confidence": "very_high",
            "reason": "置信度枚举非法",
            "suggested_probe": "你在衡量什么？",
            "accepted": False,
            "final_probe": "",
        }
    ])
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("camera_suggestions[0].confidence" in e for e in errors)


def test_p5_quality_gate_requires_accepted_signal_in_observed_signals():
    bad = _camera_record(signals_observed=[], camera_suggestions=[
        {
            "signal": "hesitated",
            "confidence": "medium",
            "reason": "被采纳后必须进入 signals_observed",
            "suggested_probe": "你在衡量什么？",
            "accepted": True,
            "final_probe": "你在衡量什么？",
        }
    ])
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("accepted camera signal" in e for e in errors)


def test_p5_quality_gate_rejects_frame_paths_in_transcript():
    bad = _camera_record(camera_suggestions=[
        {
            "signal": "hesitated",
            "confidence": "medium",
            "reason": "frame_path=/tmp/expert-skill-camera/sess/frame-001.jpg",
            "suggested_probe": "你在衡量什么？",
            "accepted": True,
            "final_probe": "你在衡量什么？",
        }
    ])
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("must not contain frame paths" in e for e in errors)


def test_p5_quality_gate_allows_png_format_mentioned_in_expert_answer():
    record = _camera_record(expert_answer="导出 .png 格式用于验收")
    errors = iss.check_p5_quality_gate(_complete_camera_records(record))
    assert errors == []


def test_p5_quality_gate_rejects_invalid_answer_input_mode():
    bad = _camera_record(answer_input_mode="voice_upload")
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("answer_input_mode" in e for e in errors)


def test_p5_quality_gate_accepts_streaming_text_answer_input_mode():
    record = _camera_record(answer_input_mode="streaming_text")
    errors = iss.check_p5_quality_gate(_complete_camera_records(record))
    assert errors == []


def test_p5_quality_gate_rejects_non_list_camera_suggestions():
    bad = _camera_record(camera_suggestions={"signal": "hesitated"})
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("camera_suggestions must be list" in e for e in errors)


def test_p5_quality_gate_rejects_non_dict_camera_suggestion_entries():
    bad = _camera_record(camera_suggestions=["hesitated"])
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("camera_suggestions[0] must be dict" in e for e in errors)


def test_p5_quality_gate_rejects_non_string_suggested_probe():
    bad = _camera_record(camera_suggestions=[
        {
            "signal": "hesitated",
            "confidence": "medium",
            "reason": "建议追问必须是字符串",
            "suggested_probe": ["你在衡量什么？"],
            "accepted": False,
            "final_probe": "",
        }
    ])
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("camera_suggestions[0].suggested_probe" in e for e in errors)


@pytest.mark.parametrize(
    "frame_reference",
    [
        "/tmp/expert-skill-camera",
        "/tmp/foo/frame-001.jpg",
        "C:\\tmp\\frame.png",
        "tmp/frame.webp",
        "sess/frame-001.jpeg",
    ],
)
def test_p5_quality_gate_rejects_camera_frame_reference_paths(frame_reference):
    bad = _camera_record(camera_suggestions=[
        {
            "signal": "hesitated",
            "confidence": "medium",
            "reason": f"contains forbidden frame reference {frame_reference}",
            "suggested_probe": "你在衡量什么？",
            "accepted": True,
            "final_probe": "你在衡量什么？",
        }
    ])
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("must not contain frame paths" in e for e in errors)


def test_p5_quality_gate_rejects_nested_frame_path_key():
    bad = _camera_record(camera_suggestions=[
        {
            "signal": "hesitated",
            "confidence": "medium",
            "reason": "nested metadata must not carry frame references",
            "suggested_probe": "你在衡量什么？",
            "accepted": True,
            "final_probe": "你在衡量什么？",
            "evidence": {"frame_path": "redacted"},
        }
    ])
    errors = iss.check_p5_quality_gate(_complete_camera_records(bad))
    assert any("must not contain frame paths" in e for e in errors)


def test_transcript_md_renders_camera_suggestions_without_frame_paths():
    record = iss.build_interview_record(
        triplet_id="tg_001",
        target_variable="lv_001",
        layer="A",
        question_text="A题目",
        expert_answer="回答A",
        followup_asked="你在衡量什么？",
        followup_answer="我在看边界条件",
        signals_observed=["hesitated"],
        probe_suggestion="你在衡量什么？",
        probe_adopted=True,
        probe_modified_text=None,
        operator_notes="",
        answer_input_mode="manual_cli",
        camera_assist_enabled=True,
        camera_suggestions=[
            iss.build_camera_suggestion(
                signal="hesitated",
                confidence="medium",
                reason="回答前有明显停顿",
                suggested_probe="你在衡量什么？",
                accepted=True,
                final_probe="你在衡量什么？",
            )
        ],
    )
    md = iss.generate_transcript_md([record], [SAMPLE_GROUP])
    assert "**摄像头辅助建议**" in md
    assert "hesitated" in md
    assert "medium" in md
    assert "回答前有明显停顿" in md
    assert "建议追问：你在衡量什么？" in md
    assert "已采纳" in md
    assert "实际追问：你在衡量什么？" in md
    assert "- [medium] hesitated：回答前有明显停顿；建议追问：你在衡量什么？；已采纳；实际追问：你在衡量什么？" in md
    assert ".jpg" not in md
    assert "frame_path" not in md


def test_transcript_md_redacts_camera_suggestion_frame_references():
    record = iss.build_interview_record(
        triplet_id="tg_001",
        target_variable="lv_001",
        layer="A",
        question_text="A题目",
        expert_answer="回答A",
        followup_asked="你在衡量什么？",
        followup_answer="我在看边界条件",
        signals_observed=["hesitated"],
        probe_suggestion="你在衡量什么？",
        probe_adopted=True,
        probe_modified_text=None,
        operator_notes="",
        answer_input_mode="manual_cli",
        camera_assist_enabled=True,
        camera_suggestions=[
            iss.build_camera_suggestion(
                signal="hesitated",
                confidence="medium",
                reason="frame_path=/tmp/expert-skill-camera/sess/frame-001.jpg",
                suggested_probe="参考 /tmp/expert-skill-camera/sess/frame-001.jpg 后追问",
                accepted=True,
                final_probe="查看 sess/frame-001.jpg 后实际追问",
            )
        ],
    )
    md = iss.generate_transcript_md([record], [SAMPLE_GROUP])
    assert "已移除临时帧引用" in md
    assert ".jpg" not in md
    assert "frame_path" not in md
    assert "/tmp/expert-skill-camera" not in md


def test_transcript_md_redacts_punctuated_camera_frame_references():
    record = iss.build_interview_record(
        triplet_id="tg_001",
        target_variable="lv_001",
        layer="A",
        question_text="A题目",
        expert_answer="回答A",
        followup_asked="你在衡量什么？",
        followup_answer="我在看边界条件",
        signals_observed=["hesitated"],
        probe_suggestion="你在衡量什么？",
        probe_adopted=True,
        probe_modified_text=None,
        operator_notes="",
        answer_input_mode="manual_cli",
        camera_assist_enabled=True,
        camera_suggestions=[
            iss.build_camera_suggestion(
                signal="hesitated",
                confidence="medium",
                reason="查看 sess/frame-001.jpg，后追问；查看 /tmp/foo/frame-001.jpg, then",
                suggested_probe="你在衡量什么？",
                accepted=True,
                final_probe="你在衡量什么？",
            )
        ],
    )
    md = iss.generate_transcript_md([record], [SAMPLE_GROUP])
    assert "已移除临时帧引用" in md
    assert "sess/frame-001.jpg" not in md
    assert "/tmp/foo/frame-001.jpg" not in md
    assert ".jpg" not in md
    assert "frame_path" not in md


def test_transcript_md_redacts_frame_references_with_common_delimiters():
    record = iss.build_interview_record(
        triplet_id="tg_001",
        target_variable="lv_001",
        layer="A",
        question_text="A题目",
        expert_answer="回答A",
        followup_asked="你在衡量什么？",
        followup_answer="我在看边界条件",
        signals_observed=["hesitated"],
        probe_suggestion="你在衡量什么？",
        probe_adopted=True,
        probe_modified_text=None,
        operator_notes="",
        answer_input_mode="manual_cli",
        camera_assist_enabled=True,
        camera_suggestions=[
            iss.build_camera_suggestion(
                signal="hesitated",
                confidence="medium",
                reason=(
                    "sess/frame-001.jpg、后追问 "
                    "sess/frame-001.jpg！后追问 "
                    "sess/frame-001.jpg? then "
                    "`sess/frame-001.jpg` "
                    "<sess/frame-001.jpg>"
                ),
                suggested_probe="你在衡量什么？",
                accepted=True,
                final_probe="你在衡量什么？",
            )
        ],
    )
    md = iss.generate_transcript_md([record], [SAMPLE_GROUP])
    assert "已移除临时帧引用" in md
    assert "sess/frame-001.jpg" not in md
    assert ".jpg" not in md
    assert "frame_path" not in md


def test_camera_assist_default_off_records_no_camera_suggestions(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base)],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    transcript = json.loads((discovery / "interview_transcript.json").read_text(encoding="utf-8"))
    assert all(record.get("camera_suggestions") in (None, []) for record in transcript)
    assert all(record.get("camera_assist_enabled") in (None, False) for record in transcript)
    assert all(record.get("answer_input_mode", "manual_cli") == "manual_cli" for record in transcript)


def test_camera_assist_cli_records_enabled_fields_without_worker(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=[
            "--slug", "expert_a",
            "--base-dir", str(base),
            "--camera-assist",
            "--disable-camera-worker-for-test",
        ],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    transcript = json.loads((discovery / "interview_transcript.json").read_text(encoding="utf-8"))
    assert all(record["camera_assist_enabled"] is True for record in transcript)
    assert all(record["camera_suggestions"] == [] for record in transcript)


def test_camera_assist_main_uses_factory_worker_suggestions(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)
    factory_calls = []

    class FakeWorker:
        def __init__(self):
            self.started = []

        def start_answer(self, triplet_id, layer):
            self.started.append((triplet_id, layer))

        def stop_answer(self):
            return [
                iss.build_camera_suggestion(
                    signal="hesitated",
                    confidence="medium",
                    reason="回答时有明显停顿",
                    suggested_probe="你在衡量什么？",
                )
            ]

    fake_worker = FakeWorker()

    def factory(args, print_fn):
        factory_calls.append((args.camera_frame_interval, print_fn))
        return fake_worker

    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base), "--camera-assist"],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
        camera_worker_factory=factory,
    )

    assert ret == 0
    assert factory_calls
    assert fake_worker.started[0] == ("tg_001", "A")
    transcript = json.loads((discovery / "interview_transcript.json").read_text(encoding="utf-8"))
    assert all(record["camera_assist_enabled"] is True for record in transcript)
    assert all(record["camera_suggestions"][0]["signal"] == "hesitated" for record in transcript)


def test_disable_camera_worker_for_test_skips_factory_but_records_enabled_fields(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)
    factory_calls = []

    def factory(args, print_fn):
        factory_calls.append((args, print_fn))
        raise AssertionError("factory should not be called")

    ret = iss.main(
        argv=[
            "--slug", "expert_a",
            "--base-dir", str(base),
            "--camera-assist",
            "--disable-camera-worker-for-test",
        ],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
        camera_worker_factory=factory,
    )

    assert ret == 0
    assert factory_calls == []
    transcript = json.loads((discovery / "interview_transcript.json").read_text(encoding="utf-8"))
    assert all(record["camera_assist_enabled"] is True for record in transcript)
    assert all(record["camera_suggestions"] == [] for record in transcript)


def test_stream_answer_input_sets_streaming_text_mode(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=[
            "--slug", "expert_a",
            "--base-dir", str(base),
            "--answer-input", "stream",
        ],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    transcript = json.loads((discovery / "interview_transcript.json").read_text(encoding="utf-8"))
    assert all(record["answer_input_mode"] == "streaming_text" for record in transcript)


def test_build_camera_frame_event_contains_response_path_without_persisting_to_transcript(tmp_path):
    event = iss.build_camera_frame_event(
        session_id="sess-001",
        frame_id="frame-001",
        frame_path=tmp_path / "frame-001.jpg",
        response_path=tmp_path / "responses" / "frame-001.json",
        triplet_id="tg_001",
        layer="A",
    )
    assert event["event"] == "camera_frame_ready"
    assert event["triplet_id"] == "tg_001"
    assert event["question_layer"] == "A"
    assert str(event["frame_path"]).endswith("frame-001.jpg")
    assert str(event["response_path"]).endswith("frame-001.json")
    assert "Return JSON only" in event["instruction"]


def test_parse_camera_response_accepts_json_array(tmp_path):
    response_path = tmp_path / "frame-001.json"
    response_path.write_text(
        json.dumps([
            {
                "signal": "hesitated",
                "confidence": "medium",
                "reason": "回答时有明显停顿",
                "suggested_probe": "你在衡量什么？",
            }
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    suggestions, errors = iss.parse_camera_response_file(response_path)
    assert errors == []
    assert suggestions[0]["signal"] == "hesitated"
    assert suggestions[0]["accepted"] is False


def test_parse_camera_response_rejects_invalid_json(tmp_path):
    response_path = tmp_path / "frame-001.json"
    response_path.write_text("not json", encoding="utf-8")
    suggestions, errors = iss.parse_camera_response_file(response_path)
    assert suggestions == []
    assert any("invalid JSON" in e for e in errors)


def test_camera_assist_worker_uses_fake_capture_and_deletes_frame(tmp_path):
    printed = []
    responses = tmp_path / "responses"
    responses.mkdir()

    def fake_capture(path):
        Path(path).write_bytes(b"fake image")
        frame_id = Path(path).stem
        (responses / f"{frame_id}.json").write_text(
            json.dumps([
                {
                    "signal": "hesitated",
                    "confidence": "medium",
                    "reason": "回答时有明显停顿",
                    "suggested_probe": "你在衡量什么？",
                }
            ], ensure_ascii=False),
            encoding="utf-8",
        )
        return True, ""

    worker = iss.CameraAssistWorker(
        temp_root=tmp_path,
        frame_interval=0.01,
        analysis_timeout=0.2,
        print_fn=printed.append,
        capture_frame_fn=fake_capture,
        session_id="sess-test",
        response_dir=responses,
    )
    suggestions = worker.capture_once("tg_001", "A")
    assert suggestions[0]["signal"] == "hesitated"
    assert "camera_frame_ready" in "\n".join(printed)
    assert not any(path.suffix == ".jpg" for path in tmp_path.rglob("*"))


def test_camera_assist_worker_captures_during_answer_until_stopped(tmp_path):
    capture_count = {"value": 0}
    responses = tmp_path / "responses"
    responses.mkdir()

    def fake_capture(path):
        capture_count["value"] += 1
        Path(path).write_bytes(b"fake image")
        frame_id = Path(path).stem
        (responses / f"{frame_id}.json").write_text(
            json.dumps([
                {
                    "signal": "hesitated",
                    "confidence": "low",
                    "reason": "回答期间出现短暂停顿",
                    "suggested_probe": "你在衡量什么？",
                }
            ], ensure_ascii=False),
            encoding="utf-8",
        )
        return True, ""

    worker = iss.CameraAssistWorker(
        temp_root=tmp_path,
        frame_interval=0.01,
        analysis_timeout=0.05,
        print_fn=lambda x: None,
        capture_frame_fn=fake_capture,
        session_id="sess-loop",
        response_dir=responses,
    )
    worker.start_answer("tg_001", "A")
    time.sleep(0.04)
    suggestions = worker.stop_answer()
    assert capture_count["value"] >= 2
    assert any(item["signal"] == "hesitated" for item in suggestions)


def test_stop_answer_retains_thread_when_join_times_out_and_clears_completed_thread(tmp_path):
    class FakeThread:
        def __init__(self, alive_after_join):
            self.alive_after_join = alive_after_join
            self.join_calls = []

        def join(self, timeout=None):
            self.join_calls.append(timeout)

        def is_alive(self):
            return self.alive_after_join

    worker = iss.CameraAssistWorker(
        temp_root=tmp_path,
        frame_interval=0.01,
        analysis_timeout=0.05,
        print_fn=lambda x: None,
        capture_frame_fn=lambda path: (False, ""),
        session_id="sess-stop",
    )
    alive_thread = FakeThread(alive_after_join=True)
    worker._thread = alive_thread
    worker._suggestions = [iss.build_camera_suggestion("hesitated", "low", "r", "p")]

    suggestions = worker.stop_answer()

    assert suggestions[0]["signal"] == "hesitated"
    assert worker._thread is alive_thread
    assert alive_thread.join_calls

    completed_thread = FakeThread(alive_after_join=False)
    worker._thread = completed_thread

    worker.stop_answer()

    assert worker._thread is None
    assert completed_thread.join_calls


def test_camera_assist_worker_does_not_return_late_previous_layer_suggestions(tmp_path):
    responses = tmp_path / "responses"
    responses.mkdir()
    capture_started = threading.Event()
    release_late_capture = threading.Event()

    def fake_capture(path):
        Path(path).write_bytes(b"fake image")
        capture_started.set()
        release_late_capture.wait(timeout=2.0)
        frame_id = Path(path).stem
        (responses / f"{frame_id}.json").write_text(
            json.dumps([
                {
                    "signal": "hesitated",
                    "confidence": "medium",
                    "reason": "late previous layer",
                    "suggested_probe": "你在衡量什么？",
                }
            ], ensure_ascii=False),
            encoding="utf-8",
        )
        return True, ""

    worker = iss.CameraAssistWorker(
        temp_root=tmp_path,
        frame_interval=0.01,
        analysis_timeout=0.01,
        print_fn=lambda x: None,
        capture_frame_fn=fake_capture,
        session_id="sess-late",
        response_dir=responses,
    )

    worker.start_answer("tg_001", "A")
    assert capture_started.wait(timeout=1.0)
    worker.stop_answer()

    worker.start_answer("tg_001", "B")
    release_late_capture.set()
    time.sleep(0.05)
    suggestions = worker.stop_answer()

    assert all(item["reason"] != "late previous layer" for item in suggestions)
