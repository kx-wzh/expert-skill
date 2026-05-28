# Camera-Assisted Expert Interview Design

Date: 2026-05-28
Status: draft-for-user-review
Branch: camera-assisted-interview-design

## Problem

The discovery pipeline already mines tacit expert knowledge through P5 structured interviews and P6 interview analysis. P5 records answers, follow-ups, operator notes, and manually observed signals such as `noticed`, `hesitated`, `boundary_invented`, `contradiction`, `pushback`, and `fuzzy_language`.

Some high-value tacit knowledge appears when the expert hesitates, looks uncertain, pushes back on the premise, or visibly struggles to draw a boundary. Today those nonverbal signals depend entirely on the interviewer noticing and recording them. When an agent such as Hermes runs the skill, the agent may already be powered by a multimodal model and can help notice these cues during the interview.

The goal is to add optional camera-assisted, real-time prompt support to P5 without turning facial expression analysis into evidence by itself.

## Goals

- Let an agent ask the user whether to enable camera assistance before P5 starts.
- Keep camera assistance optional and disabled by default.
- Fit Hermes-style agent execution, where the current agent model can inspect images.
- Avoid direct model API calls inside `expert-skill`.
- Analyze expert nonverbal reactions during answers, not after the whole interview.
- Support both manual text entry and speech-to-text input through one answer event stream.
- Save only structured text suggestions in the transcript, never raw images, videos, audio, or temporary frame paths.
- Treat camera suggestions as weak prompts for follow-up, not final tacit knowledge evidence.

## Non-Goals

- Do not build a browser UI for camera access in this version.
- Do not integrate OpenAI, Whisper, or any other model API directly into the repository.
- Do not infer expert personality, emotion, or mental state as a final conclusion.
- Do not save original camera frames, videos, or audio recordings.
- Do not require the expert to operate the CLI or type control commands.
- Do not change P3/P4/P6/P7 semantics beyond allowing P6 to read camera suggestions as auxiliary context.

## User Consent Flow

Before starting P5, `SKILL.md` should require the agent to ask:

```text
P5 访谈可以选择开启摄像头辅助。开启后，访谈过程中会调用本机摄像头，在专家回答期间定时采集临时帧，并由当前 agent 的多模态模型分析非语言信号，用于提示可能的追问。临时图片只用于实时分析，不保存到 skill 目录或 transcript。是否开启？
```

If the user declines, the agent uses the existing command:

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert
```

If the user explicitly agrees, the agent may enable camera assistance:

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --camera-assist
```

An agent runtime that supports answer streaming can opt into streaming text:

```bash
python3 tools/interview_session.py \
  --slug {slug} \
  --base-dir ./skills/expert \
  --camera-assist \
  --answer-input stream
```

## Architecture

P5 should be split into three conceptual pieces:

```text
Interview Orchestrator
  Advances A/B/C questions, follow-ups, signal confirmation, and transcript writes.

Answer Input Stream
  Converts expert answers into text events. The source can be manual entry,
  speech-to-text, meeting transcription, or another agent-provided stream.

Camera Assist
  Captures temporary frames during expert answers, asks the agent to analyze
  nonverbal cues, and buffers structured suggestions for the current answer.
```

The orchestrator must not care whether text came from manual entry, Hermes speech-to-text, Whisper, or another ASR system. All answer producers emit the same events.

## Event Model

P5 should use a unified answer event protocol:

```json
{"event": "question_presented"}
{"event": "answer_started"}
{"event": "answer_delta", "text": "我觉得这个情况要先看..."}
{"event": "answer_delta", "text": "如果同时还有另一个条件..."}
{"event": "answer_completed"}
{"event": "camera_suggestion_generated"}
{"event": "probe_decision_recorded"}
{"event": "record_committed"}
```

Camera lifecycle binds to answer lifecycle:

```text
answer_started
  -> start camera session
  -> capture one temporary frame every N seconds
  -> emit camera_frame_ready for the agent
  -> agent analyzes frame with its current multimodal model
  -> delete temporary frame
  -> buffer camera_suggestions

answer_completed
  -> stop frame capture
  -> aggregate expert_answer
  -> aggregate camera_suggestions
  -> ask the agent/interviewer whether to accept a suggested signal or probe
  -> write transcript record
```

In the existing manual CLI flow, `/done` may remain an operator control that produces `answer_completed`. It must not appear in the user-facing skill flow as something the expert does.

## Hermes Camera Analysis Protocol

`interview_session.py` should not call a model. When a frame is ready, it should expose a machine-readable task to the agent:

```json
{
  "event": "camera_frame_ready",
  "frame_path": "/tmp/expert-skill-camera/sess-001/frame-004.jpg",
  "triplet_id": "tg_003",
  "question_layer": "B",
  "instruction": "Analyze the expert's nonverbal reaction for possible interview signals. Return JSON only."
}
```

Hermes reads the temporary image path, uses its current multimodal model, and returns a JSON array:

```json
[
  {
    "signal": "hesitated",
    "confidence": "medium",
    "reason": "专家回答时出现停顿和困惑表情，可能正在权衡边界条件",
    "suggested_probe": "你在衡量什么？"
  }
]
```

If nothing useful is detected, the agent returns:

```json
[]
```

The camera helper deletes each frame after analysis or timeout. The final transcript must not contain `frame_path` or any other temporary file path.

## Transcript Schema Additions

Each P5 interview record can add optional camera fields:

```json
{
  "answer_input_mode": "manual_cli | streaming_text",
  "camera_assist_enabled": true,
  "camera_suggestions": [
    {
      "signal": "hesitated",
      "confidence": "medium",
      "reason": "专家回答时出现停顿和困惑表情，可能正在权衡边界条件",
      "suggested_probe": "你在衡量什么？",
      "accepted": true,
      "final_probe": "你在衡量什么？"
    }
  ],
  "signals_observed": ["hesitated"]
}
```

Rules:

- `camera_suggestions` is optional and may be empty.
- `camera_assist_enabled=false` does not require `camera_suggestions`.
- `signals_observed` remains the confirmed signal set.
- A camera suggestion does not automatically become an observed signal.
- If `accepted=true`, the suggestion's `signal` should be present in `signals_observed`.
- `expert_answer` stores only answer text, not camera analysis text.

## Signal Semantics

Camera suggestions must use the existing P5 signal vocabulary:

- `noticed`
- `hesitated`
- `boundary_invented`
- `contradiction`
- `pushback`
- `fuzzy_language`

The agent should prefer conservative output. When uncertain, return `[]` or `confidence=low`. The system should not create new emotion labels such as "angry", "sad", or "anxious" unless they are mapped back to an interview signal and framed as uncertainty.

## Privacy And Retention

Privacy constraints are hard requirements:

- Camera assistance is disabled by default.
- The agent must ask for explicit user consent before enabling it.
- Temporary frames may be written only under a temp directory such as `/tmp/expert-skill-camera/{session_id}/`.
- Temporary frames are deleted after analysis or timeout.
- No raw images, videos, or audio are saved under `skills/expert/{slug}/discovery/`.
- `interview_transcript.json` and `.md` do not include image paths, frame names, or raw image data.
- The transcript saves only structured text suggestions and acceptance decisions.

## P6 Analysis Rules

P6 may read `camera_suggestions` as auxiliary context, but final tacit knowledge extraction must be grounded in at least one of:

- expert answer text,
- expert follow-up answer,
- a decision difference between A/B/C layers,
- an explicit contradiction between stated and actual choices,
- consistency across multiple triplet groups.

Camera data alone cannot produce a latent finding. A valid P6 finding may say that a camera suggestion helped trigger a follow-up, but the evidence quote must come from the expert's words or recorded decision behavior.

## CLI Additions

Recommended first-version arguments:

```text
--camera-assist
--answer-input manual_cli|stream
--camera-frame-interval 3
--camera-temp-dir /tmp/expert-skill-camera
--camera-analysis-timeout 30
```

Default behavior remains unchanged:

- `--camera-assist` defaults to false.
- `--answer-input` defaults to `manual_cli`.
- Existing transcript schema remains valid.
- Existing tests and generated skills remain valid.

## Quality Gates

P5 validation should add checks when camera fields are present:

- `camera_suggestions` must be a list.
- Each suggestion must use an allowed `signal`.
- `confidence` must be `high`, `medium`, or `low`.
- `suggested_probe` must be a string.
- If `accepted=true`, the same signal must appear in `signals_observed`.
- Transcript JSON must not contain frame paths or obvious image path strings such as `.jpg`, `.jpeg`, `.png`, or `.webp`.

P6 validation should ensure that latent findings still include expert quotes or decision evidence. Camera suggestions can increase analyst attention, not replace evidence.

## Error Handling

- Camera unavailable: print a warning and continue without camera assistance.
- User denies camera permission: continue without camera assistance.
- Agent returns invalid JSON: discard that camera suggestion and continue the interview.
- Agent returns unsupported signal: discard or mark as invalid before transcript write.
- Frame analysis times out: delete the frame and continue.
- Temporary file deletion fails: retry best effort and print the path to stderr, but never write it into transcript.

## Phased Implementation

### Phase 1: Agent-Compatible Camera Assist

- Update `SKILL.md` with the consent requirement and command variants.
- Add camera-related CLI flags to `interview_session.py`.
- Add an answer input mode abstraction while keeping the existing manual flow.
- Add temporary frame capture and `camera_frame_ready` event emission.
- Accept agent-returned camera suggestion JSON.
- Persist only structured text suggestions.
- Extend P5 transcript Markdown rendering for accepted camera suggestions.
- Extend P5/P6 quality gates and tests.

### Phase 2: Richer Agent Streaming

- Support true stdin/stdout or JSON-RPC answer events.
- Let Hermes stream `answer_delta` directly from speech-to-text.
- Support multi-frame aggregation per answer instead of single-frame decisions.
- Add backpressure and cancellation for long answers.
- Improve timeout, cleanup, and headless fallback behavior.

## Testing

Add focused tests for:

- `--camera-assist` default-off behavior.
- Consent flow documentation in `SKILL.md`.
- Transcript records with and without `camera_suggestions`.
- P5 quality gate validation of camera suggestion schema.
- Rejection of unsupported signals or invalid confidence values.
- Enforcement that accepted camera suggestions appear in `signals_observed`.
- Enforcement that transcript output does not contain temporary frame paths or image extensions.
- P6 behavior where camera-only suggestions cannot become latent findings without expert evidence.
- Backward compatibility for existing mock transcripts.

Baseline acceptance command:

```bash
UV_CACHE_DIR=/tmp/uv-cache UV_TOOL_DIR=/tmp/uv-tools uvx pytest -q
```

## Design Principle

Camera assist is an optional P5-only capability. It helps the agent notice possible nonverbal signals during expert answers, but it never replaces interview evidence. Final tacit knowledge extraction must still be grounded in expert answers, decision changes, follow-up responses, and cross-triplet consistency.
