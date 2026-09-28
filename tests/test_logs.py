"""The app's own log lines (first prod evening, 2026-09-28): the journal held
only anonymous WebSocket open/close lines, because nothing configured the
`daydream` loggers. The lifespan now does (daydream/logs.py), and the
lifecycle of an evening reads in the journal: an invitation redeemed, a
sign-in, a dreamer made and entered, a WebSocket session with its length,
leaving the dream. The lines name accounts and dreamers, never a password,
a session token, an invite slug, or what a player typed."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import accounts, config, db, events, logs
from daydream.server import app

pytestmark = pytest.mark.tier_medium

PASSWORD = "a-long-enough-password"
TYPED = "i whisper the secret word marmalade"


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def test_configure_is_idempotent_and_takes_its_level_from_the_environment(monkeypatch):
    logger = logging.getLogger("daydream")
    monkeypatch.setattr(logger, "handlers", [])
    monkeypatch.setattr(logger, "level", logging.NOTSET)
    monkeypatch.setenv("DAYDREAM_LOG_LEVEL", "warning")
    logs.configure()
    logs.configure()
    assert len(logger.handlers) == 1
    assert logger.level == logging.WARNING
    monkeypatch.setenv("DAYDREAM_LOG_LEVEL", "no-such-level")
    logs.configure()
    assert logger.level == logging.INFO and len(logger.handlers) == 1


def test_an_evening_reads_in_the_log_without_secrets(caplog):
    caplog.set_level(logging.INFO, logger="daydream")
    with TestClient(app) as client:
        accounts.init()
        slug, _ = accounts.create_invite("Robin Ash")
        assert client.post("/api/invite/peek", json={"slug": "no-such-thing"}).status_code == 404
        r = client.post("/api/invite/redeem",
                        json={"slug": slug, "username": "robin", "password": PASSWORD})
        assert r.status_code == 200, r.text
        r = client.post("/api/dreamer/create",
                        json={"name": "Wren", "appearance_seed": "a small wren in a green scarf"})
        assert r.status_code == 200, r.text
        with client.websocket_connect("/ws") as ws:
            ws.receive_json()
            ws.send_json({"kind": "input", "text": "say " + TYPED})
        assert client.post("/api/session/leave").status_code == 200
        assert client.post("/api/logout").status_code == 200
        assert client.post("/api/login", json={"username": "robin",
                                               "password": "not-it-at-all"}).status_code == 401

    lines = [rec.getMessage() for rec in caplog.records if rec.name.startswith("daydream")]
    text = "\n".join(lines)
    for expected in ("invite: an unknown, used or expired link was opened",
                     "redeemed (join) by robin", "dreamer made: Wren by robin",
                     "ws: robin dreaming as Wren", "ws: robin closed after",
                     "left the dream: Wren (robin)", "sign-out: robin", "sign-in: refused"):
        assert expected in text, (expected, lines)
    for secret in (slug, PASSWORD, "not-it-at-all", "marmalade", config.cookie_name()):
        assert secret not in text, secret
