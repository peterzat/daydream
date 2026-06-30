"""Offline review harness (daydream/review.py): builds one self-contained
contact sheet from worlds/bunny.json with no live server and no live.db touch.

Engines are fully mocked: generate_image writes a tiny PNG, litellm.acompletion
returns a canned narrate, and the reachability probes are stubbed. The world
load + data-skill dialogue pipeline run for real against a throwaway temp DB,
so the test exercises the actual voice path the same way test_voice_samples
does, just generalized across the bunny NPCs."""

import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest
from PIL import Image

from daydream import db, events, review


@pytest.fixture(autouse=True)
def fresh_state():
    db.close_db()
    events.reset_subscribers()
    yield
    db.close_db()
    events.reset_subscribers()


def _fake_llm(text: str):
    payload = {"effects": [{"kind": "narrate", "text": text}]}

    async def _call(*args, **kwargs):
        class _Msg:
            content = json.dumps(payload)

        class _Choice:
            message = _Msg()

        class _Resp:
            choices = [_Choice()]
            usage = type("U", (), {"prompt_tokens": 10, "completion_tokens": 5})()

        return _Resp()

    return _call


async def _fake_generate_image(target, **kwargs):
    """Stand in for ComfyUI: write a tiny PNG to the target's out_path."""
    out = Path(target.out_path)
    Image.new("RGB", (8, 8), (200, 160, 110)).save(out)
    return out


@pytest.mark.tier_medium
def test_review_builds_contact_sheet(tmp_path):
    out_dir = tmp_path / "review"
    before_env = os.environ.get("DAYDREAM_DATA_DIR")

    with patch("daydream.review._comfyui_reachable", return_value=True), \
         patch("daydream.review._vllm_reachable", return_value=True), \
         patch("daydream.images.client.generate_image", new=_fake_generate_image), \
         patch("litellm.acompletion", new=_fake_llm("Rook taps the anvil. \"Hm.\"")):
        rc = review.main(["--out-dir", str(out_dir)])

    assert rc == 0
    sheet = out_dir / "index.html"
    assert sheet.exists()
    text = sheet.read_text()

    # Every aesthetic anchor (incl. the forge) rendered into the sheet's dir.
    for anchor in ("forge", "meadow_dusk", "cozy_room", "forest_path"):
        assert (out_dir / f"{anchor}.png").exists(), anchor
        assert anchor in text, anchor

    # Each authored NPC voice is present, with the mocked narrate captured.
    for npc in ("Rook", "Iris", "Bram"):
        assert npc in text, npc
    assert "Rook taps the anvil." in text

    # The one irreducible browser glance is batched into the same artifact.
    assert "the dream is sleeping" in text
    assert "the dream shifts" in text

    # The harness restores DAYDREAM_DATA_DIR — it never leaks the temp world
    # (evidence it did not touch the operator's live.db).
    assert os.environ.get("DAYDREAM_DATA_DIR") == before_env


@pytest.mark.tier_short
def test_review_degrades_when_engines_down(tmp_path):
    """Both engines down still yields a usable sheet: notes for the skipped
    sections plus the browser checklist (the graceful-failure ethos)."""
    out_dir = tmp_path / "review"
    with patch("daydream.review._comfyui_reachable", return_value=False), \
         patch("daydream.review._vllm_reachable", return_value=False):
        rc = review.main(["--out-dir", str(out_dir)])
    assert rc == 0
    text = (out_dir / "index.html").read_text()
    assert "comfyui-up" in text  # image section degraded with a start hint
    assert "vllm-up" in text     # voice section degraded with a start hint
    assert "the dream is sleeping" in text  # checklist still present
    # No PNGs and no NPC dialogue when engines are down.
    assert not list(out_dir.glob("*.png"))
