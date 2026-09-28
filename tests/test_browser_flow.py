"""The first evening in a real browser (codereview 2026-09-28): the front door
once sent empty credentials because it disabled its inputs before reading the
form, and every unit test posted JSON straight to the API, so nothing caught
it. These tests drive headless Chromium through the real pages instead: an
invitation opens the door, a new friend makes a dreamer and steps into the
start room; a returning friend signs in (and a wrong password is refused
without leaving the door).

The app runs under uvicorn on a free loopback port in a background thread, so
the conftest's per-test data dir, disabled loops and engine mocks all apply.
Skipped cleanly where the browser stack is absent (CI has the package but no
Chromium)."""

from __future__ import annotations

import json
import socket
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from unittest.mock import AsyncMock

import httpx
import pytest

sync_api = pytest.importorskip("playwright.sync_api")

import uvicorn  # noqa: E402

from daydream import accounts, config, db, events, toons  # noqa: E402
from daydream.api.auth import LOGIN_REFUSED  # noqa: E402
from daydream.llm import bootstrap  # noqa: E402
from daydream.server import app  # noqa: E402

pytestmark = pytest.mark.tier_medium

expect = sync_api.expect

ROOT = Path(__file__).resolve().parent.parent
ENVELOPE = json.loads((ROOT / "worlds" / "lost-hours.json").read_text())
START = next(r for r in ENVELOPE["rooms"] if r["id"] == ENVELOPE["start_room"])
PASSWORD = "a-long-enough-password"
WAIT_MS = 10_000  # per step; a healthy step takes well under a second


# ---- the browser ------------------------------------------------------------------


@pytest.fixture(scope="module")
def browser():
    """One headless Chromium for the module; each test gets a fresh context
    (no shared cookies or localStorage). Skips, never fails, when the driver
    or the browser binary is missing."""
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as e:  # any driver failure means "no browser here"
        pytest.skip(f"playwright driver unavailable: {e}")
    try:
        chromium = pw.chromium.launch()
    except Exception as e:
        pw.stop()
        pytest.skip(f"headless Chromium unavailable: {e}")
    yield chromium
    chromium.close()
    pw.stop()


# ---- the server -------------------------------------------------------------------


@pytest.fixture
def live_server(tmp_path, monkeypatch):
    """The real app over HTTP on a free loopback port, against a fresh copy of
    the canonical world in this test's own data dir. Yields the base URL."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DAYDREAM_ACCESS", "public")
    for var in ("DAYDREAM_ENV", "DAYDREAM_PUBLIC_BASE", "DAYDREAM_PUBLIC_ORIGIN"):
        monkeypatch.delenv(var, raising=False)  # dev defaults: base "/", Origin vs Host
    db.close_db()
    events.reset_subscribers()
    live = config.live_db_path()
    live.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.load_world("lost hours", json.loads(json.dumps(ENVELOPE)), live)
    db.close_db()  # the server's lifespan opens it

    # Bind first and hand uvicorn the socket: no window for another process
    # to take the port between choosing it and serving on it.
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(
        app, host="127.0.0.1", port=port, log_level="warning", lifespan="on",
        timeout_graceful_shutdown=5))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]},
                              name="daydream-browser-e2e", daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{port}"
    deadline = time.monotonic() + 15
    while True:
        if not thread.is_alive():
            pytest.fail("the server exited during startup (see the log above)")
        if server.started:
            try:
                if httpx.get(base + "/healthz", timeout=1.0).status_code == 200:
                    break
            except httpx.HTTPError:
                pass
        if time.monotonic() > deadline:
            server.should_exit = True
            thread.join(timeout=10)
            pytest.fail("the server did not answer /healthz within 15 s")
        time.sleep(0.05)
    try:
        yield base
    finally:
        server.should_exit = True
        thread.join(timeout=15)
        sock.close()
        db.close_db()
        events.reset_subscribers()
        assert not thread.is_alive(), "the server thread did not stop"


@dataclass
class Tab:
    page: object
    base: str
    js_errors: list[str] = field(default_factory=list)


@pytest.fixture
def tab(browser, live_server):
    """A fresh browser context and page pointed at the live server. Requesting
    `live_server` here orders teardown: the page closes (and its WebSocket
    with it) before the server stops."""
    context = browser.new_context(base_url=live_server)
    context.set_default_timeout(WAIT_MS)
    page = context.new_page()
    t = Tab(page=page, base=live_server)
    page.on("pageerror", lambda e: t.js_errors.append(str(e)))
    try:
        yield t
    finally:
        context.close()


@pytest.fixture
def engines(monkeypatch):
    """Spies on the two engine entry points: the first evening makes no LLM
    call and no image render (conftest already points the LLM at a dead port
    and stubs the WS image enqueue; these prove nothing reached further)."""
    llm = AsyncMock(side_effect=AssertionError("the first evening made an LLM call"))
    image = AsyncMock(side_effect=AssertionError("the first evening rendered an image"))
    monkeypatch.setattr("daydream.llm.client.acompletion_json", llm)
    monkeypatch.setattr("daydream.images.client.generate_image", image)
    return llm, image


def _assert_quiet(tab: Tab, engines) -> None:
    llm, image = engines
    assert llm.await_count == 0, llm.await_args_list
    assert image.await_count == 0, image.await_args_list
    assert tab.js_errors == [], tab.js_errors


def _submit(page, button, api_path: str):
    """Click the real submit button; return the API response it caused."""
    with page.expect_response(f"**/{api_path}") as answered:
        button.click()
    return answered.value


def _check_exchange(resp, sent: dict, status: int) -> None:
    """The door posted exactly what was typed (the 2026-09-28 bug posted
    nulls), and the server answered `status`."""
    assert resp.request.post_data_json == sent, (
        f"the door posted {resp.request.post_data_json!r}, not what was typed")
    assert resp.status == status, (resp.status, resp.text())


def _in_the_start_room(page, name: str) -> None:
    """The game shows the start room as `name`: the WebSocket connected and a
    state_snapshot arrived and rendered."""
    expect(page.locator("#room-title")).to_have_text(START["title"])
    expect(page.locator("#room-desc")).to_have_text(START["description"])
    expect(page.locator("#self .you-name")).to_have_text(name)
    expect(page.locator("#slots-panel")).to_be_hidden()
    expect(page.locator("#dream-overlay")).to_be_hidden()


# ---- the tests --------------------------------------------------------------------


def test_an_invitation_opens_the_door_and_a_new_dreamer_steps_in(tab, engines):
    page = tab.page
    slug, _ = accounts.create_invite("Robin Ash")

    page.goto(f"/invite/{slug}")
    expect(page.locator("#invite-greeting")).to_have_text(
        "Welcome, Robin. A place in the village has been kept for you.")
    expect(page.locator("#door-login")).to_be_hidden()
    form = page.locator("#invite-form")
    expect(form).to_be_visible()
    form.locator("input[name=username]").fill("Robin")  # the door lowercases it
    form.locator("input[name=password]").fill(PASSWORD)
    _check_exchange(_submit(page, page.locator("#invite-button"), "api/invite/redeem"),
                    {"slug": slug, "username": "robin", "password": PASSWORD}, 200)

    # The door hands over to the game, which has no toon for Robin yet: the
    # "your dreamer" page, with the first-visit help leaf laid over it.
    page.wait_for_url(tab.base + "/")
    expect(page.locator("#slots-panel")).to_be_visible()
    expect(page.locator("#dreamer-form")).to_be_visible()
    account = accounts.get_account("robin")
    assert account is not None
    assert (account["display_name"], account["role"]) == ("Robin Ash", "player")
    assert accounts.peek_invite(slug) is None  # single use: spent
    (invite,) = [i for i in accounts.list_invites(include_closed=True)
                 if i["for_name"] == "Robin Ash"]
    assert invite["redeemed_at"] and invite["account_id"] == account["id"]

    expect(page.locator("#help-panel")).to_be_visible()
    page.locator("#help-close").click()
    expect(page.locator("#help-panel")).to_be_hidden()

    dreamer = page.locator("#dreamer-form")
    dreamer.locator("input[name=name]").fill("Robin")
    dreamer.locator("input[name=appearance_seed]").fill("a small wren in a moss-green scarf")
    dreamer.locator("button[type=submit]").click()

    _in_the_start_room(page, "Robin")
    (toon,) = toons.owned_toons(account["id"])
    assert (toon.name, toon.current_room_id) == ("Robin", START["id"])
    _assert_quiet(tab, engines)


def test_a_returning_friend_signs_in_and_a_wrong_password_stays_at_the_door(tab, engines):
    page = tab.page
    friend = accounts.create_account("wren", PASSWORD, display_name="Wren Hollis")
    # A dreamer from an earlier evening, so signing in lands straight in it.
    toons.create_toon_in_slot(1, "Wren", "a tall heron in a patched blue coat",
                              "s-an-earlier-evening", owner_account=friend["id"])

    page.goto("/login")
    form = page.locator("#login-form")
    username = form.locator("input[name=username]")
    password = form.locator("input[name=password]")
    error = form.locator(".door-error")
    expect(error).to_be_hidden()

    submit = form.locator("button[type=submit]")
    username.fill("wren")
    password.fill("not-the-password")
    _check_exchange(_submit(page, submit, "api/login"),
                    {"username": "wren", "password": "not-the-password"}, 401)
    expect(error).to_be_visible()
    expect(error).to_have_text(LOGIN_REFUSED)
    expect(password).to_be_enabled()  # the form is usable again
    assert page.url == tab.base + "/login"
    assert config.cookie_name() not in {c["name"] for c in page.context.cookies()}

    password.fill(PASSWORD)
    _check_exchange(_submit(page, submit, "api/login"),
                    {"username": "wren", "password": PASSWORD}, 200)
    page.wait_for_url(tab.base + "/")
    assert config.cookie_name() in {c["name"] for c in page.context.cookies()}
    _in_the_start_room(page, "Wren")
    _assert_quiet(tab, engines)
