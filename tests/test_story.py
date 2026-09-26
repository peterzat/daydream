"""The story layer's primitives (SPEC 2026-09-26 criteria 2, 4-9, 11, 12, 15),
driven through the real parser -> executor over a small format-2 fixture
world (tests/data/story_fixture.json) with a fake clock and zero LLM calls."""

import copy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from daydream import (
    collect,
    db,
    director,
    events,
    knowledge,
    objects,
    story,
    variants,
    village,
    worldclock,
    worldstate,
)
from daydream.llm import format2
from tests.story_helpers import FIXTURE, WORLD, at, load, narrations, player, say

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def world(tmp_path, monkeypatch):
    spy = AsyncMock(side_effect=AssertionError("story primitives make no LLM calls"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    at("2026-10-01T10:00:00+00:00")
    load(tmp_path)
    yield spy
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


async def _start(actor: str) -> None:
    await say(actor, "light lamp")
    assert village.running(WORLD)


# ---- validation ---------------------------------------------------------------


def test_fixture_validates():
    format2.validate_envelope2(copy.deepcopy(FIXTURE))


@pytest.mark.parametrize("mutate,needle", [
    (lambda e: e["arcs"]["moth"]["endings"].pop("kept"), "at least two endings"),
    (lambda e: e["arcs"]["moth"]["beats"]["hob-notices"].pop("topic"), "needs a 'topic'"),
    (lambda e: e["arcs"]["moth"]["beats"]["hear-story"].update(after=["nope"]), "unknown beat"),
    (lambda e: next(r for r in e["rules"] if r["on"] == "give")["do"][1].update(
        name="unknown"), "undeclared player counter"),
    (lambda e: e["arcs"]["moth"]["endings"]["home"]["do"].append(
        {"kind": "kill_actor"}), "never fail states"),
    (lambda e: e["time"].update(start_flag="NOPE"), "start_flag"),
    (lambda e: e["storylets"].append({"id": "x", "at": "noon", "room": "r-green",
                                      "text": "x"}), "unknown phase"),
    (lambda e: e["collectibles"].append({"id": "g-x", "name": "x", "text": "x",
                                         "page": "p-none"}), "declared page"),
    (lambda e: e["toons"][0]["properties"]["schedule"].update(dusk="r-nowhere"),
     "unknown room"),
])
def test_story_sections_fail_loud(mutate, needle):
    env = copy.deepcopy(FIXTURE)
    mutate(env)
    with pytest.raises(format2.Format2ValidationError, match=needle):
        format2.validate_envelope2(env)


# ---- real time (criterion 4) ---------------------------------------------------


async def test_no_day_cycle_before_time_starts():
    ada = player(1, "Ada", "r-green")
    at("2026-10-01T19:00:00+00:00")
    before = events.max_seq()
    await say(ada, "look")
    assert village.phase(WORLD) == "stopped"
    assert "lamps come on" not in " ".join(narrations(before))
    assert story.arc_status(WORLD, "moth") == "dormant"


async def test_dusk_fires_once_per_day_and_brings_the_first_guest():
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    assert village.day(WORLD) == 1 and village.phase(WORLD) == "day"
    at("2026-10-01T18:05:00+00:00")
    before = events.max_seq()
    await say(ada, "look")
    text = " ".join(narrations(before))
    assert text.count("lamps come on") == 1
    assert story.arc_status(WORLD, "moth") == "open"  # the `first` arrival
    assert objects.get("t-moth").location_id == "r-lane"
    # A later command the same evening fires nothing again.
    at("2026-10-01T19:00:00+00:00")
    before = events.max_seq()
    await say(ada, "look")
    assert "lamps come on" not in " ".join(narrations(before))


async def test_restart_neither_skips_nor_double_fires(tmp_path):
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    path = Path(db.get_conn().execute("PRAGMA database_list").fetchone()["file"])
    db.close_db()
    # Server "down" across dusk; back up at 19:00.
    at("2026-10-01T19:00:00+00:00")
    from daydream import config

    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    assert village.catch_up(WORLD) == 1  # dusk, processed on the way back up
    assert worldstate.get(WORLD, "dusk_done:2026-10-01") is True
    db.close_db()
    db.init_live(path=path, migrations_dir=config.MIGRATIONS_DIR)
    assert village.catch_up(WORLD) == 0  # a second restart re-fires nothing


async def test_missed_days_catch_up_in_order_and_time_ends_arcs():
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    at("2026-10-01T18:05:00+00:00")
    village.catch_up(WORLD)
    assert story.arc_status(WORLD, "moth") == "open"
    # Nobody plays for three days: dawns and dusks all process, once each,
    # and the moth's timed ending (after 2 days) comes due at a dusk.
    at("2026-10-04T12:00:00+00:00")
    n = village.catch_up(WORLD)
    assert n == 1 + 4 + 4 + 2  # night 10-01; four each 10-02/03; dawn+day 10-04
    assert story.ending_of(WORLD, "moth") == "kept"
    assert all(worldstate.get(WORLD, f"dusk_done:2026-10-0{d}") for d in (1, 2, 3))
    assert village.day(WORLD) == 4


async def test_early_dusk_holds_and_blocks_the_same_day_wall_dusk():
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    from daydream.skills import effects

    effects.dispatch_effects([{"kind": "run_phase", "phase": "dusk"}], actor_id=ada,
                             room_id="r-green", world_id=WORLD,
                             allowed=effects.RULE_KINDS)
    assert village.phase(WORLD) == "dusk"  # held until the next boundary
    assert story.arc_status(WORLD, "moth") == "open"
    at("2026-10-01T18:30:00+00:00")
    before = events.max_seq()
    village.catch_up(WORLD)
    assert "lamps come on" not in " ".join(narrations(before))


async def test_schedules_move_npcs_by_phase():
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    assert objects.get("t-hob").location_id == "r-green"
    at("2026-10-01T18:05:00+00:00")
    village.catch_up(WORLD)
    assert objects.get("t-hob").location_id == "r-lane"
    at("2026-10-01T22:00:00+00:00")
    village.catch_up(WORLD)
    assert objects.get("t-hob").location_id == "r-mill"


def test_story_rolls_never_key_on_turn():
    a = worldstate.rng_stable(WORLD, "director:x").random()
    worldstate.advance_turn(WORLD)
    assert worldstate.rng_stable(WORLD, "director:x").random() == a


# ---- the director (criterion 5) --------------------------------------------------


async def test_seeded_choice_is_deterministic_and_out_of_set_changes_nothing():
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    elig = director.eligible_events(WORLD, "night", "2026-10-01")
    assert {s["id"] for s in elig} == {"owl", "fox"}
    seeded = director.choose_event(WORLD, "2026-10-01", "night")
    assert director.choose_event(WORLD, "2026-10-01", "night")["id"] == seeded["id"]
    # An LLM answer outside the eligible set is ignored: the seeded pick stands.
    assert director.choose_event(WORLD, "2026-10-01", "night",
                                 pick="dragon")["id"] == seeded["id"]
    other = "fox" if seeded["id"] == "owl" else "owl"
    assert director.choose_event(WORLD, "2026-10-01", "night", pick=other)["id"] == other


async def test_llm_ranking_uses_the_background_class(monkeypatch):
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    seen = {}

    async def fake(**kw):
        seen.update(kw)
        return {"choice": "dragon"}

    monkeypatch.setattr("daydream.llm.client.acompletion_json", fake)
    picks = await director.llm_picks(WORLD, "2026-10-01", "night")
    assert seen["gate"] == "background" and seen["purpose"] == "director"
    enum = seen["response_format"]["json_schema"]["schema"]["properties"]["choice"]["enum"]
    assert set(enum) == {"owl", "fox"}
    assert picks["event"] is None  # out-of-set -> treated as an outage


# ---- arcs, beats, endings, ask (criteria 2, 6, 15) --------------------------------


async def _moth_open(ada):
    home = objects.get(ada).location_id
    objects.move(ada, "r-green")  # the lamp that starts time is on the green
    await _start(ada)
    objects.move(ada, home)
    at("2026-10-01T18:05:00+00:00")
    village.catch_up(WORLD)


async def test_ask_lists_and_advances_beats_deterministically():
    ada = player(1, "Ada", "r-green")
    await _moth_open(ada)
    objects.move(ada, "r-lane")  # Hob is on the lane at dusk
    listed = " ".join(await say(ada, "ask hob"))
    assert "the moth" in listed and "the lamps" in listed
    got = " ".join(await say(ada, "ask hob about the moth"))
    assert "wants a lamp" in got
    assert story.beat_done(WORLD, "moth", "hob-notices")
    assert story.pflag(WORLD, ada, "GREETED")
    assert ada in story.arc_state(WORLD, "moth")["helpers"]
    # The beat is spent: asking again no longer offers it.
    assert "the moth" not in " ".join(await say(ada, "ask hob"))


async def test_stale_or_unready_beats_change_nothing():
    ada = player(1, "Ada", "r-green")
    await _moth_open(ada)
    # hear-story requires hob-notices first.
    assert story.advance_beat(WORLD, "moth", "hear-story", ada, "r-lane") is None
    assert not story.beat_done(WORLD, "moth", "hear-story")
    assert story.advance_beat(WORLD, "moth", "no-such-beat", ada, "r-lane") is None


async def test_per_player_beats_and_endings_and_the_chronicle():
    ada = player(1, "Ada", "r-lane")
    bo = player(2, "Bo", "r-lane")
    await _moth_open(ada)
    await say(ada, "ask hob about the moth")
    await say(ada, "ask moth about home")
    assert story.beat_done(WORLD, "moth", "hear-story", by=ada)
    assert not story.beat_done(WORLD, "moth", "hear-story", by=bo)
    assert "porch light" in " ".join(await say(bo, "ask moth about home"))
    ledger_empty = " ".join(await say(ada, "go west") + await say(ada, "read ledger"))
    assert "No hours have come home yet" in ledger_empty
    story.close_arc(WORLD, "moth", "home", ada, "r-green")
    assert story.ending_of(WORLD, "moth") == "home"
    assert objects.get("t-moth").location_id is None  # gone home
    assert any(o.name == "seedling" for o in objects.contents(ada, kind="thing"))
    text = " ".join(await say(ada, "read ledger"))
    assert "Ada and Bo lit a lamp for the moth hour" in text
    # A closed arc can't close again or reopen.
    assert story.close_arc(WORLD, "moth", "kept") is None
    assert story.open_arc(WORLD, "moth") is None


async def test_topic_answers_vary_without_verbatim_repeats():
    ada = player(1, "Ada", "r-green")
    told = [" ".join(await say(ada, "ask hob about the lamps")) for _ in range(9)]
    for i in range(2, len(told)):
        assert told[i] not in (told[i - 1], told[i - 2]), told


def test_variant_picker_window():
    opts = ["a", "b", "c", "d"]
    seq = [variants.pick(WORLD, "k", opts, "r-green") for _ in range(20)]
    for i in range(3, len(seq)):
        assert seq[i] not in seq[i - 3:i]
    two = [variants.pick(WORLD, "k2", ["x", "y"], "r-green") for _ in range(6)]
    assert two in (["x", "y"] * 3, ["y", "x"] * 3)


# ---- after-hooks + gossip + relationships (criteria 7, 8, 9) ----------------------


async def test_after_hook_follows_a_successful_give_and_gossip_spreads():
    ada = player(1, "Ada", "r-lane")
    await say(ada, "take oats")
    objects.move(ada, "r-mill")
    wynn = objects.get("t-wynn")
    hob = objects.get("t-hob")
    before = events.max_seq()
    await say(ada, "give oats to wynn")
    # Normal handling ran (the oats moved) AND the after-hook ran.
    assert objects.get("o-oats").location_id == "t-wynn"
    assert story.pcounter(WORLD, ada, "favors") == 1
    assert story.rel(WORLD, "t-wynn", ada) == 2
    assert any(e.kind == "fact_added" for e in events.fetch_since(before))
    # Wynn knows at once; Hob only after the 30-minute gossip interval.
    assert any("Ada brought Wynn the oats" in f["text"]
               for f in knowledge.known_facts(wynn, ada))
    at("2026-10-01T10:29:00+00:00")
    assert not any("oats" in f["text"] for f in knowledge.known_facts(hob, ada))
    at("2026-10-01T10:31:00+00:00")
    assert any("Ada brought Wynn the oats" in f["text"]
               for f in knowledge.known_facts(hob, ada))
    assert knowledge.npc_knows(WORLD, "t-hob", "gave-oats", about=ada)


async def test_after_hook_does_not_fire_on_a_refused_give():
    ada = player(1, "Ada", "r-lane")
    await say(ada, "take oats")
    objects.move(ada, "r-green")
    await say(ada, "give oats to hob")  # Hob doesn't want them: declined
    assert objects.get("o-oats").location_id == ada
    assert story.pcounter(WORLD, ada, "favors") == 0
    assert not knowledge.deed_facts(WORLD)


async def test_relationships_are_per_player():
    ada = player(1, "Ada", "r-lane")
    bo = player(2, "Bo", "r-lane")
    await say(ada, "take oats")
    objects.move(ada, "r-mill")
    await say(ada, "give oats to wynn")
    assert story.rel(WORLD, "t-wynn", ada) == 2
    assert story.rel(WORLD, "t-wynn", bo) == 0
    assert story.relationship_label(WORLD, "t-wynn", bo) == "a stranger"
    story.adjust_rel(WORLD, "t-wynn", ada, 1)
    assert story.relationship_label(WORLD, "t-wynn", ada) == "a friend"
    # World-scoped state is untouched by per-player state.
    assert worldstate.score(WORLD) == 0


# ---- collectibles (criterion 12) ------------------------------------------------------


async def test_daily_finds_are_per_player_and_fill_the_book():
    ada = player(1, "Ada", "r-green")
    bo = player(2, "Bo", "r-green")
    await _start(ada)
    await say(ada, "look")
    await say(bo, "look")
    mine = [o for o in objects.things_where_property(WORLD, "private_to", ada)]
    theirs = [o for o in objects.things_where_property(WORLD, "private_to", bo)]
    assert len(mine) == 2 and len(theirs) == 2
    # Bo never sees Ada's glints.
    bo_scope = {o.id for o in objects.in_scope(bo)}
    assert not bo_scope & {o.id for o in mine}
    for o in mine:
        objects.move(ada, o.location_id)
        await say(ada, "take glint")
    assert collect.count(WORLD, ada) == 2
    assert collect.count(WORLD, bo) == 0
    book = collect.book(WORLD, ada)
    assert book["title"] == "Book of Glints" and book["found"] == 2
    # Next day brings new finds for each player regardless of the other.
    at("2026-10-02T09:00:00+00:00")
    await say(ada, "look")
    assert len(objects.things_where_property(WORLD, "private_to", ada)) == 2


async def test_completing_a_page_grants_its_reward_once():
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    for cid in ("g-kettle", "g-sneeze"):
        collect.grant(WORLD, ada, cid, "r-green")
    assert story.pcounter(WORLD, ada, "favors") == 5
    collect.grant(WORLD, ada, "g-kettle", "r-green")  # a repeat changes nothing
    assert story.pcounter(WORLD, ada, "favors") == 5
    page = next(p for p in collect.book(WORLD, ada)["pages"] if p["id"] == "p-first")
    assert page["complete"] and page["reward_text"] == "The page glows warm."
