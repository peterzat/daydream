"""The delete-slot grace window (BACKLOG delete-slot-grace-window).

Deleting a toon is irreversible, so a controller that dropped its WS
connection moments ago (the reconnect overlay rides those drops out all
the time) still protects its slot from OTHER sessions for
DELETE_GRACE_SECONDS. Kick keeps the plain-liveness rule — it rests a
recoverable toon."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.api import slots as slots_module
from daydream.api import ws as ws_module
from daydream.server import app

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    ws_module._live_session_counts.clear()
    ws_module._last_disconnect.clear()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()
    ws_module._live_session_counts.clear()
    ws_module._last_disconnect.clear()


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)


def _controller_session(client: TestClient) -> str:
    """Claim slot 1 for this client and return its session id (the toon's
    controller_session)."""
    client.post("/api/slots/1/kick")
    r = client.post("/api/slots/1/claim")
    assert r.status_code == 200
    from daydream import toons

    t = toons.get_toon_in_slot(1)
    assert t is not None and t.controller_session
    return t.controller_session


def test_delete_blocked_within_grace_of_disconnect():
    """Simulate the exact grief window: the controller's socket dropped a
    moment ago (mark + unmark records the disconnect time). Another
    session's delete must 403; kick (recoverable) is still allowed."""
    with TestClient(app) as owner, TestClient(app) as rival:
        _login(owner)
        sid = _controller_session(owner)
        # A connect/disconnect cycle: the controller was just live.
        ws_module._mark_session_live(sid)
        ws_module._unmark_session_live(sid)

        _login(rival)
        r = rival.post("/api/slots/1/delete")
        assert r.status_code == 403
        # The recoverable action stays permitted on plain liveness.
        r = rival.post("/api/slots/1/kick")
        assert r.status_code == 200


def test_delete_allowed_after_grace_expires():
    with TestClient(app) as owner, TestClient(app) as rival:
        _login(owner)
        sid = _controller_session(owner)
        ws_module._mark_session_live(sid)
        ws_module._unmark_session_live(sid)
        # Age the disconnect past the window.
        ws_module._last_disconnect[sid] -= slots_module.DELETE_GRACE_SECONDS + 1

        _login(rival)
        r = rival.post("/api/slots/1/delete")
        assert r.status_code == 200


def test_delete_blocked_while_controller_connected():
    with TestClient(app) as owner, TestClient(app) as rival:
        _login(owner)
        sid = _controller_session(owner)
        ws_module._mark_session_live(sid)  # live right now
        try:
            _login(rival)
            r = rival.post("/api/slots/1/delete")
            assert r.status_code == 403
        finally:
            ws_module._unmark_session_live(sid)


def test_own_delete_unaffected_by_grace():
    """The controller deleting its OWN toon is never grace-blocked."""
    with TestClient(app) as owner:
        _login(owner)
        sid = _controller_session(owner)
        ws_module._mark_session_live(sid)
        ws_module._unmark_session_live(sid)
        r = owner.post("/api/slots/1/delete")
        assert r.status_code == 200
