"""`bin/game play` (SPEC 2026-09-26 criterion 17): an agent drives a live
session through the same WebSocket path a browser uses, across repeated
invocations (each prints what happened since the previous one), with
several concurrent toons. Runs a real uvicorn server on a free port over a
temp data dir."""

import asyncio
import socket
import threading
import time

import pytest
import uvicorn

from daydream import db, events, play

pytestmark = pytest.mark.tier_medium


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture()
def live_server(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    events.reset_subscribers()
    from daydream.server import app

    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    th = threading.Thread(target=server.run, daemon=True)
    th.start()
    for _ in range(100):
        if server.started:
            break
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    th.join(timeout=10)
    db.close_db()
    events.reset_subscribers()


def _run(capsys, *argv) -> str:
    rc = play.main(list(argv))
    out = capsys.readouterr().out
    assert rc == 0, out
    return out


def test_two_agents_play_across_invocations(live_server, capsys):
    base = ["--base", live_server]
    out = _run(capsys, *base, "start", "Ada")
    assert "Ways:" in out and "You carry: nothing" in out
    _run(capsys, *base, "start", "Bo")
    out = _run(capsys, *base, "do", "Ada", "take lantern")
    assert "You take the lantern." in out
    # Bo's next invocation shows what happened in the room meanwhile.
    out = _run(capsys, *base, "do", "Bo", "look")
    assert "(meanwhile)" in out and "take the lantern" in out
    out = _run(capsys, *base, "look", "Ada")
    assert "You carry: lantern" in out
    out = _run(capsys, *base, "click", "Ada", "drop", "lantern")
    assert "You drop the lantern." in out
    out = _run(capsys, *base, "leave", "Bo")
    assert "left the dream" in out


def test_scene_rendering_lists_topics_time_and_the_book():
    snap = {
        "room": {"title": "The Square", "description": "Lanterns.", "exits": {"west": "r-x"}},
        "time": {"running": True, "day": 2, "label": "dusk", "phase": "dusk"},
        "self": {"id": "t-me"},
        "toons": [{"id": "t-me", "name": "Me"},
                  {"id": "t-bell", "name": "Bell", "mood": "cheerful",
                   "topics": ["the lanterns", "the yawning stranger"]}],
        "items": [{"name": "paper lantern"}], "inventory": [],
        "verb_bar": [{"name": "examine"}, {"name": "ask"}],
        "book": {"found": 3, "total": 160},
        "while_you_slept": {"title": "The First Dream", "text": "A heron came."},
    }
    text = play._scene(snap)
    assert "(day 2, dusk)" in text
    assert "Bell (cheerful)  | ask about: the lanterns; the yawning stranger" in text
    assert "Book: 3/160" in text and "The First Dream" in text
    assert asyncio.iscoroutinefunction(play._session)
