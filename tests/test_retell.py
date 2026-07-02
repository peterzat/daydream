"""The retell layer (SPEC 2026-07-02 criterion 13): unit coverage for the
gates — world opt-in, the env kill-switch, eligibility heuristics, strict
validation with authored-text fallback, the verbatim mark, and the
rules-dispatch integration under a mocked LLM."""

from unittest.mock import AsyncMock

import pytest

from daydream import db, events, objects, retell, verbs, worldstate
from daydream.llm.client import LLMUnavailable

pytestmark = pytest.mark.tier_short

WORLD = "w-retell"
ACTOR = "t-r-actor"

ELIGIBLE = (
    "The water level behind the dam falls away with a long, diminishing "
    "sigh; the reservoir gives up its bed."
)
VOICE = {
    "register": "Dry, precise, unhurried.",
    "examples": ["This is a forest, with trees in all directions."],
    "retell": {"enabled": True, "banlist": ["cozy"], "max_ratio": 1.6},
}


@pytest.fixture()
def retell_world(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_RETELL_ENABLED", "1")
    db.close_db()
    events.reset_subscribers()
    db.init_live(path=tmp_path / "retell.db")
    db.get_conn().execute(
        "INSERT INTO worlds (id, name, slug, aesthetic_seed) VALUES "
        f"('{WORLD}', 'Retell', 'retell', 'seed')"
    )
    worldstate.set(WORLD, "voice", VOICE)
    yield
    db.close_db()
    events.reset_subscribers()


def mock_llm(monkeypatch, reply):
    if isinstance(reply, Exception):
        m = AsyncMock(side_effect=reply)
    else:
        m = AsyncMock(return_value=reply)
    monkeypatch.setattr("daydream.llm.client.acompletion_json", m)
    return m


# ---- eligibility -------------------------------------------------------------


def test_mechanical_shapes_are_verbatim_zones():
    assert retell.eligible(ELIGIBLE)
    assert not retell.eligible("Click.")  # short = mechanics
    assert not retell.eligible(
        'A hollow voice says "Fool." and the walls agree with it entirely.'
    )  # quoted speech
    assert not retell.eligible(
        "Abandon every hope all ye who enter here!\nThe gate is open."
    )  # shaped text
    assert not retell.eligible(
        "Oh dear, it appears that the smell in this room was coal gas. ** BOOM **"
    )  # shouting beat


def test_proper_noun_extraction_skips_sentence_starts():
    nouns = retell.proper_nouns(
        "The sluice gates open. Water pours through Flood Control Dam and "
        "the Frigid River takes it from there."
    )
    assert {"Flood", "Control", "Dam", "Frigid", "River"} <= nouns
    assert "Water" not in nouns  # sentence-initial
    assert "The" not in nouns


# ---- validation ---------------------------------------------------------------


def test_validation_gates():
    cfg = VOICE["retell"]
    original = "The reservoir gives up its bed below Flood Control Dam #3, all 112 spans of it."
    ok = "Below Flood Control Dam #3 the water surrenders its bed, all 112 spans of it."
    assert retell.validate(original, ok, cfg)
    assert not retell.validate(original, None, cfg)
    assert not retell.validate(original, original, cfg)  # must differ
    assert not retell.validate(original, "Too short.", cfg)  # gutted
    assert not retell.validate(original, ok * 4, cfg)  # ratio blowout
    assert not retell.validate(  # dropped proper noun
        original, "Below the dam the water surrenders its bed, all 112 spans of it.", cfg)
    assert not retell.validate(  # digits changed
        original, "Below Flood Control Dam #3 the water surrenders its bed, all 12 spans.", cfg)
    assert not retell.validate(  # banlist
        original, "Below Flood Control Dam #3, a cozy 112 spans give up their bed.", cfg)


# ---- maybe_retell -------------------------------------------------------------


async def test_disabled_world_makes_no_call(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_RETELL_ENABLED", "1")
    db.close_db()
    db.init_live(path=tmp_path / "off.db")
    spy = mock_llm(monkeypatch, AssertionError("no call expected"))
    assert await retell.maybe_retell("w-none", ELIGIBLE) == ELIGIBLE
    assert spy.await_count == 0
    db.close_db()


async def test_env_killswitch_wins_over_world_config(retell_world, monkeypatch):
    monkeypatch.setenv("DAYDREAM_RETELL_ENABLED", "0")
    spy = mock_llm(monkeypatch, AssertionError("no call expected"))
    assert await retell.maybe_retell(WORLD, ELIGIBLE) == ELIGIBLE
    assert spy.await_count == 0


async def test_valid_candidate_replaces_text(retell_world, monkeypatch):
    retold = (
        "With a long, diminishing sigh the water behind the dam falls away, "
        "and the reservoir gives up its bed."
    )
    mock_llm(monkeypatch, {"text": retold})
    assert await retell.maybe_retell(WORLD, ELIGIBLE) == retold


async def test_invalid_candidate_falls_back(retell_world, monkeypatch):
    mock_llm(monkeypatch, {"text": "A cozy little pond drains."})
    assert await retell.maybe_retell(WORLD, ELIGIBLE) == ELIGIBLE


async def test_backend_failure_falls_back(retell_world, monkeypatch):
    mock_llm(monkeypatch, LLMUnavailable("down"))
    assert await retell.maybe_retell(WORLD, ELIGIBLE) == ELIGIBLE


# ---- effect-list + dispatch integration ---------------------------------------


async def test_verbatim_mark_is_absolute(retell_world, monkeypatch):
    spy = mock_llm(monkeypatch, {"text": "should never be used"})
    effs = [{"kind": "narrate", "text": ELIGIBLE, "verbatim": True},
            {"kind": "set_flag", "name": "X", "value": True}]
    out = await retell.retell_effects(WORLD, effs)
    assert out[0]["text"] == ELIGIBLE
    assert out[1] == effs[1]
    assert spy.await_count == 0


async def test_rule_narration_is_retold_through_dispatch(retell_world, monkeypatch):
    from daydream import rules

    retold = (
        "With a long, diminishing sigh the water behind the dam falls away; "
        "the reservoir gives up its bed."
    )
    mock_llm(monkeypatch, {"text": retold})
    room = objects.spawn(WORLD, "room", "Test Room", None,
                         properties={"slug": "t", "seed": "t", "exits": {}},
                         object_id="r-retell")
    actor = objects.spawn(WORLD, "toon", "Tester", room.id, object_id=ACTOR,
                          properties={})
    thing = objects.spawn(
        WORLD, "thing", "stone", room.id, object_id="o-r-stone",
        properties={"seed": "a stone", "verbs": ["examine"],
                    "rules": [{"on": "examine",
                               "do": [{"kind": "narrate", "text": ELIGIBLE}]}]},
    )
    fired = await rules.dispatch(actor, "examine", thing, None, room_id=room.id)
    assert fired
    texts = [e.payload.get("text") for e in events.fetch_since(0)
             if e.kind == "narrate"]
    assert retold in texts and ELIGIBLE not in texts


async def test_spine_unchanged_when_llm_absent(retell_world, monkeypatch):
    """Criterion 13's vLLM-down clause: same rule, backend down — the
    authored text lands, nothing raises, the verb completes."""
    from daydream import rules

    mock_llm(monkeypatch, LLMUnavailable("down"))
    room = objects.spawn(WORLD, "room", "Test Room 2", None,
                         properties={"slug": "t2", "seed": "t", "exits": {}},
                         object_id="r-retell-2")
    actor = objects.spawn(WORLD, "toon", "Tester2", room.id,
                          object_id="t-r-actor-2", properties={})
    thing = objects.spawn(
        WORLD, "thing", "pebble", room.id, object_id="o-r-pebble",
        properties={"seed": "a pebble", "verbs": ["examine"],
                    "rules": [{"on": "examine",
                               "do": [{"kind": "narrate", "text": ELIGIBLE}]}]},
    )
    fired = await rules.dispatch(actor, "examine", thing, None, room_id=room.id)
    assert fired
    texts = [e.payload.get("text") for e in events.fetch_since(0)
             if e.kind == "narrate"]
    assert ELIGIBLE in texts


async def test_execute_command_still_ticks_with_retell_on(retell_world, monkeypatch):
    """The clock contract survives the async dispatch conversion."""
    mock_llm(monkeypatch, LLMUnavailable("down"))
    room = objects.spawn(WORLD, "room", "Tick Room", None,
                         properties={"slug": "t3", "seed": "t", "exits": {}},
                         object_id="r-retell-3")
    objects.spawn(WORLD, "toon", "Ticker", room.id, object_id="t-ticker",
                  properties={})
    before = worldstate.turn(WORLD)
    await verbs.execute_command("t-ticker", "look")
    assert worldstate.turn(WORLD) == before + 1
