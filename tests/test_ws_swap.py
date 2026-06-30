"""World hot-swap: live in-process DB swap with WS reconnect.

SPEC 2026-06-29 (world-hot-swap). The oracle (test_hot_swap_open_socket_
converges_on_new_world) holds an open WS, swaps the live DB to a second
world over the in-process endpoint, and asserts the socket converges on the
new world AND the live DB equals the swap target. Refusal, failure-safety,
and drift-survival edges follow. No GPU, no real LLM (drift LLM stays off)."""

import io
import sqlite3
import urllib.error

import pytest
from fastapi.testclient import TestClient

from daydream import admin, config, db, drift, events
from daydream.api import world
from daydream.server import app

pytestmark = pytest.mark.tier_medium

# A distinguishing marker stamped into world B's meadow. World A (the seeded
# live world) never carries it, so its presence in a snapshot or on disk
# proves the live DB was actually swapped.
MARKER_TITLE = "World B Meadow (swap marker)"


@pytest.fixture(autouse=True)
def fresh_state(tmp_path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303), f"login failed: {r.status_code} {r.text}"


def _claim_wren(client: TestClient) -> None:
    """Bind the seeded Wren (slot 1) to this session so a WS connect resolves
    a controlled toon (picker-first entry, SPEC 2026-06-30, removed the
    default-toon fallback). The id stays `t-wren`; world B is migration-seeded
    too, so the cached toon id re-resolves there after a swap."""
    assert client.post("/api/slots/1/kick").status_code == 200
    rc = client.post("/api/slots/1/claim")
    assert rc.status_code == 200 and rc.json()["id"] == "t-wren", rc.text


def _make_world(path, *, meadow_title=None, extra_migration=None):
    """Build a standalone, fully-seeded world DB at `path`. Optionally rename
    the meadow (a distinguishable marker) or stamp a bogus future migration
    row (to exercise the newer-schema refusal). Checkpointed before close so
    the file is self-contained and a plain copy carries the whole world."""
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = db.open_db(path)
    try:
        db.init_schema(conn, config.MIGRATIONS_DIR)
        if meadow_title is not None:
            conn.execute(
                "UPDATE objects SET name = ?, "
                "properties_json = json_set(properties_json, '$.title', ?) "
                "WHERE kind = 'room' AND json_extract(properties_json, '$.slug') = 'meadow'",
                (meadow_title, meadow_title),
            )
        if extra_migration is not None:
            conn.execute(
                "INSERT INTO _migrations(filename) VALUES (?)", (extra_migration,)
            )
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    finally:
        conn.close()


def _meadow_title(path):
    """Read the meadow title from a DB file independently (read-only), so the
    oracle confirms on-disk state without going through the live connection."""
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(
            "SELECT json_extract(properties_json, '$.title') AS title "
            "FROM objects WHERE kind = 'room' "
            "AND json_extract(properties_json, '$.slug') = 'meadow'"
        ).fetchone()
        return row["title"] if row else None
    finally:
        conn.close()


def test_hot_swap_open_socket_converges_on_new_world(tmp_path):
    """Oracle: an open WS is told to re-snapshot against the swapped-in world,
    and afterward the live DB equals the swap target and differs from world A."""
    world_b = tmp_path / "snapshots" / "world-b.db"
    _make_world(world_b, meadow_title=MARKER_TITLE)
    with TestClient(app) as client:
        _login(client)
        _claim_wren(client)
        with client.websocket_connect("/ws") as ws:
            snap_a = ws.receive_json()
            assert snap_a["kind"] == "state_snapshot"
            assert snap_a["room"]["slug"] == "meadow"
            assert snap_a["room"]["title"] != MARKER_TITLE  # world A

            r = client.post("/api/world/swap", json={"target": str(world_b)})
            assert r.status_code == 200, r.text
            assert r.json()["ok"] is True

            changed = ws.receive_json()
            assert changed == {"kind": "world_changed"}
            snap_b = ws.receive_json()
            assert snap_b["kind"] == "state_snapshot"
            assert snap_b["room"]["title"] == MARKER_TITLE  # world B
    # Oracle, on disk and independent of the live connection: the live DB now
    # equals the swap target (and not world A's content).
    assert _meadow_title(config.live_db_path()) == MARKER_TITLE
    assert _meadow_title(world_b) == MARKER_TITLE


def test_hot_swap_refuses_missing_target(tmp_path):
    missing = tmp_path / "snapshots" / "nope.db"
    missing.parent.mkdir(parents=True, exist_ok=True)
    with TestClient(app) as client:
        _login(client)
        before = _meadow_title(config.live_db_path())
        r = client.post("/api/world/swap", json={"target": str(missing)})
        assert r.status_code == 404, r.text
        assert _meadow_title(config.live_db_path()) == before  # unchanged


def test_hot_swap_refuses_non_db_file(tmp_path):
    junk = tmp_path / "junk.db"
    junk.write_text("this is not a sqlite database")
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/world/swap", json={"target": str(junk)})
        assert r.status_code == 400, r.text
        assert "not a readable daydream DB" in r.json()["error"]


def test_hot_swap_refuses_newer_schema(tmp_path):
    future = tmp_path / "snapshots" / "future.db"
    _make_world(future, extra_migration="999_from_the_future.sql")
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/world/swap", json={"target": str(future)})
        assert r.status_code == 409, r.text
        assert "newer than this code" in r.json()["error"]


def test_hot_swap_refuses_target_outside_data_dir(tmp_path):
    # tmp_path.parent is above DAYDREAM_DATA_DIR (= tmp_path), so it is
    # outside the confinement boundary.
    outside = tmp_path.parent / "outside.db"
    with TestClient(app) as client:
        _login(client)
        r = client.post("/api/world/swap", json={"target": str(outside)})
        assert r.status_code == 400, r.text
        assert "under the data dir" in r.json()["error"]


def test_hot_swap_requires_auth(tmp_path):
    world_b = tmp_path / "snapshots" / "world-b.db"
    _make_world(world_b, meadow_title=MARKER_TITLE)
    with TestClient(app) as client:
        # No _login: the public-mode test client is unauthenticated.
        r = client.post("/api/world/swap", json={"target": str(world_b)})
        assert r.status_code == 401, r.text
    assert _meadow_title(config.live_db_path()) != MARKER_TITLE  # untouched


def test_hot_swap_failed_copy_restores_original_world(tmp_path, monkeypatch):
    """A swap that fails mid-install leaves the server serving the ORIGINAL
    world over a healthy connection (criterion 3, failure-safe)."""
    world_b = tmp_path / "snapshots" / "world-b.db"
    _make_world(world_b, meadow_title=MARKER_TITLE)

    def boom(src, dst, *a, **k):
        raise OSError("disk full (injected)")

    with TestClient(app) as client:
        _login(client)
        _claim_wren(client)
        original = _meadow_title(config.live_db_path())
        monkeypatch.setattr(db.shutil, "copyfile", boom)
        r = client.post("/api/world/swap", json={"target": str(world_b)})
        assert r.status_code == 500, r.text
        # The original world is still served on a fresh connection (the copy
        # injection does not touch the WS connect / snapshot path).
        with client.websocket_connect("/ws") as ws:
            snap = ws.receive_json()
            assert snap["room"]["title"] == original
            assert snap["room"]["title"] != MARKER_TITLE
    assert _meadow_title(config.live_db_path()) == original


@pytest.mark.asyncio
async def test_drift_loop_survives_swap(tmp_path, monkeypatch):
    """Drift is stopped before the swap and restarted after against the new
    world: the running task is replaced by a fresh, live one (criterion 4)."""
    monkeypatch.setenv("DAYDREAM_DRIFT_ENABLED", "1")
    world_b = tmp_path / "snapshots" / "world-b.db"
    _make_world(world_b, meadow_title=MARKER_TITLE)
    db.init_live()  # world A
    try:
        drift.start_drift_loop()
        before = drift._handle
        assert before is not None and not before.done()

        result = await world.perform_world_swap(world_b)
        assert result["ok"] is True

        after = drift._handle
        assert after is not None and not after.done()  # restarted
        assert after is not before  # a fresh task, not the stopped one
        assert _meadow_title(config.live_db_path()) == MARKER_TITLE
    finally:
        await drift.stop_drift_loop()
        db.close_db()


def test_lifespan_shutdown_after_swap_stops_live_drift(tmp_path, monkeypatch):
    """Regression: the lifespan must stop the CURRENT drift task on shutdown,
    not its stale startup handle. A swap replaces the task mid-run; before the
    fix, shutdown stopped the pre-swap handle and leaked the live post-swap
    task. Exercises the real lifespan via the TestClient context manager."""
    monkeypatch.setenv("DAYDREAM_DRIFT_ENABLED", "1")
    world_b = tmp_path / "snapshots" / "world-b.db"
    _make_world(world_b, meadow_title=MARKER_TITLE)
    with TestClient(app) as client:
        _login(client)
        assert client.post(
            "/api/world/swap", json={"target": str(world_b)}
        ).status_code == 200
        live = drift._handle  # the fresh task started after the swap
        assert live is not None and not live.done()
    # The TestClient context exit ran the lifespan shutdown. The live task is
    # stopped and the module handle cleared (with the bug, _handle would still
    # point at an un-cancelled post-swap task).
    assert drift._handle is None
    assert live.done()


# ---- CLI thin client (bin/game world swap -> admin.cmd_swap) -------------
#
# cmd_swap talks to the RUNNING server over a real socket (not the ASGI app),
# so these patch urllib's opener to record the request and inject responses.


class _FakeResp:
    def __init__(self, payload: bytes):
        self._payload = payload

    def read(self) -> bytes:
        return self._payload


def _fake_opener_factory(handler):
    class _Opener:
        def open(self, req):
            return handler(req)

    return lambda *a, **k: _Opener()


def test_cmd_swap_posts_target_and_succeeds(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")  # CLI skips the login
    target = tmp_path / "snapshots" / "world-b.db"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"")  # cmd_swap only sends the path; the server validates
    seen = {}

    def handler(req):
        seen["url"] = req.full_url
        seen["body"] = req.data
        return _FakeResp(
            b'{"ok": true, "world_id": "w-x", "subscribers_notified": 2}'
        )

    monkeypatch.setattr(
        "urllib.request.build_opener", _fake_opener_factory(handler)
    )
    rc = admin.main(["swap", str(target)])
    assert rc == 0
    assert seen["url"].endswith("/api/world/swap")
    import json as _json

    assert _json.loads(seen["body"])["target"] == str(target.resolve())
    assert "swapped live world" in capsys.readouterr().out


def test_cmd_swap_reports_server_refusal(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    target = tmp_path / "x.db"
    target.write_bytes(b"")

    def handler(req):
        raise urllib.error.HTTPError(
            req.full_url, 409, "Conflict", {}, io.BytesIO(b'{"error": "newer schema"}')
        )

    monkeypatch.setattr(
        "urllib.request.build_opener", _fake_opener_factory(handler)
    )
    rc = admin.main(["swap", str(target)])
    assert rc == 2
    assert "swap refused (409)" in capsys.readouterr().err


def test_cmd_swap_reports_server_unreachable(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    target = tmp_path / "x.db"
    target.write_bytes(b"")

    def handler(req):
        raise urllib.error.URLError("Connection refused")

    monkeypatch.setattr(
        "urllib.request.build_opener", _fake_opener_factory(handler)
    )
    rc = admin.main(["swap", str(target)])
    assert rc == 2
    assert "could not reach the daydream server" in capsys.readouterr().err
