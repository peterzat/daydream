"""Jev in the running game (daydream/jev/runtime.py), over the canonical
world with the local model and Jev both mocked. Off (no key), the judge and
topic choice are exactly the local path and Jev is never asked; on, the
judge serves its rule over both verdicts and topic choice serves Jev's pick
at TOPIC_MIN or more. docs/EXTERNAL.md, docs/JEV-SPIKE.md."""

import copy
import json
from pathlib import Path

import httpx
import pytest

from daydream import db, events, heard, objects, parser, toons, verbs, walkthrough, worldclock
from daydream.jev import client, ledger, settings

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
ENV = json.loads((ROOT / "worlds/lost-hours.json").read_text())


def choice(c, conf=0.95):
    return {"type": "choice", "choice": c, "confidence": conf, "probabilities": {c: conf}}


def pok(p):
    return {"type": "choice", "choice": "ok" if p >= 0.5 else "promise", "confidence": 0.9,
            "probabilities": {"ok": p, "promise": 1 - p}}


@pytest.fixture()
def world(tmp_path, monkeypatch):
    worldclock.set_fake_now("2026-10-01T10:00:00+00:00")
    heard.clear_cache()
    walkthrough.fresh_world(copy.deepcopy(ENV), tmp_path / "w.db")
    monkeypatch.setenv("DAYDREAM_JEV_API_KEY", "test-key")
    monkeypatch.delenv("DAYDREAM_EGRESS_URL", raising=False)
    monkeypatch.setattr(ledger, "root", lambda: tmp_path / "jev")
    client.reset()
    settings.forget()
    jev = {"answers": {}, "asked": []}

    def handler(request):
        body = json.loads(request.content)
        jev["asked"].append(sorted(body["questions"]))
        return httpx.Response(200, json={"model": "jev-1.13.0", "answers": jev["answers"],
                                         "usage": {"input_tokens": 500}})

    monkeypatch.setattr(client, "transport", httpx.MockTransport(handler))
    t = toons.create_toon_in_slot(1, "Wren", "Wren, a dreamer", "jev-test",
                                  owner_account="a-jev")
    objects.move(t.id, "r-loft")
    yield t.id, jev
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def _llm(monkeypatch, reply):
    calls = []

    async def fake(**kw):
        calls.append(kw.get("purpose"))
        return reply(kw) if callable(reply) else reply

    monkeypatch.setattr("daydream.llm.client.acompletion_json", fake)
    return calls


async def _told(me, line) -> list[dict]:
    before = events.max_seq()
    lp = await parser.parse_line(me, line)
    for p in lp.commands:
        await verbs.execute_command(me, p.verb, p.dobj_id, p.iobj_id, p.args,
                                    dobj_name=p.dobj_name)
    return [e.payload for e in events.fetch_since(before)
            if e.kind == "narrate" and e.recipient_id == me]


async def test_without_a_key_jev_is_never_asked(world, monkeypatch):
    me, jev = world
    monkeypatch.delenv("DAYDREAM_JEV_API_KEY")
    llm = _llm(monkeypatch, {"gesture": "Tace nods.", "say": "Long ago.", "advance": "none"})
    said = await _told(me, "talk to tace: who taught you everything you know?")
    assert [p.get("src") for p in said if p.get("src")] == ["local"]  # improvised, as before
    assert "dialogue" in llm and jev["asked"] == [] and ledger.decisions() == []


async def test_a_paraphrase_gets_its_authored_topic(world, monkeypatch):
    """"who taught you everything you know" names no topic's words; the word
    match misses and the model would improvise. Jev reads it as Wend."""
    me, jev = world
    llm = _llm(monkeypatch, {"gesture": "Tace nods.", "say": "Long ago.", "advance": "none"})
    jev["answers"] = {"topic": choice("Wend"), "request": {"type": "noul", "noul": 0.02}}
    said = await _told(me, "talk to tace: who taught you everything you know?")
    assert any("Wend" in p["text"] and "src" not in p for p in said)  # authored
    assert "dialogue" not in llm
    [row] = [r for r in ledger.decisions() if r["surface"] == "topics"]
    assert row["served"] == "jev" and row["local"] is None and row["jev"] == "Wend"
    assert row["toon"] == me


async def test_a_pick_below_the_threshold_leaves_the_word_match(world, monkeypatch):
    me, jev = world
    llm = _llm(monkeypatch, {"gesture": "Tace nods.", "say": "Long ago.", "advance": "none"})
    jev["answers"] = {"topic": choice("Wend", 0.5), "request": {"type": "noul", "noul": 0.02}}
    said = await _told(me, "talk to tace: who taught you everything you know?")
    assert [p.get("src") for p in said if p.get("src")] == ["local"] and "dialogue" in llm
    assert ledger.decisions()[-1]["served"] == "local"


async def test_a_request_that_names_a_topic_is_improvised_with_its_words(world, monkeypatch):
    me, jev = world
    prompts = []

    def reply(kw):
        prompts.append(kw.get("user", ""))
        return {"gesture": "Tace shakes their head.", "say": "Not today.", "advance": "none"}

    _llm(monkeypatch, reply)
    jev["answers"] = {"topic": choice("clockmaking"), "request": {"type": "noul", "noul": 0.97}}
    said = await _told(me, "talk to tace: lend me your tools")
    assert [p.get("src") for p in said if p.get("src")] == ["local"]  # not the canned topic
    assert any("WOULD SAY ABOUT WHAT WAS MENTIONED" in u for u in prompts)  # its words ground it


async def test_a_paraphrase_never_takes_an_open_beats_line(world, monkeypatch):
    """Codereview 2026-09-30d: "the folded thing" and "the tin" are Mott's
    plain topics and his open beat's aliases, so the beat wins them; Jev is
    never offered them while it is open, and a paraphrase reaches the
    dialogue that advances the beat."""
    from daydream import story

    me, jev = world
    wid = objects.get(me).world_id
    story.open_arc(wid, "mott-minute")
    story.adjust_rel(wid, "t-mott", me, 2)
    objects.move(me, objects.get("t-mott").location_id)
    llm = _llm(monkeypatch, {"gesture": "Mott turns the tin over.", "say": "Well now.",
                             "advance": "mott-minute/mott-confides"})
    jev["answers"] = {"topic": choice("the folded thing", 0.9),
                      "request": {"type": "noul", "noul": 0.02}}
    await _told(me, "talk to mott: what is that little thing you keep so close?")
    assert "dialogue" in llm
    assert story.beat_done(wid, "mott-minute", "mott-confides")


@pytest.mark.parametrize("local,p_ok,passes", [
    ("a", 0.97, True),    # Jev sure it only talks: a needless local hold is lifted
    ("a", 0.6, False),    # Jev leaning, local failing: held (a live miss: the jar's contents)
    ("ok", 0.6, True),    # both lean to pass
    ("ok", 0.3, False),   # Jev sure enough it fails: held (a live miss: the old baker)
])
async def test_the_judge_serves_its_rule_over_both_verdicts(world, monkeypatch, local, p_ok,
                                                            passes):
    from daydream import dialogue

    me, jev = world
    _llm(monkeypatch, {"verdicts": [local]})
    jev["answers"] = {"d0": pok(p_ok)}
    assert await dialogue.judge("CONTEXT", ["Tace nods. 'Go on up.'"], toon=me) == [passes]
    [row] = ledger.decisions()
    assert row["served"] == "combined" and row["local"] == [local == "ok"]
    assert row["served_value"] == [passes] and row["toon"] == me


async def test_the_judge_is_local_when_jev_is_silent_or_off(world, monkeypatch):
    from daydream import dialogue

    me, jev = world
    _llm(monkeypatch, {"verdicts": ["a"]})
    client._paused["empty"] = 10 ** 12  # an empty account: no call is made
    assert await dialogue.judge("CONTEXT", ["x"], toon=me) == [False]
    assert ledger.decisions()[-1]["served"] == "local"
    client.reset()
    monkeypatch.delenv("DAYDREAM_JEV_API_KEY")
    _llm(monkeypatch, {"verdicts": ["ok"]})
    assert await dialogue.judge("CONTEXT", ["x"], toon=me) == [True]
    assert len(ledger.decisions()) == 1 and jev["asked"] == []
