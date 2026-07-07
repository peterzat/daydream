"""Dream journal (daydream/journal.py; SPEC 2026-07-07 criterion 3).

Deterministic tests with a MOCKED LLM: the leave-triggered recap appends a
validated entry with sequence idempotency (no new events -> no call, no
write), every failure path (kill switch, LLM outage, refusal, length window,
banlist) skips silently without advancing the idempotency marker, the FIFO
cap holds, authored beats append with zero LLM, the snapshot carries the
controlled toon's journal only, and the leave endpoint always succeeds."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from daydream import config, db, events, journal, objects
from daydream.llm import client
from daydream.server import app

pytestmark = pytest.mark.tier_short

GOOD_ENTRY = (
    "You wandered the meadow while the fireflies were waking, and traded a "
    "few soft words with the dusk. Before you woke, you tucked one small "
    "wonder away to keep."
)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_JOURNAL_ENABLED", "1")
    db.init_live(path=tmp_path / "test.db", migrations_dir=config.MIGRATIONS_DIR)
    yield
    db.close_db()
    events.reset_subscribers()


def _mock_llm(monkeypatch, payload):
    spy = AsyncMock(return_value=payload)
    monkeypatch.setattr("daydream.llm.client.acompletion_json", spy)
    return spy


def _act(text: str = "hello dusk") -> None:
    """Give wren an attributable event."""
    events.append("toon", "t-wren", "say", {"text": text, "name": "Wren"},
                  room_id="r-meadow")


def _journal() -> list:
    return objects.get_property("t-wren", "journal") or []


# ---- fetch_for_toon -------------------------------------------------------


def test_fetch_for_toon_filters_actor_and_recipient():
    _act("mine")
    events.append("toon", "t-rook", "say", {"text": "not mine"}, room_id="r-forge")
    events.append("system", None, "narrate", {"text": "addressed to wren"},
                  room_id="r-meadow", recipient_id="t-wren")
    got = events.fetch_for_toon("t-wren")
    texts = [e.payload.get("text") for e in got]
    assert texts == ["mine", "addressed to wren"]


def test_fetch_for_toon_since_and_limit():
    for i in range(6):
        _act(f"line {i}")
    all_seqs = [e.seq for e in events.fetch_for_toon("t-wren")]
    got = events.fetch_for_toon("t-wren", since=all_seqs[1], limit=3)
    assert [e.payload["text"] for e in got] == ["line 3", "line 4", "line 5"]
    assert [e.seq for e in got] == sorted(e.seq for e in got)  # oldest first


# ---- write_entry ----------------------------------------------------------


async def test_write_entry_appends_and_is_seq_idempotent(monkeypatch):
    spy = _mock_llm(monkeypatch, {"entry": GOOD_ENTRY})
    _act()
    await journal.write_entry("t-wren")
    assert [e["text"] for e in _journal()] == [GOOD_ENTRY]
    assert spy.call_count == 1
    # Leaving again with NO new events: no LLM call, nothing written.
    await journal.write_entry("t-wren")
    assert spy.call_count == 1
    assert len(_journal()) == 1
    # A new event re-arms it.
    _act("one more thing")
    await journal.write_entry("t-wren")
    assert spy.call_count == 2
    assert len(_journal()) == 2


async def test_write_entry_kill_switch(monkeypatch):
    monkeypatch.setenv("DAYDREAM_JOURNAL_ENABLED", "0")
    spy = _mock_llm(monkeypatch, {"entry": GOOD_ENTRY})
    _act()
    await journal.write_entry("t-wren")
    assert spy.call_count == 0 and _journal() == []


@pytest.mark.parametrize("payload", [
    {"refused": True, "reason": "the dream is thin tonight"},
    {"entry": "too short"},
    {"entry": "x" * 600},
    {"entry": "You saw grimdark pixel-art machinery " + "and walked on. " * 6},
    {"nonsense": True},
])
async def test_write_entry_validation_skips_and_keeps_marker(monkeypatch, payload):
    """A refused/invalid recap writes nothing AND leaves journal_last_seq
    unset, so the next leave retries with the same events still tellable."""
    spy = _mock_llm(monkeypatch, payload)
    _act()
    await journal.write_entry("t-wren")
    assert _journal() == []
    assert objects.get_property("t-wren", "journal_last_seq") is None
    # Retry succeeds once the model behaves — same events, one more call.
    _mock_llm(monkeypatch, {"entry": GOOD_ENTRY})
    await journal.write_entry("t-wren")
    assert [e["text"] for e in _journal()] == [GOOD_ENTRY]
    assert spy.call_count == 1  # the first spy saw exactly the failed call


async def test_write_entry_llm_outage_is_silent(monkeypatch):
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=client.LLMUnavailable("vllm down")),
    )
    _act()
    await journal.write_entry("t-wren")  # must not raise
    assert _journal() == []


async def test_write_entry_never_raises(monkeypatch):
    """Fire-and-forget contract: even an unexpected explosion inside the
    pipeline is swallowed (logged), never raised to the leave endpoint."""
    monkeypatch.setattr(
        "daydream.llm.client.acompletion_json",
        AsyncMock(side_effect=RuntimeError("boom")),
    )
    _act()
    await journal.write_entry("t-wren")


async def test_journal_fifo_cap(monkeypatch):
    _mock_llm(monkeypatch, {"entry": GOOD_ENTRY})
    for i in range(journal.MAX_ENTRIES + 2):
        _act(f"round {i}")
        await journal.write_entry("t-wren")
    assert len(_journal()) == journal.MAX_ENTRIES


def test_append_authored_no_llm(monkeypatch):
    spy = _mock_llm(monkeypatch, {"entry": GOOD_ENTRY})
    journal.append_authored("t-wren", "The loft grew its first new room today.")
    entries = _journal()
    assert len(entries) == 1 and entries[0]["authored"] is True
    assert spy.call_count == 0
    journal.append_authored("t-wren", "   ")  # blank: ignored
    assert len(_journal()) == 1


def test_entries_for_snapshot_caps_at_eight():
    objects.set_property(
        "t-wren", "journal",
        [{"text": f"e{i}", "at": "t"} for i in range(10)],
    )
    got = journal.entries_for_snapshot("t-wren")
    assert len(got) == journal.SNAPSHOT_ENTRIES
    assert got[-1]["text"] == "e9"


# ---- the leave endpoint + snapshot ----------------------------------------


def _login(c: TestClient) -> None:
    r = c.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)
    assert c.post("/api/slots/1/kick").status_code == 200
    assert c.post("/api/slots/1/claim").status_code == 200


def test_leave_fires_journal_task_and_always_succeeds(tmp_path, monkeypatch):
    db.close_db()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    called = []

    async def fake_write(toon_id):
        called.append(toon_id)
        raise RuntimeError("even an exploding writer never fails the leave")

    monkeypatch.setattr("daydream.journal.write_entry", fake_write)
    with TestClient(app) as c:
        _login(c)
        r = c.post("/api/session/leave")
        assert r.status_code == 200 and r.json()["released"] == "t-wren"
    assert called == ["t-wren"]
    # Leaving with no toon fires nothing and still succeeds.
    with TestClient(app) as c:
        r = c.post("/api/login", data={"password": "test-password"})
        r = c.post("/api/session/leave")
        assert r.status_code == 200 and r.json()["released"] is None
    assert called == ["t-wren"]


def test_snapshot_journal_is_self_only(tmp_path, monkeypatch):
    db.close_db()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    with TestClient(app) as c:
        _login(c)
        # Wren has entries; co-located Rook (moved here) has its own.
        objects.set_property("t-wren", "journal", [{"text": "wren's page", "at": "t"}])
        objects.set_property("t-rook", "journal", [{"text": "rook's secret", "at": "t"}])
        objects.move("t-rook", "r-meadow")
        with c.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
    assert [e["text"] for e in snap["journal"]] == ["wren's page"]
    for card in snap["toons"] + [snap["self"]]:
        assert "journal" not in card  # never on toon cards
    text = str(snap)
    assert "rook's secret" not in text
