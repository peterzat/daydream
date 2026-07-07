"""Journal recap quality probe (SPEC 2026-07-07 criteria 3 + 12).

Five real leave-recaps against live vLLM: each scripted event stream is a
plausible short session in the loft, and journal.write_entry runs the REAL
prompt + model + validation pipeline (temperature 0). The mechanical gates
here are the floor — at least 4/5 recaps survive validation, every survivor
is second person and inside the length window, and none leaks an object id.
The CEILING is the in-session agent grading: the probe records every entry
(and every skip) in tests/baselines/journal_probe.latest.json, and the
review step reads them against WHIMSY.md (gentle, past-tense, grounded in
the events, no invention). Honest-default rule: if quality misses the bar
there, DAYDREAM_JOURNAL_ENABLED ships defaulted off (flag-local-limits)."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from daydream import config, db, events, journal, objects

from .conftest import write_latest

pytestmark = [
    pytest.mark.tier_long,
    pytest.mark.requires_vllm,
]

REPO = Path(__file__).resolve().parent.parent.parent

# Five scripted sessions: (name, [(kind, payload_text_or_direction)]).
# Shapes mirror what the live game emits (say / narrate / move).
SESSIONS = [
    ("greeting-and-lanterns", [
        ("move", "east"),
        ("narrate", "Bell is up a small ladder coaxing a lantern alight, and lifts a sooty hand in greeting."),
        ("say", "hello, Bell"),
        ("narrate", "Bell grins down from the ladder. 'Evening! Mind the wick-smoke, it likes new faces.'"),
        ("narrate", "The lanterns come on one by one around the square, each a small warm pool."),
    ]),
    ("the-gear-comes-home", [
        ("move", "south"),
        ("narrate", "You lift the escapement gear from the moss at the well's foot, cool and whole."),
        ("move", "north"),
        ("narrate", "Tace turns the little gear over in the lamplight, and something long held eases out of their shoulders."),
        ("narrate", "They fold a small brass key into your hand, warm from their pocket."),
    ]),
    ("a-quiet-sweep", [
        ("say", "good evening, Mott"),
        ("narrate", "Mott pauses mid-sweep, leans on the broom, and gives you an unhurried, friendly look."),
        ("narrate", "Mott sets a stray button on the windowsill, where its owner might think to look."),
        ("say", "what's in the tin?"),
        ("narrate", "Mott rattles the tin gently. 'Small things that lost their people. They keep fine here.'"),
    ]),
    ("the-planting", [
        ("narrate", "You press the dreamseed into the earth and hold a small vision of a mossy stair."),
        ("narrate", "The dreamseed takes root, and the dream makes room. A new way opens to the south: The Moss Stair."),
        ("move", "south"),
        ("narrate", "A stair of moss coils gently downward. The air is cool and smells of rain."),
    ]),
    ("a-wander-at-dusk", [
        ("move", "up"),
        ("narrate", "The great clock stands still overhead, its hands resting at a quarter past some old hour."),
        ("move", "down"),
        ("move", "east"),
        ("narrate", "The square smells of wick-smoke and cooling stone."),
    ]),
]


@pytest.fixture(autouse=True)
def journal_on(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_JOURNAL_ENABLED", "1")
    db.init_live(path=tmp_path / "probe.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _script(toon_id: str, steps: list[tuple[str, str]]) -> None:
    for kind, text in steps:
        if kind == "say":
            events.append("toon", toon_id, "say",
                          {"text": text, "name": "Wren"}, room_id="r-meadow")
        elif kind == "move":
            events.append("toon", toon_id, "move",
                          {"direction": text}, room_id="r-meadow")
        else:
            events.append("system", None, "narrate", {"text": text},
                          room_id="r-meadow", recipient_id=toon_id)


async def test_five_leave_recaps_against_live_vllm():
    results: list[dict] = []
    for name, steps in SESSIONS:
        objects.set_property("t-wren", "journal", [])
        objects.set_property("t-wren", "journal_last_seq", events.max_seq())
        _script("t-wren", steps)
        await journal.write_entry("t-wren")
        entries = objects.get_property("t-wren", "journal") or []
        results.append({
            "session": name,
            "written": bool(entries),
            "entry": entries[-1]["text"] if entries else None,
        })

    write_latest("journal_probe", {"sessions": results})

    written = [r for r in results if r["written"]]
    assert len(written) >= 4, (
        f"only {len(written)}/5 recaps survived validation: {results}"
    )
    for r in written:
        text = r["entry"]
        assert journal.MIN_ENTRY_CHARS <= len(text) <= journal.MAX_ENTRY_CHARS
        assert re.search(r"\byou\b", text, re.IGNORECASE), (
            f"{r['session']}: not second person: {text!r}"
        )
        # No object/toon ids in player-visible text, ever.
        assert not re.search(r"\b[rto]-[a-z0-9-]+\b", text), text
