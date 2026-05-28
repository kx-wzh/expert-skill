#!/usr/bin/env python3
"""Tests for tools/interview_analyzer.py"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent))
import interview_analyzer as ia

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

VALID_FINDING_HIGH = {
    "type": "变量",
    "content": "高置信度发现",
    "confidence": "high",
    "evidence": {
        "triplet_id": "tg_001",
        "layer": "B",
        "expert_quote": "专家原话高",
        "confidence_reason": "明确表述",
    },
}

VALID_FINDING_MEDIUM = {
    "type": "优先级",
    "content": "中置信度发现",
    "confidence": "medium",
    "evidence": {
        "triplet_id": "tg_001",
        "layer": "C",
        "expert_quote": "专家原话中",
        "confidence_reason": "间接推断",
    },
}

VALID_FINDING_LOW = {
    "type": "边界条件",
    "content": "低置信度发现",
    "confidence": "low",
    "evidence": {
        "triplet_id": "tg_002",
        "layer": "B",
        "expert_quote": "专家原话低",
        "confidence_reason": "单一证据",
    },
}

VALID_ANALYSIS_001 = {
    "triplet_id": "tg_001",
    "baseline_rule": "基准规则",
    "awareness_state": "semi_latent",
    "priority_topology": {"winner": "规则A", "loser": "规则B", "condition": "条件"},
    "confidence": "medium",
    "latent_findings": [VALID_FINDING_HIGH],
    "invalidated_candidates": [],
}

VALID_CROSS_ANALYSIS = {
    "confirmed_variables": [],
    "inconsistent_variables": [],
    "priority_topology": [],
    "boundary_map": [],
}

VALID_REPORT_SECTIONS = {
    "discovered_variables": [],
    "priority_topology": [],
    "boundary_map": [],
    "suspected_bias": [],
    "open_questions": [],
}

VALID_RESULT = {
    "triplet_analyses": [VALID_ANALYSIS_001],
    "cross_analysis": VALID_CROSS_ANALYSIS,
    "report_sections": VALID_REPORT_SECTIONS,
}

SAMPLE_TRANSCRIPT = [
    {
        "triplet_id": "tg_001",
        "question_layer": "A",
        "expert_answer": "回答A",
        "signals_observed": [],
    },
    {
        "triplet_id": "tg_001",
        "question_layer": "B",
        "expert_answer": "回答B",
        "signals_observed": [],
    },
    {
        "triplet_id": "tg_001",
        "question_layer": "C",
        "expert_answer": "回答C",
        "signals_observed": [],
    },
]

SAMPLE_GROUPS = [
    {
        "id": "tg_001",
        "target_variable": "lv_001",
        "question_A": {"text": "A题目"},
        "question_B": {"text": "B题目"},
        "question_C": {"text": "C题目"},
    }
]

MINIMAL_TEMPLATE = (
    "专家：{name}（{expertise_type}）\n"
    "三联体：{triplet_groups_json}\n"
    "记录：{interview_transcript_json}\n"
)


def setup_discovery_dir(tmp_path, slug="expert_a", meta=None,
                        transcript=None, groups=None, profile=None):
    base = tmp_path / "skills" / "expert"
    discovery = base / slug / "discovery"
    discovery.mkdir(parents=True)
    t = transcript if transcript is not None else SAMPLE_TRANSCRIPT
    g = groups if groups is not None else SAMPLE_GROUPS
    (discovery / "interview_transcript.json").write_text(
        json.dumps(t, ensure_ascii=False), encoding="utf-8"
    )
    (discovery / "triplet_groups.json").write_text(
        json.dumps(g, ensure_ascii=False), encoding="utf-8"
    )
    if profile is not None:
        (discovery / "expert_profile.json").write_text(
            json.dumps(profile, ensure_ascii=False), encoding="utf-8"
        )
    if meta is not None:
        (base / slug / "meta.json").write_text(
            json.dumps(meta, ensure_ascii=False), encoding="utf-8"
        )
    return base, discovery


def write_output_file(tmp_path, result, filename="output.json"):
    p = tmp_path / filename
    p.write_text(json.dumps(result, ensure_ascii=False), encoding="utf-8")
    return p


# ---------------------------------------------------------------------------
# 1. test_prompt_assembly_no_leftover_placeholders
# ---------------------------------------------------------------------------

def test_prompt_assembly_no_leftover_placeholders():
    prompt = ia.assemble_prompt(
        MINIMAL_TEMPLATE,
        name="张三",
        expertise_type="故障排查专家",
        triplet_groups_json="[]",
        interview_transcript_json="[]",
    )
    assert "{name}" not in prompt
    assert "{expertise_type}" not in prompt
    assert "{triplet_groups_json}" not in prompt
    assert "{interview_transcript_json}" not in prompt
    assert "张三" in prompt
    assert "故障排查专家" in prompt


# ---------------------------------------------------------------------------
# 2. test_parse_output_saves_latent_findings_json
# ---------------------------------------------------------------------------

def test_parse_output_saves_latent_findings_json(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path)
    out_file = write_output_file(tmp_path, VALID_RESULT)
    orig = ia.PROMPT_TEMPLATE_PATH
    try:
        tpl = tmp_path / "tpl.md"
        tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
        ia.PROMPT_TEMPLATE_PATH = tpl
        ret = ia.main([
            "--slug", "expert_a", "--base-dir", str(base),
            "--parse-output", str(out_file),
        ])
    finally:
        ia.PROMPT_TEMPLATE_PATH = orig
    assert ret == 0
    findings_path = discovery / "latent_findings.json"
    assert findings_path.exists()
    findings = json.loads(findings_path.read_text(encoding="utf-8"))
    assert isinstance(findings, list)
    assert len(findings) == 1
    assert findings[0]["content"] == "高置信度发现"


# ---------------------------------------------------------------------------
# 3. test_p6_gate_requires_baseline_rule
# ---------------------------------------------------------------------------

def test_p6_gate_requires_baseline_rule():
    bad = {**VALID_ANALYSIS_001, "baseline_rule": ""}
    result = {**VALID_RESULT, "triplet_analyses": [bad]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT)
    assert any("baseline_rule" in e for e in errors)


# ---------------------------------------------------------------------------
# 4. test_p6_gate_requires_awareness_state
# ---------------------------------------------------------------------------

def test_p6_gate_requires_awareness_state():
    bad = {**VALID_ANALYSIS_001, "awareness_state": ""}
    result = {**VALID_RESULT, "triplet_analyses": [bad]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT)
    assert any("awareness_state" in e for e in errors)


# ---------------------------------------------------------------------------
# 5. test_p6_gate_requires_priority_topology
# ---------------------------------------------------------------------------

def test_p6_gate_requires_priority_topology():
    bad = {**VALID_ANALYSIS_001, "priority_topology": {}}
    result = {**VALID_RESULT, "triplet_analyses": [bad]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT)
    assert any("priority_topology" in e for e in errors)


# ---------------------------------------------------------------------------
# 6. test_p6_gate_rejects_invalid_awareness_state
# ---------------------------------------------------------------------------

def test_p6_gate_rejects_invalid_awareness_state():
    bad = {**VALID_ANALYSIS_001, "awareness_state": "unknown_state"}
    result = {**VALID_RESULT, "triplet_analyses": [bad]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT)
    assert any("awareness_state" in e for e in errors)


# ---------------------------------------------------------------------------
# 7. test_p6_gate_requires_finding_confidence
# ---------------------------------------------------------------------------

def test_p6_gate_requires_finding_confidence():
    bad_finding = {**VALID_FINDING_HIGH, "confidence": ""}
    bad_analysis = {**VALID_ANALYSIS_001, "latent_findings": [bad_finding]}
    result = {**VALID_RESULT, "triplet_analyses": [bad_analysis]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT)
    assert any("confidence" in e for e in errors)


# ---------------------------------------------------------------------------
# 8. test_p6_gate_requires_finding_expert_quote
# ---------------------------------------------------------------------------

def test_p6_gate_requires_finding_expert_quote():
    bad_ev = {**VALID_FINDING_HIGH["evidence"], "expert_quote": ""}
    bad_finding = {**VALID_FINDING_HIGH, "evidence": bad_ev}
    bad_analysis = {**VALID_ANALYSIS_001, "latent_findings": [bad_finding]}
    result = {**VALID_RESULT, "triplet_analyses": [bad_analysis]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT)
    assert any("expert_quote" in e for e in errors)


# ---------------------------------------------------------------------------
# 9. test_latent_report_md_contains_required_sections
# ---------------------------------------------------------------------------

def test_latent_report_md_contains_required_sections():
    md = ia.generate_latent_report_md(VALID_RESULT)
    assert "## 发现的隐性变量" in md
    assert "## 隐性优先级拓扑" in md
    assert "## 全局边界地图" in md
    assert "## 疑似误判区" in md
    assert "## 未解问题" in md


# ---------------------------------------------------------------------------
# 10. test_latent_report_md_sorted_by_confidence
# ---------------------------------------------------------------------------

def test_latent_report_md_sorted_by_confidence():
    analysis_002 = {
        **VALID_ANALYSIS_001,
        "triplet_id": "tg_002",
        "latent_findings": [VALID_FINDING_LOW],
    }
    result = {
        **VALID_RESULT,
        "triplet_analyses": [
            {**VALID_ANALYSIS_001, "latent_findings": [VALID_FINDING_MEDIUM]},
            analysis_002,
        ],
    }
    # Add a high finding to first analysis
    result["triplet_analyses"][0]["latent_findings"] = [VALID_FINDING_MEDIUM, VALID_FINDING_HIGH]
    md = ia.generate_latent_report_md(result)
    idx_high = md.index("[high]")
    idx_medium = md.index("[medium]")
    idx_low = md.index("[low]")
    assert idx_high < idx_medium < idx_low


# ---------------------------------------------------------------------------
# 11. test_latent_report_md_includes_evidence_citation
# ---------------------------------------------------------------------------

def test_latent_report_md_includes_evidence_citation():
    md = ia.generate_latent_report_md(VALID_RESULT)
    assert "tg_001" in md
    assert "专家原话高" in md


# ---------------------------------------------------------------------------
# 12. test_dry_run_conflicts_with_parse_output
# ---------------------------------------------------------------------------

def test_dry_run_conflicts_with_parse_output(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path)
    ret = ia.main([
        "--slug", "expert_a", "--base-dir", str(base),
        "--dry-run", "--parse-output", "somefile.json",
    ])
    assert ret == 1


# ---------------------------------------------------------------------------
# 13. test_dry_run_does_not_write_files
# ---------------------------------------------------------------------------

def test_dry_run_does_not_write_files(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path)
    orig = ia.PROMPT_TEMPLATE_PATH
    try:
        tpl = tmp_path / "tpl.md"
        tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
        ia.PROMPT_TEMPLATE_PATH = tpl
        ret = ia.main([
            "--slug", "expert_a", "--base-dir", str(base), "--dry-run",
        ])
    finally:
        ia.PROMPT_TEMPLATE_PATH = orig
    assert ret == 0
    assert not (discovery / "interview_analyzer_prompt.md").exists()
    assert not (discovery / "interview_analysis.json").exists()
    assert not (discovery / "latent_report.md").exists()


# ---------------------------------------------------------------------------
# 14. test_parse_output_updates_meta_status
# ---------------------------------------------------------------------------

def test_parse_output_updates_meta_status(tmp_path):
    base, discovery = setup_discovery_dir(
        tmp_path, meta={"discovery": {"status": "interview_in_progress"}}
    )
    out_file = write_output_file(tmp_path, VALID_RESULT)
    orig = ia.PROMPT_TEMPLATE_PATH
    try:
        tpl = tmp_path / "tpl.md"
        tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
        ia.PROMPT_TEMPLATE_PATH = tpl
        ret = ia.main([
            "--slug", "expert_a", "--base-dir", str(base),
            "--parse-output", str(out_file),
        ])
    finally:
        ia.PROMPT_TEMPLATE_PATH = orig
    assert ret == 0
    meta = json.loads((base / "expert_a" / "meta.json").read_text(encoding="utf-8"))
    assert meta["discovery"]["status"] == "analysis_ready"


# ---------------------------------------------------------------------------
# 15. test_validate_triplet_analysis_local_function
# ---------------------------------------------------------------------------

def test_validate_triplet_analysis_local_function():
    # Valid analysis: no errors
    errors = ia.check_triplet_analysis_schema(VALID_ANALYSIS_001)
    assert errors == []

    # Missing required field
    bad = {k: v for k, v in VALID_ANALYSIS_001.items() if k != "baseline_rule"}
    errors = ia.check_triplet_analysis_schema(bad)
    assert any("baseline_rule" in e for e in errors)

    # Function must exist in interview_analyzer module directly
    assert hasattr(ia, "check_triplet_analysis_schema")
    # Must not be imported from discovery_schema (no validate_triplet_analysis there)
    import discovery_schema as ds
    assert not hasattr(ds, "validate_triplet_analysis")


# ---------------------------------------------------------------------------
# 16. test_p6_gate_requires_top_level_confidence
# ---------------------------------------------------------------------------

def test_p6_gate_requires_top_level_confidence():
    bad = {**VALID_ANALYSIS_001, "confidence": ""}
    result = {**VALID_RESULT, "triplet_analyses": [bad]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT)
    assert any("confidence" in e for e in errors)


# ---------------------------------------------------------------------------
# 17. test_p6_gate_rejects_invalid_confidence
# ---------------------------------------------------------------------------

def test_p6_gate_rejects_invalid_confidence():
    bad = {**VALID_ANALYSIS_001, "confidence": "very_high"}
    result = {**VALID_RESULT, "triplet_analyses": [bad]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT)
    assert any("confidence" in e for e in errors)


# ---------------------------------------------------------------------------
# 18. test_p6_gate_fails_boundary_invented_missing_from_boundary_map
# ---------------------------------------------------------------------------

def test_p6_gate_fails_boundary_invented_missing_from_boundary_map():
    transcript_with_bi = SAMPLE_TRANSCRIPT + [
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "要看情况...",
            "signals_observed": ["boundary_invented"],
        }
    ]
    # cross_analysis.boundary_map is empty → tg_001 not covered → must be an error
    errors, _ = ia.check_p6_quality_gate(VALID_RESULT, transcript_with_bi)
    assert any("boundary_invented" in e or "boundary_map" in e for e in errors)
    assert any("tg_001" in e for e in errors)


# ---------------------------------------------------------------------------
# 18b. test_p6_gate_passes_boundary_invented_covered_by_boundary_map
# ---------------------------------------------------------------------------

def test_p6_gate_passes_boundary_invented_covered_by_boundary_map():
    transcript_with_bi = SAMPLE_TRANSCRIPT + [
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "要看情况...",
            "signals_observed": ["boundary_invented"],
        }
    ]
    result_with_bmap = {
        **VALID_RESULT,
        "cross_analysis": {
            **VALID_CROSS_ANALYSIS,
            "boundary_map": [{"triplet_id": "tg_001", "boundary": "外部信号边界"}],
        },
    }
    errors, _ = ia.check_p6_quality_gate(result_with_bmap, transcript_with_bi)
    boundary_errors = [e for e in errors if "boundary" in e.lower() or "tg_001" in e]
    assert boundary_errors == []


# ---------------------------------------------------------------------------
# 19. test_invalidated_candidates_preserved
# ---------------------------------------------------------------------------

def test_invalidated_candidates_preserved(tmp_path):
    analysis_with_inv = {
        **VALID_ANALYSIS_001,
        "invalidated_candidates": ["lv_003", "lv_005"],
    }
    result = {**VALID_RESULT, "triplet_analyses": [analysis_with_inv]}
    base, discovery = setup_discovery_dir(tmp_path)
    out_file = write_output_file(tmp_path, result)
    orig = ia.PROMPT_TEMPLATE_PATH
    try:
        tpl = tmp_path / "tpl.md"
        tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
        ia.PROMPT_TEMPLATE_PATH = tpl
        ret = ia.main([
            "--slug", "expert_a", "--base-dir", str(base),
            "--parse-output", str(out_file),
        ])
    finally:
        ia.PROMPT_TEMPLATE_PATH = orig
    assert ret == 0
    saved = json.loads(
        (discovery / "interview_analysis.json").read_text(encoding="utf-8")
    )
    inv = saved["triplet_analyses"][0]["invalidated_candidates"]
    assert "lv_003" in inv
    assert "lv_005" in inv


# ---------------------------------------------------------------------------
# 20. test_result_requires_report_sections
# ---------------------------------------------------------------------------

def test_result_requires_report_sections():
    result_no_sections = {
        "triplet_analyses": [VALID_ANALYSIS_001],
        "cross_analysis": VALID_CROSS_ANALYSIS,
        # report_sections missing entirely
    }
    errors, _ = ia.check_p6_quality_gate(result_no_sections, SAMPLE_TRANSCRIPT)
    assert any("report_sections" in e for e in errors)

    # Missing sub-key
    result_partial = {
        "triplet_analyses": [VALID_ANALYSIS_001],
        "cross_analysis": VALID_CROSS_ANALYSIS,
        "report_sections": {k: v for k, v in VALID_REPORT_SECTIONS.items() if k != "open_questions"},
    }
    errors2, _ = ia.check_p6_quality_gate(result_partial, SAMPLE_TRANSCRIPT)
    assert any("open_questions" in e for e in errors2)


# ---------------------------------------------------------------------------
# 21. test_p6_gate_requires_analysis_for_each_triplet
# ---------------------------------------------------------------------------

def test_p6_gate_requires_analysis_for_each_triplet():
    transcript = SAMPLE_TRANSCRIPT + [
        {
            "triplet_id": "tg_002",
            "question_layer": "A",
            "expert_answer": "回答A2",
            "signals_observed": [],
        },
        {
            "triplet_id": "tg_002",
            "question_layer": "B",
            "expert_answer": "回答B2",
            "signals_observed": [],
        },
        {
            "triplet_id": "tg_002",
            "question_layer": "C",
            "expert_answer": "回答C2",
            "signals_observed": [],
        },
    ]
    groups = SAMPLE_GROUPS + [
        {
            "id": "tg_002",
            "target_variable": "lv_002",
            "question_A": {"text": "A2题目"},
            "question_B": {"text": "B2题目"},
            "question_C": {"text": "C2题目"},
        }
    ]

    errors, _ = ia.check_p6_quality_gate(VALID_RESULT, transcript, groups)
    assert any("tg_002" in e and "缺少分析" in e for e in errors)


# ---------------------------------------------------------------------------
# 22. test_parse_output_saves_interview_analysis_json
# ---------------------------------------------------------------------------

def test_parse_output_saves_interview_analysis_json(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path)
    out_file = write_output_file(tmp_path, VALID_RESULT)
    orig = ia.PROMPT_TEMPLATE_PATH
    try:
        tpl = tmp_path / "tpl.md"
        tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
        ia.PROMPT_TEMPLATE_PATH = tpl
        ret = ia.main([
            "--slug", "expert_a", "--base-dir", str(base),
            "--parse-output", str(out_file),
        ])
    finally:
        ia.PROMPT_TEMPLATE_PATH = orig
    assert ret == 0
    analysis_path = discovery / "interview_analysis.json"
    assert analysis_path.exists()
    saved = json.loads(analysis_path.read_text(encoding="utf-8"))
    assert "triplet_analyses" in saved
    assert "cross_analysis" in saved
    assert "report_sections" in saved


# ---------------------------------------------------------------------------
# 22. test_parse_output_updates_analysis_completion_meta_fields
# ---------------------------------------------------------------------------

def test_parse_output_updates_analysis_completion_meta_fields(tmp_path):
    base, discovery = setup_discovery_dir(
        tmp_path, meta={"discovery": {"status": "interview_in_progress"}}
    )
    out_file = write_output_file(tmp_path, VALID_RESULT)
    orig = ia.PROMPT_TEMPLATE_PATH
    try:
        tpl = tmp_path / "tpl.md"
        tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
        ia.PROMPT_TEMPLATE_PATH = tpl
        ret = ia.main([
            "--slug", "expert_a", "--base-dir", str(base),
            "--parse-output", str(out_file),
        ])
    finally:
        ia.PROMPT_TEMPLATE_PATH = orig
    assert ret == 0
    meta = json.loads((base / "expert_a" / "meta.json").read_text(encoding="utf-8"))
    d = meta["discovery"]
    assert d["analysis_completed"] is True
    assert d["latent_finding_count"] == 1  # VALID_RESULT has 1 finding
    assert d["report_generated"] is True


# ---------------------------------------------------------------------------
# 23. test_analysis_parse_sets_analysis_ready_status
# ---------------------------------------------------------------------------

def test_analysis_parse_sets_analysis_ready_status(tmp_path):
    # P6 parse-output must set status to "analysis_ready" (not interview_completed)
    base, discovery = setup_discovery_dir(
        tmp_path, meta={"discovery": {"status": "interview_completed"}}
    )
    out_file = write_output_file(tmp_path, VALID_RESULT)
    orig = ia.PROMPT_TEMPLATE_PATH
    try:
        tpl = tmp_path / "tpl.md"
        tpl.write_text(MINIMAL_TEMPLATE, encoding="utf-8")
        ia.PROMPT_TEMPLATE_PATH = tpl
        ret = ia.main([
            "--slug", "expert_a", "--base-dir", str(base),
            "--parse-output", str(out_file),
        ])
    finally:
        ia.PROMPT_TEMPLATE_PATH = orig
    assert ret == 0
    meta = json.loads((base / "expert_a" / "meta.json").read_text(encoding="utf-8"))
    assert meta["discovery"]["status"] == "analysis_ready"


def test_p6_gate_rejects_camera_only_latent_finding_evidence():
    camera_only_finding = {
        "type": "变量",
        "content": "仅由摄像头建议推断出的发现",
        "confidence": "medium",
        "evidence": {
            "triplet_id": "tg_001",
            "layer": "B",
            "expert_quote": "camera_suggestion: hesitated",
            "confidence_reason": "Only camera_suggestions indicated hesitation",
        },
    }
    analysis = {**VALID_ANALYSIS_001, "latent_findings": [camera_only_finding]}
    result = {**VALID_RESULT, "triplet_analyses": [analysis]}
    transcript = [
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "我还没有明确答案",
            "signals_observed": [],
            "camera_suggestions": [
                {
                    "signal": "hesitated",
                    "confidence": "medium",
                    "reason": "回答时有明显停顿",
                    "suggested_probe": "你在衡量什么？",
                    "accepted": False,
                    "final_probe": "",
                }
            ],
        }
    ]
    errors, _ = ia.check_p6_quality_gate(result, transcript, SAMPLE_GROUPS)
    assert any("camera-only evidence" in e for e in errors)


@pytest.mark.parametrize(
    "expert_quote",
    [
        "camera-only evidence",
        "仅凭摄像头判断",
    ],
)
def test_p6_gate_rejects_camera_only_markers_in_expert_quote(expert_quote):
    camera_only_finding = {
        "type": "变量",
        "content": "仅由摄像头建议推断出的发现",
        "confidence": "medium",
        "evidence": {
            "triplet_id": "tg_001",
            "layer": "B",
            "expert_quote": expert_quote,
            "confidence_reason": "引用不是专家原话",
        },
    }
    analysis = {**VALID_ANALYSIS_001, "latent_findings": [camera_only_finding]}
    result = {**VALID_RESULT, "triplet_analyses": [analysis]}
    errors, _ = ia.check_p6_quality_gate(result, SAMPLE_TRANSCRIPT, SAMPLE_GROUPS)
    assert any("camera-only evidence" in e for e in errors)


def test_p6_gate_rejects_camera_suggestion_reason_copied_as_expert_quote():
    camera_reason = "回答时有明显停顿"
    camera_only_finding = {
        "type": "变量",
        "content": "仅由摄像头建议推断出的发现",
        "confidence": "medium",
        "evidence": {
            "triplet_id": "tg_001",
            "layer": "B",
            "expert_quote": camera_reason,
            "confidence_reason": "引用不是专家原话",
        },
    }
    analysis = {**VALID_ANALYSIS_001, "latent_findings": [camera_only_finding]}
    result = {**VALID_RESULT, "triplet_analyses": [analysis]}
    transcript = [
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "我还没有明确答案",
            "followup_answer": "",
            "signals_observed": [],
            "camera_suggestions": [
                {
                    "signal": "hesitated",
                    "confidence": "medium",
                    "reason": camera_reason,
                    "suggested_probe": "你在衡量什么？",
                    "accepted": False,
                    "final_probe": "",
                }
            ],
        }
    ]
    errors, _ = ia.check_p6_quality_gate(result, transcript, SAMPLE_GROUPS)
    assert any("camera-only evidence" in e for e in errors)


def test_p6_gate_rejects_camera_only_quote_even_when_layer_is_wrong():
    camera_reason = "回答时有明显停顿"
    camera_only_finding = {
        "type": "变量",
        "content": "仅由摄像头建议推断出的发现",
        "confidence": "medium",
        "evidence": {
            "triplet_id": "tg_001",
            "layer": "A",
            "expert_quote": camera_reason,
            "confidence_reason": "引用不是专家原话",
        },
    }
    analysis = {**VALID_ANALYSIS_001, "latent_findings": [camera_only_finding]}
    result = {**VALID_RESULT, "triplet_analyses": [analysis]}
    transcript = [
        {
            "triplet_id": "tg_001",
            "question_layer": "A",
            "expert_answer": "我先按常规判断",
            "followup_answer": "",
            "signals_observed": [],
        },
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "我还没有明确答案",
            "followup_answer": "",
            "signals_observed": [],
            "camera_suggestions": [
                {
                    "signal": "hesitated",
                    "confidence": "medium",
                    "reason": camera_reason,
                    "suggested_probe": "你在衡量什么？",
                    "accepted": False,
                    "final_probe": "",
                }
            ],
        },
    ]
    errors, _ = ia.check_p6_quality_gate(result, transcript, SAMPLE_GROUPS)
    assert any("camera-only evidence" in e for e in errors)


def test_p6_gate_allows_camera_triggered_finding_with_expert_quote():
    camera_triggered_finding = {
        "type": "变量",
        "content": "专家用边界条件解释了迟疑",
        "confidence": "medium",
        "evidence": {
            "triplet_id": "tg_001",
            "layer": "B",
            "expert_quote": "我在衡量患者最近是否有低血糖，因为这会改变建议",
            "confidence_reason": "camera_suggestions triggered the follow-up, but the finding is grounded in expert_quote",
        },
    }
    analysis = {**VALID_ANALYSIS_001, "latent_findings": [camera_triggered_finding]}
    result = {**VALID_RESULT, "triplet_analyses": [analysis]}
    transcript = [
        {
            "triplet_id": "tg_001",
            "question_layer": "B",
            "expert_answer": "我在衡量患者最近是否有低血糖，因为这会改变建议",
            "signals_observed": ["hesitated"],
            "camera_suggestions": [
                {
                    "signal": "hesitated",
                    "confidence": "medium",
                    "reason": "回答时有明显停顿",
                    "suggested_probe": "你在衡量什么？",
                    "accepted": True,
                    "final_probe": "你在衡量什么？",
                }
            ],
        }
    ]
    errors, _ = ia.check_p6_quality_gate(result, transcript, SAMPLE_GROUPS)
    assert not any("camera-only evidence" in e for e in errors)


def test_interview_analyzer_prompt_mentions_camera_suggestions_are_auxiliary():
    prompt_path = Path(__file__).resolve().parent.parent / "prompts" / "discovery" / "interview_analyzer.md"
    text = prompt_path.read_text(encoding="utf-8")
    assert "camera_suggestions" in text
    assert "不能仅凭摄像头建议生成隐性知识发现" in text
