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
