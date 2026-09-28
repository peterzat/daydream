"""Grounded dialogue for voice-sheet NPCs (SPEC 2026-09-26 criteria 6, 7,
8, 10), with the local model mocked: what the prompt carries, how the reply
is chosen, and how a talk turn moves the story (or, when the offered moment
is stale or was never offered, changes nothing)."""

import pytest

from daydream import db, events, objects, story, worldclock
from daydream import dialogue as dlg
from tests.story_helpers import WORLD, at, load, narrations, player, say, talk

pytestmark = pytest.mark.tier_short


@pytest.fixture(autouse=True)
def world(tmp_path):
    at("2026-10-01T10:00:00+00:00")
    load(tmp_path)
    yield
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def _mock(monkeypatch, *replies):
    calls = []
    it = iter(replies * 10)

    async def fake(**kw):
        calls.append(kw)
        r = next(it)
        if isinstance(r, BaseException):
            raise r
        return r

    monkeypatch.setattr("daydream.llm.client.acompletion_json", fake)
    return calls


async def _open_moth(ada):
    objects.move(ada, "r-green")
    await say(ada, "light lamp")
    at("2026-10-01T18:05:00+00:00")
    from daydream import village

    village.catch_up(WORLD)


async def test_prompt_carries_voice_state_and_the_offered_beats(monkeypatch):
    ada = player(1, "Ada", "r-green")
    await _open_moth(ada)
    objects.move(ada, "r-lane")
    calls = _mock(monkeypatch, {"gesture": "Hob grins.", "say": "Evening, Ada.", "advance": "none"})
    await talk(ada, "t-hob", "how is the evening?")
    kw = calls[0]
    assert "they/them pronouns" in kw["system"]
    assert "Ada" in kw["system"] and "Ada" in kw["user"]
    user = kw["user"]
    assert "Hob lights lamps" in user                      # the voice sheet
    assert "There are twelve lamps in the hamlet." in user  # what Hob knows
    assert "A lost moth-hour is waiting on the lane." in user  # conditional fact
    assert "to see every lamp lit by dark" in user          # current wants
    assert "Hob and Ada: a stranger" in user               # relationship
    assert "no one else exists" in user and "Wynn" in user  # the closed cast
    assert "moth/hob-notices" in user                      # the offered beat
    enum = kw["response_format"]["json_schema"]["schema"]["properties"]["advance"]["enum"]
    assert enum == ["moth/hob-notices", "none"]
    assert kw["temperature"] > 0  # prose runs warm
    assert kw["purpose"] == "dialogue"


async def test_an_offered_beat_advances_and_speaks_its_authored_line(monkeypatch):
    ada = player(1, "Ada", "r-green")
    await _open_moth(ada)
    objects.move(ada, "r-lane")
    _mock(monkeypatch, {"gesture": "Hob squints at the moth.", "say": "Well now.",
                        "advance": "moth/hob-notices"})
    before = events.max_seq()
    await talk(ada, "t-hob", "did you see the little moth?")
    text = " ".join(narrations(before))
    assert story.beat_done(WORLD, "moth", "hob-notices")
    assert "That moth wants a lamp." in text      # the authored beat line
    assert "Well now." not in text                # the model chose; the author spoke


async def test_an_unoffered_id_changes_nothing(monkeypatch):
    ada = player(1, "Ada", "r-green")
    await _open_moth(ada)
    objects.move(ada, "r-lane")
    _mock(monkeypatch, {"gesture": "Hob nods.", "say": "Lamps, lamps.", "advance": "moth/lit-for-moth"})
    before = events.max_seq()
    await talk(ada, "t-hob", "hello")
    assert not story.beat_done(WORLD, "moth", "lit-for-moth")
    assert "Lamps, lamps." in " ".join(narrations(before))


async def test_a_beat_that_went_stale_before_commit_changes_nothing(monkeypatch):
    ada = player(1, "Ada", "r-green")
    bo = player(2, "Bo", "r-lane")
    await _open_moth(ada)
    objects.move(ada, "r-lane")

    async def racing(**kw):
        # Another player completes the beat while this call is in flight.
        story.advance_beat(WORLD, "moth", "hob-notices", bo, "r-lane")
        return {"gesture": "Hob laughs.", "say": "Busy evening.", "advance": "moth/hob-notices"}

    monkeypatch.setattr("daydream.llm.client.acompletion_json", racing)
    monkeypatch.setenv("DAYDREAM_DIALOGUE_NBEST", "1")
    before = events.max_seq()
    # A line naming no topic, so the model (not the authored topic route)
    # answers and the race at commit is exercised.
    await talk(ada, "t-hob", "did you see anything odd tonight?")
    st = story.arc_state(WORLD, "moth")
    assert st["beats"]["hob-notices"]["by"] == bo      # recorded once, by Bo
    assert ada not in st["helpers"]
    assert "Busy evening." in " ".join(narrations(before))


async def test_nbest_rerank_prefers_pronoun_canon_and_fresh_openers(monkeypatch):
    ada = player(1, "Ada", "r-green")
    _mock(monkeypatch,
          {"gesture": "Hob taps her ladder.", "say": "Evening!", "advance": "none"},
          {"gesture": "Hob taps their ladder.", "say": "Evening!", "advance": "none"})
    before = events.max_seq()
    await talk(ada, "t-hob", "hello")
    text = " ".join(narrations(before))
    assert "their ladder" in text and "her ladder" not in text
    # The chosen opening is remembered and penalised next time.
    assert dlg.recent_openers(WORLD, "t-hob")
    assert dlg.score("Hob taps their ladder. 'Again!'", "Hob", "they",
                     dlg.recent_openers(WORLD, "t-hob")) > \
        dlg.score("Hob hums. 'Again!'", "Hob", "they", dlg.recent_openers(WORLD, "t-hob"))


async def test_outage_is_foggy_and_changes_nothing(monkeypatch):
    from daydream.llm import client

    ada = player(1, "Ada", "r-green")
    _mock(monkeypatch, client.LLMUnavailable("down"))
    before = events.max_seq()
    await talk(ada, "t-hob", "hello")
    assert client.FOGGY_TEXT in " ".join(narrations(before))
    assert story.rel(WORLD, "t-hob", ada) == 0


async def test_failure_lines_reach_only_the_player_who_talked(monkeypatch):
    """A foggy or refused talk is the talker's, like a reply (codereview
    2026-09-27): nobody else in the room reads it."""
    from daydream.llm import client

    ada = player(1, "Ada", "r-green")
    _mock(monkeypatch, client.LLMUnavailable("down"))
    before = events.max_seq()
    await talk(ada, "t-hob", "hello")
    await talk(ada, "t-hob", "a grimdark hello")
    told = [e for e in events.fetch_since(before) if e.kind == "narrate"]
    assert {e.payload["text"] for e in told} == {client.FOGGY_TEXT, dlg._BANNED_FALLBACK}
    assert all(e.recipient_id == ada for e in told)


async def test_gossip_reaches_another_npcs_dialogue_context_on_schedule(monkeypatch):
    """Criterion 7: after Ada gives something to Wynn, Hob's dialogue
    context names Ada's deed after the gossip interval and not before."""
    ada = player(1, "Ada", "r-lane")
    await say(ada, "take oats")
    objects.move(ada, "r-mill")
    await say(ada, "give oats to wynn")
    objects.move(ada, "r-green")
    hob = objects.get("t-hob")
    _, user, _ = dlg.build_prompt(objects.get(ada), hob, "hi", "r-green", [])
    assert "Ada brought Wynn the oats." not in user
    at("2026-10-01T10:31:00+00:00")
    _, user, _ = dlg.build_prompt(objects.get(ada), hob, "hi", "r-green", [])
    assert "Ada brought Wynn the oats." in user
    # Wynn's own context has it at once, with the warmer relationship.
    wynn = objects.get("t-wynn")
    _, wuser, _ = dlg.build_prompt(objects.get(ada), wynn, "hi", "r-mill", [])
    assert "Ada brought Wynn the oats." in wuser


async def test_relationship_in_context_is_per_player(monkeypatch):
    ada = player(1, "Ada", "r-green")
    bo = player(2, "Bo", "r-green")
    story.adjust_rel(WORLD, "t-hob", ada, 5)
    hob = objects.get("t-hob")
    _, a_user, _ = dlg.build_prompt(objects.get(ada), hob, "hi", "r-green", [])
    _, b_user, _ = dlg.build_prompt(objects.get(bo), hob, "hi", "r-green", [])
    assert "Hob and Ada: a friend" in a_user
    assert "Hob and Bo: a stranger" in b_user



def test_compose_always_attributes_and_quotes():
    assert dlg.compose("Tace", "sets down the loupe", '"Hello, friend."') == \
        "Tace sets down the loupe. 'Hello, friend.'"
    assert dlg.compose("Tace", "Tace smiles.", "") == "Tace smiles."
    assert dlg.compose("Tace", "", "Hello.") == "Tace says, 'Hello.'"


def test_a_repeated_closing_tic_is_penalized():
    recent = ["Tace smiles. 'The clock is patient, friend.'"]
    assert dlg.score("Tace nods. 'All is well, friend.'", "Tace", "they", [], recent) > \
        dlg.score("Tace nods. 'All is well.'", "Tace", "they", [], recent)



async def test_a_worn_opening_gesture_is_swapped_for_an_authored_one(monkeypatch):
    ada = player(1, "Ada", "r-green")
    hob = objects.get("t-hob")
    objects.set_property("t-hob", "drift_pools", {"default": [
        "Hob polishes a lamp glass until it squeaks.", "Hob counts the lamps under their breath."],
        # Time-of-day buckets are never borrowed as a talking gesture.
        "night": ["Hob sleeps soundly under the quilt."],
        "dawn@r-green": ["Hob snores gently."]})
    _mock(monkeypatch, {"gesture": "Hob leans on the ladder and hums.", "say": "Evening.", "advance": "none"})
    monkeypatch.setenv("DAYDREAM_DIALOGUE_NBEST", "1")
    first = " ".join(await talk(ada, "t-hob", "hi"))
    second = " ".join(await talk(ada, "t-hob", "hello again"))
    assert first.startswith("Hob leans on the ladder")
    assert not second.startswith("Hob leans on the ladder")
    assert second.startswith("Hob polishes") or second.startswith("Hob counts")
    assert hob is not None


def test_pet_names_are_dampened_after_recent_use():
    hob = objects.get("t-hob")
    recent = ["Hob smiles. 'Evening, little one.'"]
    assert dlg._dampen_pet_names(hob, "Welcome back, little one.", recent) == "Welcome back."
    assert dlg._dampen_pet_names(hob, "Little one, the lamps are lit.", recent) == "The lamps are lit."
    assert dlg._dampen_pet_names(hob, "Welcome back, little one.", []) == "Welcome back, little one."


async def test_a_local_reply_is_tagged_and_an_authored_beat_is_not(monkeypatch):
    """Provenance (docs/REFLEXES.md): the 9B's improvised line carries
    src=local in the event payload; engine and authored lines never do."""
    ada = player(1, "Ada", "r-green")
    _mock(monkeypatch, {"gesture": "Hob smiles.", "say": "Evening.", "advance": "none"})
    monkeypatch.setenv("DAYDREAM_DIALOGUE_NBEST", "1")
    before = events.max_seq()
    await talk(ada, "t-hob", "hi")
    evs = [e for e in events.fetch_since(before) if e.kind == "narrate"]
    reply = [e for e in evs if e.payload.get("src") == "local"]
    assert reply and reply[0].recipient_id == ada   # the talker's own reply
    bystander = [e for e in evs if e.payload.get("except") == ada]
    assert bystander and "Hob" in bystander[0].payload["text"]   # the room sees a conversation
    before = events.max_seq()
    await verbs_look(ada)
    assert all("src" not in e.payload for e in events.fetch_since(before) if e.kind == "narrate")


async def verbs_look(actor):
    from daydream import verbs
    await verbs.execute_command(actor, "look")


def test_flat_denials_and_self_naming_are_penalized():
    """Playtest 2026-09-26: "I do not know your name, friend" and "Tace
    remembers your name" read as a guard and a script, not a person."""
    base = dlg.score("Hob nods. 'Evening, and welcome.'", "Hob", "they", [], [])
    assert dlg.score("Hob nods. 'I do not know your name.'", "Hob", "they", [], []) > base
    assert dlg.score("Hob nods. 'Hob remembers you.'", "Hob", "they", [], []) > base


def test_one_candidate_when_the_gpu_is_busy(monkeypatch):
    from daydream.gpu import arbiter
    monkeypatch.setenv("DAYDREAM_DIALOGUE_NBEST", "2")
    monkeypatch.setattr(arbiter, "stats", lambda: {"waiting_llm": 0, "active_llm": 0,
                                                   "llm_concurrency": 3})
    assert dlg.nbest() == 2
    monkeypatch.setattr(arbiter, "stats", lambda: {"waiting_llm": 1, "active_llm": 3,
                                                   "llm_concurrency": 3})
    assert dlg.nbest() == 1


def test_a_reply_that_repeats_the_player_is_an_echo():
    heard = "I would like to spend you on purpose. Shall we watch the lanterns together?"
    assert dlg.echoes("'I would like, just once, to be spent on purpose. Shall we watch "
                      "the lanterns together?'", heard)
    # A shared name or short phrase is not an echo.
    assert not dlg.echoes("'The lanterns? Hob lights them at dusk.'", heard)
    assert not dlg.echoes("'Hello to you.'", "hello")


async def test_an_echoing_candidate_is_never_the_reply(monkeypatch):
    """Playtest 2026-09-28b: the model handed the player's line back as the
    NPC's own. An echoing candidate is dropped; another one answers, and if
    none is left the NPC listens instead."""
    ada = player(1, "Ada", "r-green")
    heard = "Would you like to sit with me and count the stars tonight?"
    _mock(monkeypatch,
          {"gesture": "Hob smiles.", "say": "Would you like to sit with me and count the stars tonight?",
           "advance": "none"},
          {"gesture": "Hob nods.", "say": "I'd like that.", "advance": "none"})
    before = events.max_seq()
    await talk(ada, "t-hob", heard)
    told = " ".join(narrations(before))
    assert "I'd like that" in told and "count the stars tonight" not in told
    _mock(monkeypatch, {"gesture": "Hob smiles.",
                        "say": "Would you like to sit with me and count the stars tonight?",
                        "advance": "none"})
    before = events.max_seq()
    await talk(ada, "t-hob", heard)
    assert dlg.ECHO_FALLBACK.replace("{npc}", "Hob") in " ".join(narrations(before))


@pytest.mark.asyncio
async def test_a_reply_on_its_way_shows_on_the_askers_page(monkeypatch):
    """Beta rehearsal 2026-09-28: three to eight seconds of silence read as
    a lost line. Before the model is asked, the asker's open page gets a
    transient `thinking` frame naming who is composing; nobody else's, and
    never an event."""
    from daydream import live

    ada = player(1, "Ada", "r-green")
    bo = player(2, "Bo", "r-green")
    frames: dict[str, list] = {ada: [], bo: []}

    async def send_ada(frame):
        frames[ada].append(frame)

    async def send_bo(frame):
        frames[bo].append(frame)

    live.register(ada, send_ada)
    live.register(bo, send_bo)
    try:
        _mock(monkeypatch, {"gesture": "Hob grins.", "say": "Evening, Ada.", "advance": "none"})
        before = events.max_seq()
        await talk(ada, "t-hob", "what is your favourite colour, and why that one?")
        assert frames[ada] == [{"kind": "thinking", "who": "Hob", "text": None}]
        assert frames[bo] == []
        assert all(e.kind != "thinking" for e in events.fetch_since(before))
    finally:
        live.unregister(ada)
        live.unregister(bo)
