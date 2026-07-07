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
with `attack_until_dead` and skips the dataset's surplus `again`s.

The real side replays each segment inside a Z-machine save/restore bracket
with BOUNDED RETRY. Real Zork's ambient RNG (the wandering thief's route,
his thefts and ambushes, every melee roll) makes a single straight-line
replay of ~400 commands a lottery: an empirical 400-seed sweep produced
zero clean runs (fight deaths 25%, fight stalls 16%, den-loot variance
33%, mid-walk ambushes 14%, floor thefts 10%). Restore rewinds the game
but NOT the interpreter's RNG stream, so a retried segment samples fresh
rolls — the retry loop asks the honest differential question: CAN the
real game follow this walkthrough, and when it does, does its state agree
with ours at every checkpoint? A divergence that survives every attempt
(DAYDREAM_ZORK_ORACLE_RETRIES, default 12) is a genuine fidelity failure,
not bad luck. Our engine's side is seeded-deterministic and replays
exactly once. Parse failures never retry — a command the real game
rejects is a dataset bug regardless of RNG.

Without dfrotz or a story file the whole module skips with a named reason
(fidelity relaxation R8: the harness is optional, never load-bearing).
Setup: bin/zork-oracle-bootstrap; export DAYDREAM_ZORK_ORACLE_STORY.
The real RNG is pinned via dfrotz -s (DAYDREAM_ZORK_ORACLE_SEED, default
4); ratification records the seed and the per-segment retry counts."""

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


def _replay_real_segment(oracle: "zork_oracle.Oracle", steps: list[str]) -> None:
    """One real-side attempt at a segment. Fights resolve outcome-faithfully
    (attack_until_dead); the dataset's surplus `again`s are OUR seed's blow
    count and are skipped on the real side."""
    i = 0
    while i < len(steps):
        cmd = steps[i]
        if _is_attack(cmd):
            oracle.attack_until_dead(cmd)
            while i + 1 < len(steps) and steps[i + 1].lower() in ("again", "g"):
                i += 1
        else:
            oracle.send(cmd)
        i += 1


async def test_walkthrough_state_matches_the_real_game(our_engine):
    from daydream import worldstate

    seed = int(os.environ.get("DAYDREAM_ZORK_ORACLE_SEED", "4"))
    max_attempts = int(os.environ.get("DAYDREAM_ZORK_ORACLE_RETRIES", "12"))
    oracle = zork_oracle.Oracle(_story, seed=seed, dfrotz=_dfrotz)
    conn_state: dict = {"clarify": None}
    retry_log: list[str] = []
    try:
        for seg in DATASET["segments"]:
            steps = [s["cmd"] for s in seg["commands"]]

            # OUR side: seeded-deterministic, replayed exactly once. The
            # surplus `again`s after an attack are our fight's blow count.
            i = 0
            while i < len(steps):
                await _run_ours(steps[i], conn_state)
                if _is_attack(steps[i]):
                    while i + 1 < len(steps) and steps[i + 1].lower() in ("again", "g"):
                        i += 1
                        await _run_ours(steps[i], conn_state)
                i += 1
            ours = (
                _our_room_name().lower(),
                worldstate.score(WORLD),
                _our_inventory(),
            )

            # REAL side: bounded retry inside a save/restore bracket. Restore
            # rewinds the game but not the interpreter RNG, so each attempt
            # samples fresh thief/melee rolls (see module docstring).
            where = f"segment {seg['name']!r} (real seed {seed})"
            last_err = None
            for attempt in range(1, max_attempts + 1):
                mark = oracle.checkpoint()
                try:
                    _replay_real_segment(oracle, steps)
                    real_room, real_score, real_inv = oracle.state()
                except zork_oracle.OracleParseError:
                    raise  # the real game rejected a command: dataset bug, never RNG
                except AssertionError as e:
                    last_err = str(e)  # death / unwinnable fight: retryable
                    oracle.restore(mark)
                    continue
                real = (real_room.lower(), real_score, real_inv)
                if real == ours:
                    if attempt > 1:
                        retry_log.append(f"{seg['name']}: {attempt} attempts")
                    break
                last_err = (
                    f"real (room={real_room!r}, score={real_score}, "
                    f"inv={sorted(real_inv)}) != ours (room={ours[0]!r}, "
                    f"score={ours[1]}, inv={sorted(ours[2])})"
                )
                oracle.restore(mark)
            else:
                pytest.fail(
                    f"{where}: diverged on all {max_attempts} attempts — a real"
                    f" fidelity gap, not RNG. Last: {last_err}"
                )
    finally:
        oracle.close()

    assert worldstate.score(WORLD) == 350
    if retry_log:
        print(f"\noracle segment retries (seed {seed}): " + "; ".join(retry_log))
