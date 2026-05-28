# Camera-Assisted Expert Interview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add optional P5 camera assistance so a Hermes-style multimodal agent can inspect temporary interview frames, suggest follow-up signals, and preserve only structured text suggestions in transcript artifacts.

**Architecture:** Keep `expert-skill` as the interview orchestrator and never call a model API from this repo. `interview_session.py` owns answer lifecycle, temporary frame capture, schema validation, and transcript writes; Hermes or another agent reads emitted frame events and writes JSON suggestion responses. P6 can use camera suggestions as auxiliary context, but latent findings still require expert answer or decision evidence.

**Tech Stack:** Python standard library, optional runtime `cv2` import only when camera assist is enabled, pytest, existing P5/P6 JSON transcript artifacts.

---

## File Structure

- Modify `SKILL.md`: document the P5 consent requirement, default-off behavior, and camera-assisted command variants.
- Modify `tools/interview_session.py`: add camera suggestion schema helpers, answer input mode fields, camera CLI flags, background frame event worker, transcript rendering, and P5 quality gate checks.
- Modify `tools/test_interview_session.py`: add TDD coverage for schema validation, transcript rendering, CLI defaults, and fake camera worker integration.
- Modify `prompts/discovery/interview_analyzer.md`: state that camera suggestions are auxiliary prompts and cannot be the sole evidence for latent findings.
- Modify `tools/interview_analyzer.py`: add P6 quality gate checks that reject camera-only evidence.
- Modify `tools/test_interview_analyzer.py`: add tests for camera-only evidence rejection and prompt assembly including camera suggestions.
- Create `tools/test_camera_assist_docs.py`: assert `SKILL.md` documents consent, default-off camera behavior, and command variants.

Do not add a hard dependency file for OpenCV. `cv2` is imported inside the frame capture function only when `--camera-assist` is active; if unavailable, the tool warns and degrades to normal P5 behavior.

---

### Task 1: Document Required Camera Consent In The Skill

**Files:**
- Create: `tools/test_camera_assist_docs.py`
- Modify: `SKILL.md`

- [ ] **Step 1: Write the failing documentation test**

Create `tools/test_camera_assist_docs.py`:

```python
#!/usr/bin/env python3
"""Documentation checks for optional P5 camera assistance."""

from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
SKILL_TEXT = (ROOT / "SKILL.md").read_text(encoding="utf-8")


def test_skill_requires_camera_consent_before_p5():
    assert "摄像头辅助" in SKILL_TEXT
    assert "必须询问用户是否开启摄像头辅助" in SKILL_TEXT
    assert "只有用户明确同意后" in SKILL_TEXT


def test_skill_documents_camera_default_off_and_privacy():
    assert "默认不启用摄像头" in SKILL_TEXT
    assert "临时图片只用于实时分析" in SKILL_TEXT
    assert "不保存到 skill 目录或 transcript" in SKILL_TEXT


def test_skill_documents_camera_assist_commands():
    assert "--camera-assist" in SKILL_TEXT
    assert "--answer-input stream" in SKILL_TEXT
```

- [ ] **Step 2: Run the documentation test and verify it fails**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_camera_assist_docs.py
```

Expected: FAIL because `SKILL.md` does not yet contain the required camera consent text.

- [ ] **Step 3: Add the P5 consent and command section to `SKILL.md`**

In `SKILL.md`, replace the current `### P5：实时访谈记录` section with this text:

````markdown
### P5：实时访谈记录

按 A→B→C 协议进行结构化访谈并记录。

启动 P5 前，agent 必须询问用户是否开启摄像头辅助。摄像头辅助默认不启用。只有用户明确同意后，才能调用本机摄像头。

建议询问文案：

```text
P5 访谈可以选择开启摄像头辅助。开启后，访谈过程中会调用本机摄像头，在专家回答期间定时采集临时帧，并由当前 agent 的多模态模型分析非语言信号，用于提示可能的追问。临时图片只用于实时分析，不保存到 skill 目录或 transcript。是否开启？
```

用户不同意或运行环境没有摄像头时，使用默认命令：

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert
```

用户明确同意后，可以启用摄像头辅助：

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --camera-assist
```

如果 agent 运行时支持 answer event stream，可以使用流式文本输入模式：

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --camera-assist \
  --answer-input stream
```

摄像头辅助只生成候选追问信号。`signals_observed` 仍然表示 agent/访谈员确认后的信号；P6 不能仅凭摄像头建议生成隐性知识发现。

中断后恢复：

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --resume
```

仅完成特定三联体：

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --triplet-id tg_001
```
````

- [ ] **Step 4: Run the documentation test and verify it passes**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_camera_assist_docs.py
```

Expected: PASS.

- [ ] **Step 5: Commit Task 1**

```bash
git add SKILL.md tools/test_camera_assist_docs.py
git commit -m "docs: require consent for camera-assisted interviews"
```

---

### Task 2: Add Camera Suggestion Schema And P5 Quality Gate Checks

**Files:**
- Modify: `tools/interview_session.py`
- Modify: `tools/test_interview_session.py`

- [ ] **Step 1: Write failing schema tests**

Append these tests to `tools/test_interview_session.py`:

```python
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
```

- [ ] **Step 2: Run the new schema tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py -k "camera or build_record_supports"
```

Expected: FAIL because `build_camera_suggestion`, camera fields on `build_interview_record`, and camera validation do not exist.

- [ ] **Step 3: Implement schema constants and helper functions**

In `tools/interview_session.py`, add these constants below `_FUZZY_LANGUAGE_DEFAULT_PROBE`:

```python
_VALID_INTERVIEW_SIGNALS = {
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
```

Add these helper functions before `build_interview_record`:

```python
def build_camera_suggestion(
    signal: str,
    confidence: str,
    reason: str,
    suggested_probe: str,
    accepted: bool = False,
    final_probe: str = "",
) -> dict:
    """Build a camera suggestion entry for a P5 transcript record."""
    return {
        "signal": signal,
        "confidence": confidence,
        "reason": reason,
        "suggested_probe": suggested_probe,
        "accepted": accepted,
        "final_probe": final_probe,
    }


def _contains_frame_reference(value) -> bool:
    """Return True when a transcript value contains a temporary frame reference."""
    if isinstance(value, str):
        lowered = value.lower()
        return any(marker in lowered for marker in _FRAME_REFERENCE_MARKERS)
    if isinstance(value, list):
        return any(_contains_frame_reference(item) for item in value)
    if isinstance(value, dict):
        return any(_contains_frame_reference(item) for item in value.values())
    return False


def validate_camera_suggestions(record: dict) -> list[str]:
    """Validate optional camera suggestion fields on one transcript record."""
    errors: list[str] = []
    tid = record.get("triplet_id", "?")
    layer = record.get("question_layer", "?")

    mode = record.get("answer_input_mode")
    if mode is not None and mode not in _VALID_ANSWER_INPUT_MODES:
        errors.append(f"P5: 三联体 {tid} {layer} 层 answer_input_mode 非法值 '{mode}'")

    suggestions = record.get("camera_suggestions", [])
    if suggestions is None:
        suggestions = []
    if not isinstance(suggestions, list):
        return [f"P5: 三联体 {tid} {layer} 层 camera_suggestions 必须是 list"]

    observed = set(record.get("signals_observed", []))
    for i, suggestion in enumerate(suggestions):
        prefix = f"P5: 三联体 {tid} {layer} 层 camera_suggestions[{i}]"
        if not isinstance(suggestion, dict):
            errors.append(f"{prefix} 必须是对象")
            continue
        signal = suggestion.get("signal", "")
        confidence = suggestion.get("confidence", "")
        if signal not in _VALID_INTERVIEW_SIGNALS:
            errors.append(f"{prefix}.signal 非法值 '{signal}'")
        if confidence not in _VALID_CAMERA_CONFIDENCE:
            errors.append(f"{prefix}.confidence 非法值 '{confidence}'")
        if not isinstance(suggestion.get("suggested_probe", ""), str):
            errors.append(f"{prefix}.suggested_probe 必须是字符串")
        if suggestion.get("accepted") is True and signal not in observed:
            errors.append(f"{prefix}: accepted camera signal '{signal}' missing from signals_observed")

    if _contains_frame_reference(record):
        errors.append(f"P5: 三联体 {tid} {layer} 层 transcript must not contain frame paths")

    return errors
```

- [ ] **Step 4: Extend `build_interview_record`**

Change the function signature to:

```python
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
    record = {
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
    }
    if answer_input_mode != "manual_cli" or camera_assist_enabled or camera_suggestions:
        record["answer_input_mode"] = answer_input_mode
    if camera_assist_enabled or camera_suggestions:
        record["camera_assist_enabled"] = camera_assist_enabled
        record["camera_suggestions"] = camera_suggestions or []
    return record
```

- [ ] **Step 5: Extend `check_p5_quality_gate`**

Inside the per-record loop in `check_p5_quality_gate`, after the `signals_observed` checks, add:

```python
            errors.extend(validate_camera_suggestions(r))
```

- [ ] **Step 6: Run the schema tests and verify they pass**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py -k "camera or build_record_supports"
```

Expected: PASS.

- [ ] **Step 7: Run the full P5 test file**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py
```

Expected: PASS.

- [ ] **Step 8: Commit Task 2**

```bash
git add tools/interview_session.py tools/test_interview_session.py
git commit -m "feat: validate camera interview suggestions"
```

---

### Task 3: Render Camera Suggestions In Markdown Transcript

**Files:**
- Modify: `tools/interview_session.py`
- Modify: `tools/test_interview_session.py`

- [ ] **Step 1: Write the failing Markdown rendering test**

Append this test to `tools/test_interview_session.py`:

```python
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
    assert "回答前有明显停顿" in md
    assert ".jpg" not in md
    assert "frame_path" not in md
```

- [ ] **Step 2: Run the Markdown test and verify it fails**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py::test_transcript_md_renders_camera_suggestions_without_frame_paths
```

Expected: FAIL because `generate_transcript_md` does not render camera suggestions.

- [ ] **Step 3: Implement Markdown rendering**

In `generate_transcript_md`, after the existing probe adoption rendering and before operator notes, add:

```python
            camera_suggestions = r.get("camera_suggestions", [])
            if camera_suggestions:
                lines += ["**摄像头辅助建议**：", ""]
                for suggestion in camera_suggestions:
                    signal = suggestion.get("signal", "")
                    confidence = suggestion.get("confidence", "")
                    reason = suggestion.get("reason", "")
                    suggested_probe = suggestion.get("suggested_probe", "")
                    accepted = "已采纳" if suggestion.get("accepted") else "未采纳"
                    final_probe = suggestion.get("final_probe", "")
                    line = f"- [{confidence}] {signal}：{reason}；建议追问：{suggested_probe}；{accepted}"
                    if final_probe:
                        line += f"；实际追问：{final_probe}"
                    lines.append(line)
                lines.append("")
```

- [ ] **Step 4: Run the Markdown test and verify it passes**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py::test_transcript_md_renders_camera_suggestions_without_frame_paths
```

Expected: PASS.

- [ ] **Step 5: Run P5 tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py
```

Expected: PASS.

- [ ] **Step 6: Commit Task 3**

```bash
git add tools/interview_session.py tools/test_interview_session.py
git commit -m "feat: render camera suggestions in transcripts"
```

---

### Task 4: Add CLI Flags And Default-Off Runtime Configuration

**Files:**
- Modify: `tools/interview_session.py`
- Modify: `tools/test_interview_session.py`

- [ ] **Step 1: Write failing CLI tests**

Append these tests to `tools/test_interview_session.py`:

```python
def test_camera_assist_default_off_records_no_camera_fields(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)
    ret = iss.main(
        argv=["--slug", "expert_a", "--base-dir", str(base)],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
    )
    assert ret == 0
    transcript = json.loads((discovery / "interview_transcript.json").read_text(encoding="utf-8"))
    assert all("camera_suggestions" not in record for record in transcript)
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
```

- [ ] **Step 2: Run the CLI tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py -k "camera_assist_cli or default_off or stream_answer"
```

Expected: FAIL because the CLI arguments and record propagation do not exist.

- [ ] **Step 3: Add runtime config helpers**

In `tools/interview_session.py`, add this helper after `validate_camera_suggestions`:

```python
def normalize_answer_input_mode(raw_mode: str) -> str:
    """Map CLI answer input values to transcript values."""
    if raw_mode == "stream":
        return "streaming_text"
    return "manual_cli"
```

- [ ] **Step 4: Extend `run_one_layer` signature and record creation**

Change `run_one_layer` signature to:

```python
def run_one_layer(
    group: dict,
    layer: str,
    input_fn,
    print_fn,
    answer_input_mode: str = "manual_cli",
    camera_assist_enabled: bool = False,
    camera_assist_worker=None,
) -> dict:
```

Start camera capture before answer collection and stop it after `_collect_multiline` returns:

```python
    if camera_assist_enabled and camera_assist_worker is not None:
        camera_assist_worker.start_answer(triplet_id, layer)

    print_fn("\n(请记录专家回答，输入完成后单独一行输入 /done)")
    expert_answer = _collect_multiline(input_fn)

    camera_suggestions: list[dict] = []
    if camera_assist_enabled and camera_assist_worker is not None:
        camera_suggestions = camera_assist_worker.stop_answer()
```

Pass the new fields to `build_interview_record`:

```python
        answer_input_mode=answer_input_mode,
        camera_assist_enabled=camera_assist_enabled,
        camera_suggestions=camera_suggestions,
```

- [ ] **Step 5: Extend `run_triplet_interview` signature and call**

Change the signature to:

```python
def run_triplet_interview(
    group: dict,
    discovery_dir: Path,
    records: list[dict],
    completed_triplets: list[str],
    force_start_layer: str | None = None,
    input_fn=None,
    print_fn=None,
    persist_records_fn=None,
    answer_input_mode: str = "manual_cli",
    camera_assist_enabled: bool = False,
    camera_assist_worker=None,
) -> list[dict]:
```

Change the `run_one_layer` call to:

```python
        record = run_one_layer(
            group,
            layer,
            input_fn,
            print_fn,
            answer_input_mode=answer_input_mode,
            camera_assist_enabled=camera_assist_enabled,
            camera_assist_worker=camera_assist_worker,
        )
```

- [ ] **Step 6: Add CLI arguments**

In `main`, add parser arguments after `--dry-run`:

```python
    parser.add_argument("--camera-assist", action="store_true", dest="camera_assist",
                        help="启用可选摄像头辅助；需要用户事先明确同意")
    parser.add_argument("--answer-input", choices=("manual_cli", "stream"), default="manual_cli",
                        dest="answer_input", help="专家回答文本输入模式")
    parser.add_argument("--camera-frame-interval", type=float, default=3.0,
                        dest="camera_frame_interval", help="摄像头辅助采帧间隔秒数")
    parser.add_argument("--camera-temp-dir", default="/tmp/expert-skill-camera",
                        dest="camera_temp_dir", help="摄像头临时帧根目录")
    parser.add_argument("--camera-analysis-timeout", type=float, default=30.0,
                        dest="camera_analysis_timeout", help="等待 agent 分析响应的秒数")
    parser.add_argument("--disable-camera-worker-for-test", action="store_true",
                        dest="disable_camera_worker_for_test",
                        help=argparse.SUPPRESS)
```

After `_input = input_fn or input`, add:

```python
    answer_input_mode = normalize_answer_input_mode(args.answer_input)
```

Before running sessions, add:

```python
    camera_assist_worker = None
```

Pass these values into `run_triplet_interview`:

```python
            answer_input_mode=answer_input_mode,
            camera_assist_enabled=args.camera_assist,
            camera_assist_worker=camera_assist_worker,
```

- [ ] **Step 7: Run the CLI tests and verify they pass**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py -k "camera_assist_cli or default_off or stream_answer"
```

Expected: PASS.

- [ ] **Step 8: Run P5 tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py
```

Expected: PASS.

- [ ] **Step 9: Commit Task 4**

```bash
git add tools/interview_session.py tools/test_interview_session.py
git commit -m "feat: add camera interview cli flags"
```

---

### Task 5: Implement Agent Frame Event Protocol With Fakeable Camera Capture

**Files:**
- Modify: `tools/interview_session.py`
- Modify: `tools/test_interview_session.py`

- [ ] **Step 1: Write failing event protocol tests**

Append these tests to `tools/test_interview_session.py`:

Add this import near the top of the file:

```python
import time
```

```python
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
```

- [ ] **Step 2: Run event protocol tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py -k "camera_frame_event or camera_response or CameraAssistWorker"
```

Expected: FAIL because event builders, parser, and worker do not exist.

- [ ] **Step 3: Add imports**

At the top of `tools/interview_session.py`, add:

```python
import threading
import time
import uuid
```

- [ ] **Step 4: Add frame event helpers**

Add these functions after `normalize_answer_input_mode`:

```python
def build_camera_frame_event(
    session_id: str,
    frame_id: str,
    frame_path: Path,
    response_path: Path,
    triplet_id: str,
    layer: str,
) -> dict:
    """Build the JSON task that an agent uses to analyze one temporary frame."""
    return {
        "event": "camera_frame_ready",
        "session_id": session_id,
        "frame_id": frame_id,
        "frame_path": str(frame_path),
        "response_path": str(response_path),
        "triplet_id": triplet_id,
        "question_layer": layer,
        "instruction": (
            "Analyze the expert's nonverbal reaction for possible interview signals. "
            "Return JSON only as an array of objects with signal, confidence, reason, "
            "and suggested_probe. Return [] if nothing useful is detected."
        ),
    }


def parse_camera_response_file(response_path: Path) -> tuple[list[dict], list[str]]:
    """Parse an agent-written camera response file into normalized suggestions."""
    try:
        raw = json.loads(response_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return [], [f"camera response invalid JSON: {response_path}"]
    except OSError as exc:
        return [], [f"camera response unreadable: {exc}"]

    if not isinstance(raw, list):
        return [], ["camera response must be a JSON array"]

    suggestions: list[dict] = []
    errors: list[str] = []
    for i, item in enumerate(raw):
        if not isinstance(item, dict):
            errors.append(f"camera response item {i} must be an object")
            continue
        suggestion = build_camera_suggestion(
            signal=str(item.get("signal", "")),
            confidence=str(item.get("confidence", "")),
            reason=str(item.get("reason", "")),
            suggested_probe=str(item.get("suggested_probe", "")),
            accepted=False,
            final_probe="",
        )
        probe_errors = validate_camera_suggestions({
            "triplet_id": "camera_response",
            "question_layer": str(i),
            "signals_observed": [],
            "camera_suggestions": [suggestion],
        })
        if probe_errors:
            errors.extend(probe_errors)
            continue
        suggestions.append(suggestion)
    return suggestions, errors
```

- [ ] **Step 5: Add optional frame capture**

Add:

```python
def capture_camera_frame(frame_path: Path, camera_index: int = 0) -> tuple[bool, str]:
    """Capture one camera frame to disk using cv2 when available."""
    try:
        import cv2  # noqa: PLC0415
    except ImportError:
        return False, "OpenCV/cv2 is not installed; camera assist disabled"

    camera = cv2.VideoCapture(camera_index)
    try:
        if not camera.isOpened():
            return False, f"camera index {camera_index} is not available"
        ok, frame = camera.read()
        if not ok:
            return False, "failed to read camera frame"
        frame_path.parent.mkdir(parents=True, exist_ok=True)
        if not cv2.imwrite(str(frame_path), frame):
            return False, f"failed to write frame: {frame_path}"
        return True, ""
    finally:
        camera.release()
```

- [ ] **Step 6: Add `CameraAssistWorker`**

Add:

```python
class CameraAssistWorker:
    """Capture temporary frames and collect agent-written suggestion responses."""

    def __init__(
        self,
        temp_root: Path,
        frame_interval: float,
        analysis_timeout: float,
        print_fn,
        capture_frame_fn=None,
        session_id: str | None = None,
        response_dir: Path | None = None,
    ) -> None:
        self.temp_root = Path(temp_root)
        self.frame_interval = frame_interval
        self.analysis_timeout = analysis_timeout
        self.print_fn = print_fn
        self.capture_frame_fn = capture_frame_fn or capture_camera_frame
        self.session_id = session_id or f"sess-{uuid.uuid4().hex[:12]}"
        self.session_dir = self.temp_root / self.session_id
        self.response_dir = response_dir or (self.session_dir / "responses")
        self._counter = 0
        self._stop_event: threading.Event | None = None
        self._thread: threading.Thread | None = None
        self._suggestions: list[dict] = []

    def capture_once(self, triplet_id: str, layer: str) -> list[dict]:
        """Capture one frame, emit an event, wait for response, delete the frame."""
        self._counter += 1
        frame_id = f"frame-{self._counter:04d}"
        frame_path = self.session_dir / f"{frame_id}.jpg"
        response_path = self.response_dir / f"{frame_id}.json"
        self.response_dir.mkdir(parents=True, exist_ok=True)

        ok, error = self.capture_frame_fn(frame_path)
        if not ok:
            self.print_fn(f"[camera-assist] {error}")
            return []

        event = build_camera_frame_event(
            session_id=self.session_id,
            frame_id=frame_id,
            frame_path=frame_path,
            response_path=response_path,
            triplet_id=triplet_id,
            layer=layer,
        )
        self.print_fn(json.dumps(event, ensure_ascii=False))

        deadline = time.monotonic() + self.analysis_timeout
        suggestions: list[dict] = []
        while time.monotonic() < deadline:
            if response_path.exists():
                suggestions, errors = parse_camera_response_file(response_path)
                for err in errors:
                    self.print_fn(f"[camera-assist] {err}")
                break
            time.sleep(min(0.05, self.analysis_timeout))

        try:
            frame_path.unlink(missing_ok=True)
        except OSError as exc:
            print(f"[camera-assist] failed to delete temporary frame: {exc}", file=sys.stderr)
        return suggestions

    def start_answer(self, triplet_id: str, layer: str) -> None:
        """Start interval capture for one answer."""
        if self._thread is not None and self._thread.is_alive():
            self.stop_answer()
        self._suggestions = []
        self._stop_event = threading.Event()
        self._thread = threading.Thread(
            target=self._capture_loop,
            args=(triplet_id, layer, self._stop_event),
            daemon=True,
        )
        self._thread.start()

    def _capture_loop(self, triplet_id: str, layer: str, stop_event: threading.Event) -> None:
        """Capture frames until the answer is complete."""
        while not stop_event.is_set():
            self._suggestions.extend(self.capture_once(triplet_id, layer))
            stop_event.wait(self.frame_interval)

    def stop_answer(self) -> list[dict]:
        """Stop interval capture and return suggestions collected for the answer."""
        if self._stop_event is not None:
            self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=max(self.analysis_timeout, 0.1))
        self._thread = None
        self._stop_event = None
        return list(self._suggestions)
```

- [ ] **Step 7: Run event protocol tests and verify they pass**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py -k "camera_frame_event or camera_response or CameraAssistWorker"
```

Expected: PASS.

- [ ] **Step 8: Run P5 tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py
```

Expected: PASS.

- [ ] **Step 9: Commit Task 5**

```bash
git add tools/interview_session.py tools/test_interview_session.py
git commit -m "feat: emit camera frame analysis events"
```

---

### Task 6: Bind Camera Capture To Answer Lifecycle

**Files:**
- Modify: `tools/interview_session.py`
- Modify: `tools/test_interview_session.py`

- [ ] **Step 1: Write failing lifecycle integration tests**

Append these tests to `tools/test_interview_session.py`:

```python
def test_run_one_layer_collects_camera_suggestions_from_worker():
    inputs = layer_inputs(answer="专家回答A", followup="追问回答A")

    class FakeWorker:
        def __init__(self):
            self.started = None

        def start_answer(self, triplet_id, layer):
            self.started = (triplet_id, layer)

        def stop_answer(self):
            assert self.started == ("tg_001", "A")
            return [
                iss.build_camera_suggestion(
                    signal="hesitated",
                    confidence="medium",
                    reason="回答期间有明显停顿",
                    suggested_probe="你在衡量什么？",
                )
            ]

    record = iss.run_one_layer(
        SAMPLE_GROUP,
        "A",
        make_input_fn(*inputs),
        lambda x: None,
        answer_input_mode="manual_cli",
        camera_assist_enabled=True,
        camera_assist_worker=FakeWorker(),
    )
    assert record["camera_suggestions"][0]["signal"] == "hesitated"
    assert record["camera_assist_enabled"] is True


def test_camera_assist_main_uses_fake_worker_during_answer(tmp_path):
    base, discovery = setup_discovery_dir(tmp_path, [SAMPLE_GROUP], meta={"discovery": {}})
    inputs = _full_session_inputs(group_count=1)

    class FakeWorker:
        def __init__(self):
            self.current = None

        def start_answer(self, triplet_id, layer):
            self.current = (triplet_id, layer)

        def stop_answer(self):
            triplet_id, layer = self.current
            return [
                iss.build_camera_suggestion(
                    signal="hesitated",
                    confidence="medium",
                    reason=f"{triplet_id}-{layer} 有停顿",
                    suggested_probe="你在衡量什么？",
                )
            ]

    ret = iss.main(
        argv=[
            "--slug", "expert_a",
            "--base-dir", str(base),
            "--camera-assist",
        ],
        input_fn=make_input_fn(*inputs),
        print_fn=lambda x: None,
        camera_worker_factory=lambda args, print_fn: FakeWorker(),
    )
    assert ret == 0
    transcript = json.loads((discovery / "interview_transcript.json").read_text(encoding="utf-8"))
    assert transcript[0]["camera_suggestions"][0]["signal"] == "hesitated"
```

- [ ] **Step 2: Run lifecycle tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py -k "collects_camera_suggestions or fake_worker"
```

Expected: FAIL until `main` accepts a fake worker factory and wires the worker into answer lifecycle.

- [ ] **Step 3: Extend `main` for worker factory injection**

Change the signature:

```python
def main(argv: list[str] | None = None, input_fn=None, print_fn=None, camera_worker_factory=None) -> int:
```

After parsing and `_print` setup, build the worker:

```python
    camera_assist_worker = None
    if args.camera_assist:
        if not args.disable_camera_worker_for_test:
            if camera_worker_factory is not None:
                camera_assist_worker = camera_worker_factory(args, _print)
            else:
                camera_assist_worker = CameraAssistWorker(
                    temp_root=Path(args.camera_temp_dir),
                    frame_interval=args.camera_frame_interval,
                    analysis_timeout=args.camera_analysis_timeout,
                    print_fn=_print,
                )
```

Remove the earlier `camera_assist_worker = None` initialization from Task 4 if it duplicates this logic.

- [ ] **Step 4: Bind worker start/stop to answer collection**

The code in `run_one_layer` should start camera capture immediately before answer collection and stop it immediately after the answer completes:

```python
    if camera_assist_enabled and camera_assist_worker is not None:
        camera_assist_worker.start_answer(triplet_id, layer)

    print_fn("\n(请记录专家回答，输入完成后单独一行输入 /done)")
    expert_answer = _collect_multiline(input_fn)

    camera_suggestions: list[dict] = []
    if camera_assist_enabled and camera_assist_worker is not None:
        camera_suggestions = camera_assist_worker.stop_answer()
```

- [ ] **Step 5: Run lifecycle tests and verify they pass**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py -k "collects_camera_suggestions or fake_worker"
```

Expected: PASS.

- [ ] **Step 6: Run P5 tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_session.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 6**

```bash
git add tools/interview_session.py tools/test_interview_session.py
git commit -m "feat: attach camera suggestions to interview records"
```

---

### Task 7: Add P6 Camera Evidence Guardrails

**Files:**
- Modify: `prompts/discovery/interview_analyzer.md`
- Modify: `tools/interview_analyzer.py`
- Modify: `tools/test_interview_analyzer.py`

- [ ] **Step 1: Write failing P6 guardrail tests**

Append these tests to `tools/test_interview_analyzer.py`:

```python
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
```

- [ ] **Step 2: Run P6 guardrail tests and verify they fail**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_analyzer.py -k "camera"
```

Expected: FAIL because P6 guardrails and prompt text do not exist.

- [ ] **Step 3: Add camera-only evidence detector**

In `tools/interview_analyzer.py`, add this helper before `check_p6_quality_gate`:

```python
def _is_camera_only_evidence(finding: dict) -> bool:
    """Return True if a latent finding is grounded only in camera suggestions."""
    evidence = finding.get("evidence", {})
    quote = str(evidence.get("expert_quote", "")).strip().lower()
    reason = str(evidence.get("confidence_reason", "")).strip().lower()
    if not quote:
        return False
    quote_markers = ("camera_suggestion", "camera_suggestions", "摄像头建议")
    reason_only_markers = ("only camera", "camera-only", "仅凭摄像头")
    return any(marker in quote for marker in quote_markers) or any(
        marker in reason for marker in reason_only_markers
    )
```

In `check_p6_quality_gate`, inside the `for f in a.get("latent_findings", [])` loop, add:

```python
            if _is_camera_only_evidence(f):
                errors.append(f"P6: 三联体 {tid} 的 finding 使用 camera-only evidence，必须引用专家原话或决策行为")
```

- [ ] **Step 4: Update the P6 prompt**

In `prompts/discovery/interview_analyzer.md`, after the input section for interview records, add:

```markdown
### 摄像头辅助建议

访谈记录中可能包含 `camera_suggestions`。这些字段来自可选摄像头辅助，只能作为追问触发线索或分析注意力提示。

你可以说明某个追问是由摄像头辅助建议触发的，但不能仅凭摄像头建议生成隐性知识发现。每个 `latent_findings[*].evidence.expert_quote` 必须引用专家原话、追问回答或 A/B/C 决策行为，不能写成 `camera_suggestion`、`摄像头建议` 或其他非专家原话。
```

In the quality standards section, add:

```markdown
- 如果访谈记录包含 `camera_suggestions`，只能作为辅助上下文；不能仅凭摄像头建议生成隐性知识发现
```

- [ ] **Step 5: Run P6 guardrail tests and verify they pass**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_analyzer.py -k "camera"
```

Expected: PASS.

- [ ] **Step 6: Run P6 tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q tools/test_interview_analyzer.py
```

Expected: PASS.

- [ ] **Step 7: Commit Task 7**

```bash
git add prompts/discovery/interview_analyzer.md tools/interview_analyzer.py tools/test_interview_analyzer.py
git commit -m "feat: guard p6 against camera-only evidence"
```

---

### Task 8: Final Regression And Spec Cross-Check

**Files:**
- Modify only if previous tasks reveal inconsistencies:
  - `docs/superpowers/specs/2026-05-28-camera-assisted-interview-design.md`
  - `README.md`

- [ ] **Step 1: Run all tests**

Run:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q
```

Expected: PASS with all tests passing.

- [ ] **Step 2: Verify no transcript path leakage appears in tests**

Run:

```bash
rg -n "frame_path|/tmp/expert-skill-camera|\\.jpg|\\.jpeg|\\.png|\\.webp" tools/test_interview_session.py tools/test_interview_analyzer.py
```

Expected: matches only in tests that intentionally verify event emission or leakage rejection. No fixture should expect a frame path inside `interview_transcript.json` or `interview_transcript.md`.

- [ ] **Step 3: Verify CLI help includes camera flags**

Run:

```bash
python3 tools/interview_session.py --help
```

Expected: output includes `--camera-assist`, `--answer-input`, `--camera-frame-interval`, `--camera-temp-dir`, and `--camera-analysis-timeout`.

- [ ] **Step 4: Verify the design requirements are covered**

Read:

```bash
sed -n '1,340p' docs/superpowers/specs/2026-05-28-camera-assisted-interview-design.md
```

Check against these implemented points:

- Camera assist is optional and default-off.
- `SKILL.md` requires user consent before P5 camera use.
- No model API is called inside this repository.
- Temporary frame paths are emitted only in camera frame events, not transcript artifacts.
- Transcript stores only structured text suggestions.
- P5 validates camera suggestions and accepted signals.
- P6 rejects camera-only latent finding evidence.

- [ ] **Step 5: Update `README.md` only if CLI help and `SKILL.md` diverge**

If the README P5 command section does not mention camera assistance after implementation, add this compact note under "P5：访谈记录":

````markdown
摄像头辅助是可选能力，默认关闭。只有用户明确同意后，agent 才能使用：

```bash
python tools/interview_session.py \
  --slug demo-expert \
  --base-dir ./skills/expert \
  --camera-assist
```

摄像头临时帧只用于当前 agent 的多模态分析，不写入 transcript；最终记录只保存结构化文字建议。
````

- [ ] **Step 6: Commit final docs if changed**

If Step 5 changed README or spec text:

```bash
git add README.md docs/superpowers/specs/2026-05-28-camera-assisted-interview-design.md
git commit -m "docs: align camera assist usage notes"
```

If no files changed, do not create an empty commit.

- [ ] **Step 7: Verify final branch state**

Run:

```bash
git status --short
git log --oneline --max-count=8
```

Expected: clean working tree and task commits visible on `camera-assisted-interview-design`.
