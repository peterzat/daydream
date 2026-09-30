"""Local replies keep only the promises the engine keeps (spec 2026-09-29
criterion 8), with the local model mocked: the drafts are judged in one
call, the best passing one is shown, the authored deflection speaks when
none passes, and a judge that fails shows the first draft as before."""

import copy
import json
import logging

import pytest

from daydream import db, events, worldclock
from daydream import dialogue as dlg
from daydream.llm import client, format2
from tests.story_helpers import FIXTURE, ROOT, at, load, player, talk

pytestmark = pytest.mark.tier_short

PROMISE = {"gesture": "Hob grins.", "say": "Follow me, I'll show you the way.", "advance": "none"}
INVENTS = {"gesture": "Hob grins.", "say": "The mill pond froze in the long winter.",
           "advance": "none"}
HONEST = {"gesture": "Hob rubs the soot from a thumb.", "say": "The lane's that way, friend.",
          "advance": "none"}


def _env(**voice_extra):
    env = copy.deepcopy(FIXTURE)
    for t in env["toons"]:
        if t["id"] == "t-hob":
            t.setdefault("properties", {}).setdefault("voice", {}).update(voice_extra)
    return env


@pytest.fixture(autouse=True)
def guard_on(monkeypatch, tmp_path):
    monkeypatch.setenv("DAYDREAM_PROMISE_GUARD", "1")
    monkeypatch.setenv("DAYDREAM_DIALOGUE_NBEST", "2")
    at("2026-10-01T10:00:00+00:00")
    load(tmp_path, _env(deflections=["Hob shakes their head, smiling. 'Not mine to promise.'"]))
    yield
    worldclock.set_fake_now(None)
    db.close_db()
    events.reset_subscribers()


def _mock(monkeypatch, drafts, verdict):
    """Dialogue calls get the drafts in turn; the judge gets `verdict` (a
    dict, or an exception to raise)."""
    calls = []
    it = iter(drafts)

    async def fake(**kw):
        calls.append(kw)
        if kw.get("purpose") == "promise_judge":
            if isinstance(verdict, BaseException):
                raise verdict
            return verdict
        return next(it)

    monkeypatch.setattr("daydream.llm.client.acompletion_json", fake)
    return calls


async def test_a_promising_draft_is_held_back_for_one_that_only_talks(monkeypatch):
    ada = player(1, "Ada", "r-green")
    calls = _mock(monkeypatch, [INVENTS, HONEST], {"verdicts": ["c", "ok"]})
    monkeypatch.setattr(dlg, "score", lambda line, *a, **k: 0 if "pond" in line else 1)
    said = " ".join(await talk(ada, "t-hob", "can you take me there?"))
    assert "The lane's that way" in said and "pond" not in said
    judges = [c for c in calls if c["purpose"] == "promise_judge"]
    assert len(calls) == 3 and len(judges) == 1  # two drafts, one judge call
    assert "1. Hob grins." in judges[0]["user"] and "2. Hob rubs" in judges[0]["user"]
    assert "can you take me there?" in judges[0]["user"]  # the context the drafts saw
    assert judges[0]["temperature"] == 0.0


async def test_when_every_draft_promises_the_authored_deflection_speaks(monkeypatch):
    ada = player(1, "Ada", "r-green")
    _mock(monkeypatch, [PROMISE, PROMISE], {"verdicts": ["a", "b"]})
    before = events.max_seq()
    await talk(ada, "t-hob", "follow me to the well")
    evs = [e for e in events.fetch_since(before) if e.kind == "narrate"]
    texts = [e.payload["text"] for e in evs]
    assert "Hob shakes their head, smiling. 'Not mine to promise.'" in texts
    assert not any("Follow me" in t for t in texts)
    mine = [e for e in evs if "Not mine" in e.payload["text"]]
    assert mine[0].recipient_id == ada and "src" not in mine[0].payload  # authored, private


@pytest.mark.parametrize("verdict", [client.LLMUnavailable("down"), {"nope": 1}, "garbage"])
async def test_a_judge_that_fails_shows_the_first_draft_and_logs(monkeypatch, caplog, verdict):
    ada = player(1, "Ada", "r-green")
    _mock(monkeypatch, [HONEST, PROMISE], verdict)
    monkeypatch.setattr(dlg, "score", lambda line, *a, **k: 0 if "lane's" in line else 1)
    with caplog.at_level(logging.WARNING, logger="daydream.dialogue"):
        said = " ".join(await talk(ada, "t-hob", "where does this go?"))
    assert "The lane's that way" in said
    assert any("promise judge" in r.getMessage() for r in caplog.records)


async def test_switched_off_there_is_no_judge(monkeypatch):
    monkeypatch.setenv("DAYDREAM_PROMISE_GUARD", "0")
    ada = player(1, "Ada", "r-green")
    calls = _mock(monkeypatch, [PROMISE, PROMISE], {"verdicts": ["a", "b"]})
    said = " ".join(await talk(ada, "t-hob", "follow me"))
    assert "Follow me" in said
    assert [c["purpose"] for c in calls] == ["dialogue", "dialogue"]


def test_deflections_fall_back_to_the_world_then_the_engine(tmp_path):
    env = copy.deepcopy(FIXTURE)
    env.setdefault("config", {})["deflections"] = ["{npc} lets that one drift by."]
    load(tmp_path, env, name="world-default")
    from daydream import objects

    assert dlg.deflection(objects.get("t-hob")) == "Hob lets that one drift by."
    load(tmp_path, copy.deepcopy(FIXTURE), name="engine-default")
    assert dlg.deflection(objects.get("t-hob")) == "Hob considers that for a moment, and lets it rest."


@pytest.mark.parametrize("where,value,needle", [
    ("voice", "not a list", "voice.deflections must be a list of strings"),
    ("config", ["no placeholder here"], "config.deflections must be a list of lines"),
])
def test_the_loader_refuses_bad_deflections(where, value, needle):
    env = json.loads((ROOT / "worlds/lost-hours.json").read_text())
    if where == "voice":
        env["toons"][0]["properties"]["voice"]["deflections"] = value
    else:
        env["config"]["deflections"] = value
    with pytest.raises(format2.Format2ValidationError, match=needle):
        format2.validate_envelope2(env)


def test_every_village_resident_and_guest_has_a_deflection():
    env = json.loads((ROOT / "worlds/lost-hours.json").read_text())
    voiced = [t for t in env["toons"] if (t.get("properties") or {}).get("voice")]
    assert voiced
    missing = [t["id"] for t in voiced if not t["properties"]["voice"].get("deflections")]
    assert missing == []


async def test_the_judge_reads_what_bears_on_its_rules(monkeypatch):
    ada = player(1, "Ada", "r-green")
    calls = _mock(monkeypatch, [HONEST, HONEST], {"verdicts": ["ok", "ok"]})
    await talk(ada, "t-hob", "is there a river here?")
    drafting = next(c for c in calls if c["purpose"] == "dialogue")["user"]
    judged = next(c for c in calls if c["purpose"] == "promise_judge")["user"]
    assert "THE VILLAGE'S PLACES AND THE WAYS BETWEEN THEM (no others exist):" in drafting
    for kept in ("WHO HOB IS", "THE VILLAGE'S PEOPLE", "THE VILLAGE'S PLACES", "WHAT HOB KNOWS",
                 "is there a river here?"):
        assert kept in judged, kept
    for dropped in ("THEIR VOICE, FOR FLAVOR", "WHAT THEY WANT", "Hob and Ada: a stranger"):
        assert dropped in drafting and dropped not in judged, dropped


async def test_a_deflection_is_a_line_the_resident_said(monkeypatch):
    ada = player(1, "Ada", "r-green")
    _mock(monkeypatch, [PROMISE, PROMISE], {"verdicts": ["a", "b"]})
    await talk(ada, "t-hob", "follow me")
    assert "Not mine to promise" in " ".join(dlg.recent_lines("w-fixture", "t-hob"))


@pytest.mark.parametrize("line,names", [
    ("Bell dusts soot off. 'Oh, the Old Bakery? That's where the flour was.'", ["Bakery"]),
    ("Hob grins. 'Wynn says the lane is quiet, Ada.'", []),
    ("'Not tonight,' Hob says. 'Tuesday, maybe.'", []),  # a sentence opens capitalized
    ("Hob nods. 'I'll think on it. Hob's lamps are lit.'", []),
])
def test_names_a_draft_invents(line, names):
    known = {"hob", "wynn", "ada", "lane", "lamps", "bell", "old"}
    assert dlg.unknown_names(line, known) == names


async def test_an_invented_name_is_held_back_without_the_judge(monkeypatch):
    ada = player(1, "Ada", "r-green")
    invented = {"gesture": "Hob points.", "say": "The Copper Kettle Inn is down that way.",
                "advance": "none"}
    calls = _mock(monkeypatch, [invented, HONEST], {"verdicts": ["ok", "ok"]})
    said = " ".join(await talk(ada, "t-hob", "where can I eat?"))
    assert "Copper Kettle" not in said and "The lane's that way" in said
    judged = [c for c in calls if c["purpose"] == "promise_judge"]
    assert len(judged) == 1 and "Copper" not in judged[0]["user"]


async def test_every_draft_inventing_deflects_with_no_judge_call(monkeypatch):
    ada = player(1, "Ada", "r-green")
    invented = {"gesture": "Hob points.", "say": "Ask at the Copper Kettle Inn.",
                "advance": "none"}
    calls = _mock(monkeypatch, [invented, invented], {"verdicts": ["ok", "ok"]})
    said = " ".join(await talk(ada, "t-hob", "where can I eat?"))
    assert "Not mine to promise" in said
    assert [c["purpose"] for c in calls] == ["dialogue", "dialogue"]


@pytest.mark.parametrize("line,hit", [
    ("Tace nods. 'I will listen to your spring and see where it slipped.'", True),
    ("Linden smiles. 'Warm your hands before we step out.'", True),
    ("Bell grins. 'Right, I've saved the bottom rung for you.'", True),
    ("Tace nods. 'I can't leave the bench, friend.'", False),
    ("Linden pours. 'I can pour you a cup while you think.'", False),
    ("Bell laughs. 'I'll tell you about Pollen, she sulks.'", False),
    ("Hob reaches for a key and offers it warmly to you. 'Here is your key.'", True),
    ("Hob beams. 'I'd love to walk with you, and then we can decide where to go.'", True),
    ("Hob nods. 'Have a sip before we wander toward the green.'", True),
    ("Hob hums. 'Do you want me to light the lamp for you?'", True),
    ("Hob smiles. 'Would you like a cup of tea?'", False),
    ("Hob squints. 'I will mend this little wheel before dusk.'", False),
    ("Hob nods. 'I can mend it for you, friend.'", True),
    ("Hob beams. 'I'll keep your pebble safe.'", True),
    ("Hob nods. 'The lane waits for you, and so do the lamps.'", False),
])
def test_commitments_the_engine_wont_keep(line, hit):
    assert dlg.commits(line) is hit
