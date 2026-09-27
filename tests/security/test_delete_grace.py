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
from tests import authhelp

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


def _login(client: TestClient, username: str = "rival") -> None:
    authhelp.login(client, username)


def _controller_session(client: TestClient) -> str:
    """Since accounts (SPEC 2026-09-27 criterion 5) an OWNED toon is protected
    by ownership outright; the delete grace window now guards an UNOWNED human
    toon (seeded, or from before accounts) that some session is playing. Put
    one in slot 1's place and return its controller session id."""
    from daydream import toons

    client.post("/api/slots/1/kick")  # rest the seeded Wren out of the way
    toons.delete_slot(1)
    t = toons.create_toon_in_slot(1, "Legacy", "an old friend", "s-legacy-player")
    assert t is not None and t.owner_account is None
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
    """Deleting your OWN toon is never grace-blocked: with accounts, "own"
    means the account owns it, whichever session last played it."""
    with TestClient(app) as owner:
        _login(owner, "owner")
        r = owner.post("/api/dreamer/create", json={"name": "Mira", "appearance_seed": "a fox"})
        slot = r.json()["slot"]
        from daydream import toons
        sid = toons.get_toon_in_slot(slot).controller_session
        ws_module._mark_session_live(sid)
        ws_module._unmark_session_live(sid)
        assert owner.post(f"/api/slots/{slot}/delete").status_code == 200
