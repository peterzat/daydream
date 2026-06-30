"""Claude-vision aesthetic gate — logic, gating, and parse (no key, no GPU).

The gate (daydream/testing/vision_gate.py) is the OPT-IN automation that
replaces a human aesthetic eyeball with an Opus vision rubric check. These
tests pin the gate's behavior with litellm fully mocked, so the whole thing is
GPU-free, key-free, and never makes a network call: the env flag controls
on/off, the rubric carries the WHIMSY constraints, the JSON reply parses, and
a disqualifying element caps the verdict to FAIL.
"""

from pathlib import Path

import pytest
from PIL import Image

from daydream.testing import vision_gate

pytestmark = pytest.mark.tier_short


def _tiny_png(tmp_path: Path) -> Path:
    p = tmp_path / "swatch.png"
    Image.new("RGB", (8, 8), (246, 243, 236)).save(p)  # WHIMSY paper cream
    return p


def test_enabled_respects_flag(monkeypatch):
    monkeypatch.delenv(vision_gate.ENV_FLAG, raising=False)
    assert vision_gate.enabled() is False
    for off in ("", "0", "false", "no", "off"):
        monkeypatch.setenv(vision_gate.ENV_FLAG, off)
        assert vision_gate.enabled() is False, off
    for on in ("1", "true", "yes", "on"):
        monkeypatch.setenv(vision_gate.ENV_FLAG, on)
        assert vision_gate.enabled() is True, on


def test_threshold_override(monkeypatch):
    monkeypatch.delenv(vision_gate.THRESHOLD_ENV, raising=False)
    assert vision_gate.threshold() == vision_gate.DEFAULT_THRESHOLD
    monkeypatch.setenv(vision_gate.THRESHOLD_ENV, "8")
    assert vision_gate.threshold() == 8
    monkeypatch.setenv(vision_gate.THRESHOLD_ENV, "not-an-int")
    assert vision_gate.threshold() == vision_gate.DEFAULT_THRESHOLD  # falls back


def test_rubric_carries_whimsy_constraints():
    sys = vision_gate.RUBRIC_SYSTEM.lower()
    # The tone bible's positive anchors + a few disqualifiers must be present,
    # so the gate actually grades against WHIMSY and not some generic prompt.
    for token in ("watercolor", "spiritfarer", "a short hike", "cream and sage"):
        assert token in sys, token
    for banned in ("pixel-art", "machinery", "horror", "neon"):
        assert banned in sys, banned


def test_build_messages_has_rubric_and_image(tmp_path):
    png = _tiny_png(tmp_path)
    msgs = vision_gate.build_messages(png, "the forge")
    assert msgs[0]["role"] == "system"
    assert "watercolor" in msgs[0]["content"].lower()
    # The image rides as a base64 data URL block (litellm -> Anthropic vision).
    blocks = msgs[1]["content"]
    image_blocks = [b for b in blocks if b.get("type") == "image_url"]
    assert image_blocks, "no image block in the user message"
    assert image_blocks[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "the forge" in " ".join(b.get("text", "") for b in blocks)


def test_parse_verdict_pass_fail_and_banned_cap():
    thr = 6
    ok = vision_gate.parse_verdict('{"score": 8, "banned": [], "reason": "cozy"}', thr)
    assert ok.passed and ok.score == 8 and ok.label == "PASS 8/10"

    low = vision_gate.parse_verdict('{"score": 4, "banned": [], "reason": "flat"}', thr)
    assert not low.passed and low.label == "FAIL 4/10"

    # A disqualifying element caps to FAIL even with a high score.
    banned = vision_gate.parse_verdict(
        '{"score": 9, "banned": ["machinery"], "reason": "industrial"}', thr
    )
    assert not banned.passed
    assert banned.banned == ("machinery",)


async def test_rate_image_disabled_raises(tmp_path, monkeypatch):
    monkeypatch.delenv(vision_gate.ENV_FLAG, raising=False)
    with pytest.raises(RuntimeError, match="disabled"):
        await vision_gate.rate_image(_tiny_png(tmp_path))


async def test_rate_image_mocked_call(tmp_path, monkeypatch):
    monkeypatch.setenv(vision_gate.ENV_FLAG, "1")
    png = _tiny_png(tmp_path)

    captured = {}

    class _Msg:
        content = '{"score": 9, "banned": [], "reason": "soft watercolor, on-aesthetic"}'

    class _Choice:
        message = _Msg()

    class _Resp:
        choices = [_Choice()]

    async def _fake_acompletion(**kwargs):
        captured.update(kwargs)
        return _Resp()

    import litellm
    monkeypatch.setattr(litellm, "acompletion", _fake_acompletion)

    verdict = await vision_gate.rate_image(png, subject="the forge")
    assert verdict.passed and verdict.score == 9
    # The real WHIMSY rubric + image block were sent, JSON response_format set.
    assert captured["model"] == vision_gate.model()
    assert captured["response_format"] == {"type": "json_object"}
    sent_image = [
        b for b in captured["messages"][1]["content"] if b.get("type") == "image_url"
    ]
    assert sent_image and sent_image[0]["image_url"]["url"].startswith("data:image/png;base64,")
