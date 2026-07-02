"""The canonical walkthrough (SPEC 2026-07-02 criterion 1): the committed
dataset drives the parser -> executor over the loaded worlds/zork1.json
under an LLM spy asserting ZERO calls and the pinned world seed. Segment
checkpoints (room, score, carried, deposited, flags, narration fragments)
hold at every step; the final 350/win assertions arm when the dataset
declares itself complete (the endgame region's commit)."""

import json
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import config, db, events, objects, parser, pronouns, verbs, worldstate
from daydream.llm import bootstrap

pytestmark = pytest.mark.tier_medium

ROOT = Path(__file__).resolve().parent.parent
DATASET = json.loads((ROOT / "tests/data/zork1_walkthrough.json").read_text())
ENVELOPE = ROOT / "worlds/zork1.json"

WORLD = "w-zork1"
ACTOR = "t-adventurer"


@pytest.fixture()
def zork_world(tmp_path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    pronouns.reset()
    spy = AsyncMock(side_effect=AssertionError(
        "criterion 1: the walkthrough must make ZERO LLM calls"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    env = json.loads(ENVELOPE.read_text())
    out = tmp_path / "zork1.db"
    bootstrap.load_world("zork1", env, out)
    db.init_live(path=out, migrations_dir=config.MIGRATIONS_DIR)
    # The canonical run is played BY A PLAYER: the wanderer daemon's
    # pickpocket rolls only target player-controlled toons, so an
    # unclaimed actor would replay a different seeded stream than the
    # live game (the swap rehearsal caught exactly this divergence).
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1 WHERE id = ?", (ACTOR,)
    )
    assert worldstate.rng_seed(WORLD) == "zork1-release-88"  # pinned seed
    yield spy
    db.close_db()
    events.reset_subscribers()
    pronouns.reset()


def carried_names() -> set[str]:
    return {o.name for o in objects.contents(ACTOR, kind="thing")}


def case_names() -> set[str]:
    return {o.name for o in objects.contents("o-trophy-case", kind="thing")}


def recent_narrates(since: int) -> str:
    return " | ".join(
        e.payload.get("text", "") for e in events.fetch_since(since)
        if e.kind == "narrate"
    )


async def run_command(text: str, conn_state: dict) -> None:
    lp = await parser.parse_line(ACTOR, text, pending=conn_state.get("clarify"))
    conn_state["clarify"] = lp.clarify
    assert lp.error is None, f"parse error on {text!r}: {lp.error}"
    assert lp.commands or lp.clarify or lp.message, f"{text!r} parsed to nothing"
    for p in lp.commands:
        assert p.verb != "none", f"{text!r} fell to chatter"
        await verbs.execute_command(
            ACTOR, p.verb, p.dobj_id, p.iobj_id, p.args, dobj_name=p.dobj_name
        )


def check(expect: dict, cmd: str, seq_before: int) -> None:
    where = f"after {cmd!r}"
    if "room" in expect:
        assert objects.get(ACTOR).location_id == expect["room"], (
            f"{where}: in {objects.get(ACTOR).location_id}, wanted {expect['room']}")
    if "score" in expect:
        assert worldstate.score(WORLD) == expect["score"], (
            f"{where}: score {worldstate.score(WORLD)}, wanted {expect['score']}")
    for name in expect.get("carrying", []):
        assert name in carried_names(), f"{where}: not carrying {name!r}"
    for name in expect.get("in_case", []):
        assert name in case_names(), f"{where}: {name!r} not in the trophy case"
    for flag, value in (expect.get("flag") or {}).items():
        assert worldstate.get_flag(WORLD, flag) is value, (
            f"{where}: flag {flag} != {value}")
    if "narrate_contains" in expect:
        assert expect["narrate_contains"] in recent_narrates(seq_before), (
            f"{where}: narration lacks {expect['narrate_contains']!r}")


@pytest.mark.parametrize(
    "segment", DATASET["segments"], ids=[s["name"] for s in DATASET["segments"]]
)
async def test_walkthrough_segments_are_cumulative_prefixes(zork_world, segment):
    """Each parametrized case replays the walkthrough FROM THE START up
    through its segment, so any segment failure names the exact frontier
    while earlier segments stay green (the region-by-region growth loop)."""
    conn_state: dict = {"clarify": None}
    for seg in DATASET["segments"]:
        for step in seg["commands"]:
            seq_before = events.max_seq()
            await run_command(step["cmd"], conn_state)
            if "expect" in step:
                check(step["expect"], step["cmd"], seq_before)
        if seg["name"] == segment["name"]:
            break


async def test_walkthrough_completes_at_350(zork_world):
    """The endgame contract (criterion 1). Armed when the dataset declares
    itself complete; until then this records the frontier explicitly."""
    if not DATASET.get("complete"):
        pytest.skip("walkthrough dataset not yet complete (world under construction)")
    conn_state: dict = {"clarify": None}
    for seg in DATASET["segments"]:
        for step in seg["commands"]:
            await run_command(step["cmd"], conn_state)
    assert worldstate.score(WORLD) == 350
    assert worldstate.rank_for(WORLD, 350) == "Master Adventurer"
    assert len(case_names()) >= 19 or worldstate.get(WORLD, "won")
    assert worldstate.get_flag(WORLD, "WON-ENABLED") is True
    assert worldstate.get(WORLD, "won") is not None  # the barrow entered
    assert objects.get(ACTOR).location_id == "r-stone-barrow"
