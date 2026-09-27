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
from tests.story_helpers import FIXTURE, WORLD, at, load, narrations, player, say, talk

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


async def test_the_first_daily_find_is_one_exit_from_the_player():
    """Playtest 2026-09-26: a newcomer's finds landed in rooms they never
    visited. The first find of the day is placed one exit from where the
    player stands (r-mill and r-lane are the fixture's neighbors of r-green)."""
    from daydream import collect as c

    assert c._near("r-green", ["r-green", "r-mill", "r-lane"], 1) == ["r-lane", "r-mill"]
    assert c._near("r-mill", ["r-green", "r-mill", "r-lane"], 2) == ["r-lane"]
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    objects.move(ada, "r-mill")
    await say(ada, "look")
    spawned = objects.things_where_property(WORLD, "private_to", ada)
    assert any(o.location_id == "r-green" for o in spawned)   # r-mill's only neighbor
    import random
    for seed in range(25):   # the rule, not luck: the first pick is always a neighbor
        where = c._daily_rooms(objects.get(ada), ["r-green", "r-mill", "r-lane"], 2,
                               random.Random(seed))
        assert where[0] == "r-green" and len(set(where)) == 2


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


async def test_daily_finds_favor_the_page_nearest_completion():
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    collect.grant(WORLD, ada, "g-rain", "r-green")   # one of p-second's three
    assert collect.focus_page(WORLD, ada) == "p-second"
    await say(ada, "look")
    spawned = objects.things_where_property(WORLD, "private_to", ada)
    pages = {collect.items(WORLD)[o.properties["collectible"]]["page"] for o in spawned}
    assert "p-second" in pages


async def test_a_second_dreamseed_from_another_source_is_never_dropped():
    """Generative spawns dedup on the SAME provenance only: a page reward's
    dreamseed arrives even while an arc's dreamseed is still carried."""
    from daydream.skills import effects

    ada = player(1, "Ada", "r-green")
    for src in ("arc:one", "page:two", "arc:one"):
        effects.dispatch_effects(
            [{"kind": "spawn_template", "template": "seedling", "location_id": ada,
              "generated_by": src}],
            actor_id=ada, room_id="r-green", world_id=WORLD, allowed=effects.RULE_KINDS)
    seeds = [o for o in objects.contents(ada, kind="thing") if o.name == "seedling"]
    assert len(seeds) == 2   # one per source; the repeat of arc:one is deduped


async def test_an_arc_opened_during_a_catch_up_records_its_own_day():
    """A dusk processed late (the server was down for days) opens its arc on
    THAT dusk's village day, not the day the catch-up ran."""
    ada = player(1, "Ada", "r-green")
    await _start(ada)
    worldstate.set(WORLD, "director:first_arrival_done", True)  # no `first` shortcut
    story.close_arc(WORLD, "moth", "kept") if story.arc_status(WORLD, "moth") == "open" else None
    at("2026-10-04T12:00:00+00:00")   # days 1-3's dusks all processed now
    village.catch_up(WORLD)
    days = sorted(story.arc_state(WORLD, a).get("opened_day") for a in ("moth", "reed"))
    assert days[0] == 1                # the day-1 dusk opened the first guest
    assert days[1] in (2, 3)           # the second only after the cap freed


async def test_knows_honors_an_authored_facts_own_condition():
    """The `knows` condition applies the fact's `if`, exactly as the dialogue
    context does: a gated fact is not known while its gate is shut."""
    assert knowledge.npc_knows(WORLD, "t-hob", "lamps-twelve")      # ungated
    assert story.arc_status(WORLD, "moth") != "open"
    assert not knowledge.npc_knows(WORLD, "t-hob", "moth-lost")    # arc not open
    story.open_arc(WORLD, "moth", None, None)
    assert knowledge.npc_knows(WORLD, "t-hob", "moth-lost")


async def test_a_topic_answer_is_the_askers_and_the_room_sees_one_line():
    """Playtest 2026-09-26: in a busy room four dreamers' answers reached
    everyone, unaddressed. The answer goes to the asker; others see one short
    line, at most once per pair every ten minutes, never the pair themselves."""
    ada = player(1, "Ada", "r-green")
    player(2, "Bo", "r-green")
    before = events.max_seq()
    await say(ada, "ask hob about the lamps")
    await say(ada, "ask hob about the lamps")
    evs = [e for e in events.fetch_since(before) if e.kind == "narrate"]
    answers = [e for e in evs if e.recipient_id == ada]
    assert len(answers) == 2
    seen_by_bo = [e.payload["text"] for e in events.fetch_since(before, recipient_for="t-bo")]
    bo_view = [e.payload["text"] for e in evs if e.recipient_id is None and e.payload.get("except") == ada]
    assert len(bo_view) == 1 and "Hob" in bo_view[0] and "Ada" in bo_view[0]
    assert all("lamp" not in t.lower() for t in bo_view)
    mine = [e.payload["text"] for e in events.fetch_since(before, recipient_for=ada)]
    assert not any(t in mine for t in bo_view)
    del seen_by_bo


async def test_talking_to_another_dreamer_is_speech_to_them():
    ada = player(1, "Ada", "r-green")
    player(2, "Bo", "r-green")
    before = events.max_seq()
    await say(ada, "talk to Bo: hello there, neighbor")
    says = [e for e in events.fetch_since(before) if e.kind == "say"]
    assert says and says[0].payload == {"text": "hello there, neighbor", "name": "Ada", "to": "Bo"}
    assert not any("much to say" in (e.payload.get("text") or "")
                   for e in events.fetch_since(before))


def test_narration_that_addresses_you_is_detected_outside_speech():
    from daydream.skills import effects
    assert effects.addresses_actor("You turn the little key.")
    assert effects.addresses_actor("They fold a small brass key into your hand, warm.")
    assert not effects.addresses_actor("Tace smiles. 'The case is yours to open now, friend.'")
    assert not effects.addresses_actor("Hob's lamps hum; 'you know,' Hob says.")
    assert not effects.addresses_actor("Down in the square, a lantern comes alight early.")


async def test_a_resting_player_sends_world_objects_home_and_keeps_keepsakes():
    """Playtest 2026-09-26: a spare pendulum and the unsent letters stranded
    in the pockets of players who left. Things with a home go back there on
    rest; a keepsake (no home) stays with the player."""
    from daydream import toons
    ada = player(1, "Ada", "r-lane")
    await say(ada, "take oats")
    objects.set_property("o-oats", "home", "r-lane")
    kept = objects.spawn(WORLD, "thing", "pressed flower", ada, prototype_id=objects.PROTO_THING)
    objects.move(ada, "r-mill")
    toons.kick_slot(1)
    assert objects.get("o-oats").location_id == "r-lane"
    assert objects.get(kept.id).location_id == ada


async def test_talk_that_names_a_topic_gets_the_authored_answer(monkeypatch):
    """Select, don't write (docs/REFLEXES.md): a free-form line naming one of
    an NPC's topics answers with the authored line and makes no LLM call;
    plural or singular, as whole words; a line naming none goes to the model."""
    from unittest.mock import AsyncMock
    spy = AsyncMock(return_value={"gesture": "Hob nods.", "say": "Evening.", "advance": "none"})
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    ada = player(1, "Ada", "r-green")
    before = events.max_seq()
    await talk(ada, "t-hob", "Hello Hob! Tell me about your lamps, would you?")
    said = narrations(before)
    assert any(t in " ".join(said) for t in ("Twelve lamps", "hum at dusk", "has a name"))
    assert spy.await_count == 0
    hob = objects.get("t-hob")
    assert story.match_in_talk(hob, ada, "is that a lamp?")["label"] == "the lamps"
    assert story.match_in_talk(hob, ada, "lampshades are nice") is None
    await talk(ada, "t-hob", "how was your day?")
    assert spy.await_count >= 1


def test_beats_and_endings_may_carry_others_and_to():
    env = copy.deepcopy(FIXTURE)
    env["arcs"]["moth"]["beats"]["hob-notices"]["others"] = "{actor} and Hob talk about the moth."
    env["arcs"]["moth"]["endings"]["home"]["to"] = "everyone"
    format2.validate_envelope2(copy.deepcopy(env))
    env["arcs"]["moth"]["beats"]["hob-notices"]["others"] = ""
    with pytest.raises(Exception, match="others"):
        format2.validate_envelope2(copy.deepcopy(env))
    env["arcs"]["moth"]["beats"]["hob-notices"]["others"] = "{actor} listens."
    env["arcs"]["moth"]["endings"]["home"]["to"] = "@actor"
    with pytest.raises(Exception, match="to must be"):
        format2.validate_envelope2(copy.deepcopy(env))
