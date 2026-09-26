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
    await talk(ada, "t-hob", "did you see the moth?")
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
        "Hob polishes a lamp glass until it squeaks.", "Hob counts the lamps under their breath."]})
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
