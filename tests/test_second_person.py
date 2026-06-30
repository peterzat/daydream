"""Player-action narration is second person (SPEC 2026-06-30 C8).

Static scan over the live authored world (worlds/bunny.json) plus the
data-skill dispatcher system message: no "a visitor" / "the visitor" /
"this visitor" third-person framing in any authored prompt, and the
room-affordance prompts (stoke / tend) address the player as "you".
Runtime second-person output is the flagged one-time eyeball, not a
machine assertion."""

import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

BUNNY = Path(__file__).resolve().parent.parent / "worlds" / "bunny.json"
_VISITOR_FRAMES = ("a visitor", "the visitor", "this visitor")


def _authored_prompts(envelope: dict) -> list[str]:
    out: list[str] = []
    for t in envelope.get("toons", []):
        tpl = (t.get("dialogue") or {}).get("prompt_template")
        if tpl:
            out.append(tpl)
    for s in envelope.get("skills", []):
        if s.get("prompt_template"):
            out.append(s["prompt_template"])
    return out


def test_no_visitor_framing_in_authored_prompts():
    env = json.loads(BUNNY.read_text())
    prompts = _authored_prompts(env)
    assert prompts  # sanity: there are prompts to scan
    for tpl in prompts:
        low = tpl.lower()
        for bad in _VISITOR_FRAMES:
            assert bad not in low, f"third-person {bad!r} framing in an authored prompt"


def test_affordance_prompts_address_the_player_as_you():
    env = json.loads(BUNNY.read_text())
    by_name = {s["name"]: s["prompt_template"] for s in env.get("skills", [])}
    for name in ("stoke", "tend"):
        assert name in by_name, f"missing affordance prompt: {name}"
        assert "you " in by_name[name].lower()


def test_dispatcher_system_message_instructs_second_person():
    from daydream.skills import data

    msg = data._DISPATCHER_SYSTEM.lower()
    assert "second person" in msg
    assert "you" in msg
