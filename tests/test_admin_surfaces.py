"""The few things the CLI asks a running or stopped prod to do (SPEC
2026-09-27 criteria 4 and 15): announce a line to everyone through a file
(the sleep warning; no web endpoint), say who is playing, and rest everyone
with their journals when the village falls asleep."""

from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from daydream import admin, db, events, toons
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def test_an_announcement_from_the_shell_reaches_everyone(tmp_path):
    """No web endpoint (criterion 4: the admin's web extras are exactly three);
    the CLI drops a file, the server tells everyone and removes it."""
    import json

    from daydream import announce

    with TestClient(app):
        announce.path().write_text(json.dumps({"text": "The lamps are dimming."}))
        assert announce.check_once() == "The lamps are dimming."
        assert not announce.path().exists()
        ev = [e for e in events.fetch_since(0) if e.kind == "narrate"][-1]
        assert ev.room_id is None and ev.payload["text"] == "The lamps are dimming."
        assert announce.check_once() is None  # delivered once
        announce.path().write_text("not json")
        assert announce.check_once() is None and not announce.path().exists()


def test_there_is_no_web_announce_endpoint():
    with TestClient(app) as client:
        authhelp.login(client, "keeper", role="admin")
        assert client.post("/api/admin/announce", json={"text": "hi"}).status_code == 404


def test_status_who_names_the_players():
    with TestClient(app) as client:
        authhelp.login(client, "wren")
        client.post("/api/dreamer/create", json={"name": "Mira", "appearance_seed": "a fox"})
        client.cookies.clear()
        authhelp.login(client, "keeper", role="admin")
        r = client.get("/status/who")
        from daydream import toons

        mira = next(t for t in toons.playing() if t.name == "Mira")
    # the id is what moderation needs: names are not unique
    assert r.status_code == 200 and r.text.startswith(f"playing: Mira [{mira.id}]")


def test_rest_all_rests_everyone_and_writes_their_journals(monkeypatch, capsys):
    written = []

    async def fake_entry(toon_id):
        written.append(toon_id)

    monkeypatch.setattr("daydream.journal.write_entry", AsyncMock(side_effect=fake_entry))
    with TestClient(app) as client:
        authhelp.login(client, "wren")
        mira = client.post("/api/dreamer/create",
                           json={"name": "Mira", "appearance_seed": "a fox"}).json()
    db.close_db()
    assert admin.cmd_rest_all(journal_too=True) == 0
    assert "rested Mira" in capsys.readouterr().out
    assert written == [mira["id"]]
    db.init_live()
    t = toons.get_toon(mira["id"])
    assert t.kicked_at is not None and not t.is_human_controlled
