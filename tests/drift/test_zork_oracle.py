"""The differential oracle (SPEC 2026-07-02 criterion 14): replay the
canonical walkthrough in BOTH engines — ours via parser -> executor, the
real Zork I via dfrotz — and compare STATE at every segment boundary:

    room       our room id, mapped through worlds/zork1/oracle_map.json,
               must equal the room name the real game prints
    score      integer equality
    inventory  name multiset equality, carried open containers flattened
               on both sides, names mapped through the oracle map

Combat is compared on outcomes, not blow-by-blow (R3): our dataset's
attack/again counts are OUR seed's fight; the real replay drives each fight
with `attack_until_dead` and skips the dataset's surplus `again`s. State
probes (look/score/i) tick the real clock, so they run ONLY at segment
boundaries — inside a segment the two engines stay command-for-command in
step, which is what keeps the fuse windows (the exorcism ritual) and the
river conveyor aligned.

Without dfrotz or a story file the whole module skips with a named reason
(fidelity relaxation R8: the harness is optional, never load-bearing).
Setup: bin/zork-oracle-bootstrap; export DAYDREAM_ZORK_ORACLE_STORY.
The real RNG is pinned via dfrotz -s (DAYDREAM_ZORK_ORACLE_SEED, default
4); ratification records the seed that plays clean."""

import json
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "tools"))

import zork_oracle  # noqa: E402

pytestmark = pytest.mark.tier_long

DATASET = json.loads((ROOT / "tests/data/zork1_walkthrough.json").read_text())
ORACLE_MAP = json.loads((ROOT / "worlds/zork1/oracle_map.json").read_text())
ENVELOPE = ROOT / "worlds/zork1.json"
WORLD = "w-zork1"
ACTOR = "t-adventurer"

_dfrotz = zork_oracle.find_dfrotz()
_story = zork_oracle.find_story()
if _dfrotz is None:
    pytestmark = [pytest.mark.tier_long, pytest.mark.skip(
        reason="dfrotz not found (run bin/zork-oracle-bootstrap)")]
elif _story is None:
    pytestmark = [pytest.mark.tier_long, pytest.mark.skip(
        reason="DAYDREAM_ZORK_ORACLE_STORY not set (see bin/zork-oracle-bootstrap)")]


@pytest.fixture()
def our_engine(tmp_path, monkeypatch):
    from daydream import config, db, events, pronouns
    from daydream.llm import bootstrap

    db.close_db()
    events.reset_subscribers()
    pronouns.reset()
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=AssertionError("oracle replay must be LLM-free")),
    )
    env = json.loads(ENVELOPE.read_text())
    out = tmp_path / "zork1.db"
    bootstrap.load_world("zork1", env, out)
    db.init_live(path=out, migrations_dir=config.MIGRATIONS_DIR)
    # Replay as a player (matches the live game and the walkthrough test:
    # the wanderer's pickpocket stream only exists for player toons).
    db.get_conn().execute(
        "UPDATE objects SET is_human_controlled = 1 WHERE id = ?", (ACTOR,)
    )
    yield
    db.close_db()
    events.reset_subscribers()
    pronouns.reset()


async def _run_ours(text: str, conn_state: dict) -> None:
    from daydream import parser, verbs

    lp = await parser.parse_line(ACTOR, text, pending=conn_state.get("clarify"))
    conn_state["clarify"] = lp.clarify
    assert lp.error is None, f"our parse error on {text!r}: {lp.error}"
    for p in lp.commands:
        await verbs.execute_command(
            ACTOR, p.verb, p.dobj_id, p.iobj_id, p.args, dobj_name=p.dobj_name
        )


def _our_room_name() -> str:
    from daydream import objects

    rid = objects.get(ACTOR).location_id
    return ORACLE_MAP["rooms"].get(rid, rid)


def _our_inventory() -> set[str]:
    """Direct carried things plus the contents of carried open containers,
    names mapped to the original's, lowercased — the same flattening the
    real game's `i` listing performs."""
    from daydream import objects

    names: set[str] = set()

    def add(thing) -> None:
        mapped = ORACLE_MAP["things"].get(thing.id, thing.name)
        names.add(mapped.lower())
        if objects.contents_visible(thing):
            for inner in objects.contents(thing.id, kind="thing"):
                add(inner)

    for thing in objects.contents(ACTOR, kind="thing"):
        add(thing)
    return names


def _is_attack(cmd: str) -> bool:
    word = cmd.split()[0].lower()
    return word in ("kill", "attack", "fight", "stab", "smash")


async def test_walkthrough_state_matches_the_real_game(our_engine):
    from daydream import worldstate

    seed = int(os.environ.get("DAYDREAM_ZORK_ORACLE_SEED", "4"))
    oracle = zork_oracle.Oracle(_story, seed=seed, dfrotz=_dfrotz)
    conn_state: dict = {"clarify": None}
    try:
        for seg in DATASET["segments"]:
            steps = [s["cmd"] for s in seg["commands"]]
            i = 0
            while i < len(steps):
                cmd = steps[i]
                await _run_ours(cmd, conn_state)
                if _is_attack(cmd):
                    oracle.attack_until_dead(cmd)
                    # Our dataset's surplus `again`s are OUR seed's blow
                    # count; the real fight already resolved. Replay them
                    # on our side only.
                    while i + 1 < len(steps) and steps[i + 1].lower() in ("again", "g"):
                        i += 1
                        await _run_ours(steps[i], conn_state)
                else:
                    oracle.send(cmd)
                i += 1

            where = f"after segment {seg['name']!r} (real seed {seed})"
            real_room = oracle.room()
            assert real_room.lower() == _our_room_name().lower(), (
                f"{where}: real room {real_room!r} != ours {_our_room_name()!r}")
            real_score = oracle.score()
            ours_score = worldstate.score(WORLD)
            assert real_score == ours_score, (
                f"{where}: real score {real_score} != ours {ours_score}")
            real_inv = oracle.inventory()
            ours_inv = _our_inventory()
            assert real_inv == ours_inv, (
                f"{where}: real inventory {sorted(real_inv)} != ours {sorted(ours_inv)}")
    finally:
        oracle.close()

    assert worldstate.score(WORLD) == 350
