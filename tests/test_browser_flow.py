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
import re
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
    # The name given at the door is offered back, not asked for twice
    # (playtest 2026-09-28).
    expect(dreamer.locator("input[name=name]")).to_have_value("Robin")
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
    toons.create_toon_in_slot(1, "Wren", "round spectacles, a patched blue coat",
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


# ---- the first evening in prod (playtest 2026-09-28) ------------------------------

UP = next(r for r in ENVELOPE["rooms"] if r["id"] == START["exits"]["up"])

# Where the reading column rests, measured in the page: its scroll position,
# whether a paragraph (the room description or a log line) starts at its
# resting place (a fade's height, `pad`, below the top edge, so the fade never
# greys the first line: playtest 2026-09-28b), where the newest log line ends,
# and its scroll-cue classes.
READING = """() => {
  const sc = document.querySelector(".prose");
  const pad = restAbove(sc);
  const origin = sc.getBoundingClientRect().top + sc.clientTop;
  const paras = [document.getElementById("room-desc"),
                 ...document.querySelectorAll("#chat > *")];
  const tops = paras.map((p) => p.getBoundingClientRect().top
    - (parseFloat(getComputedStyle(p).marginTop) || 0) - origin);
  const lines = document.querySelectorAll("#chat > .evt[data-seq]");
  const last = lines[lines.length - 1];
  return {scrollTop: sc.scrollTop, height: sc.clientHeight, pad,
          restsOnParagraph: tops.some((t) => Math.abs(t - pad) < 2),
          lastTop: last.getBoundingClientRect().top - origin,
          lastBottom: last.getBoundingClientRect().bottom - origin,
          cue: sc.className};
}"""


def _signed_in_with_a_dreamer(tab: Tab, name: str = "Marlo"):
    """A friend from an earlier evening signs in and lands in their dreamer."""
    friend = accounts.create_account(name.lower(), PASSWORD, display_name="A Friend")
    toons.create_toon_in_slot(1, name, "round spectacles, a patched blue coat",
                              "s-an-earlier-evening", owner_account=friend["id"])
    page = tab.page
    page.add_init_script("try { localStorage.setItem('dd-help-seen', '1'); } catch (e) {}")
    page.goto("/login")
    form = page.locator("#login-form")
    form.locator("input[name=username]").fill(name.lower())
    form.locator("input[name=password]").fill(PASSWORD)
    form.locator("button[type=submit]").click()
    page.wait_for_url(tab.base + "/")
    _in_the_start_room(page, name)
    return page


def test_leaving_the_dream_wakes_on_a_page_with_the_way_back(tab, engines):
    """Leaving used to leave the empty scene behind the dreamer panel:
    "drifting...", empty margins and a live input box. Now the page between
    dreams says where your dreamer is and steps back in with one click."""
    page = _signed_in_with_a_dreamer(tab)
    page.locator("#leave-dream").click()
    expect(page.locator("#awake")).to_be_visible()
    expect(page.locator("#room-title")).to_have_text("awake")
    expect(page.locator("#awake-text")).to_contain_text("Marlo is resting in the village")
    for gone in ("#input-form", "#scene", ".ribbon-wrap", "#exit-bar", "#leave-dream",
                 "#slots-panel"):
        expect(page.locator(gone)).to_be_hidden()

    page.locator("#awake-return").click()
    _in_the_start_room(page, "Marlo")
    expect(page.locator("#awake")).to_be_hidden()
    expect(page.locator("#input-form")).to_be_visible()
    _assert_quiet(tab, engines)


def test_a_lapsed_session_steps_back_in_at_the_door(tab, engines):
    """Awake, every failure went to the hidden log, so "step back in" with a
    lapsed session did nothing (codereview 2026-09-28c). It goes to the door."""
    page = _signed_in_with_a_dreamer(tab)
    page.locator("#leave-dream").click()
    expect(page.locator("#awake-text")).to_contain_text("Marlo is resting in the village")
    page.context.clear_cookies()
    page.locator("#awake-return").click()
    expect(page.locator("#login-form")).to_be_visible()
    _assert_quiet(tab, engines)


def test_an_unreachable_village_is_not_read_as_no_dreamer(tab, engines):
    """A failed read of your dreamer offered to make one (codereview
    2026-09-28c). The leaf says the village could not be reached, the note
    says why (here, asleep), and the button tries again."""
    page = _signed_in_with_a_dreamer(tab)
    asleep = json.dumps({"asleep": True, "note": "Back at first light."})
    page.route("**/api/dreamer", lambda route: route.fulfill(
        status=503, content_type="application/json", body=asleep))
    page.locator("#leave-dream").click()
    expect(page.locator("#awake-text")).to_have_text("The village could not be reached just now.")
    expect(page.locator("#awake-note")).to_contain_text("The village is asleep. Back at first light.")
    page.unroute("**/api/dreamer")
    expect(page.locator("#awake-return")).to_have_text("try again")
    page.locator("#awake-return").click()
    expect(page.locator("#awake-text")).to_contain_text("Marlo is resting in the village")
    expect(page.locator("#awake-return")).to_have_text("step back in")
    expect(page.locator("#awake-note")).to_be_hidden()
    _assert_quiet(tab, engines)


def test_letting_your_dreamer_go_while_awake_offers_a_new_one(tab, engines):
    """Letting your only dreamer go while awake left the leaf saying it was
    resting, with a "step back in" that claimed an empty slot (codereview
    2026-09-28c). The leaf now offers to make a new one."""
    page = _signed_in_with_a_dreamer(tab)
    page.locator("#leave-dream").click()
    expect(page.locator("#awake-text")).to_contain_text("Marlo is resting in the village")
    page.locator("#awake-dreamer").click()
    page.locator("#slots-list .slot-delete").click()
    page.locator("#delete-yes").click()
    expect(page.locator("#awake-return")).to_have_text("make your dreamer")
    expect(page.locator("#awake-text")).to_contain_text("Make your dreamer")
    expect(page.locator("#dreamer-form")).to_be_visible()
    _assert_quiet(tab, engines)


def test_an_answer_rests_on_a_paragraph_top_and_the_columns_show_more(tab, engines):
    """On a laptop-sized window, asking a resident about a topic pinned the
    column to its bottom and left the tail of an older paragraph at the top,
    and nothing showed that the columns held more (overlay scrollbars hide).
    Each answer now comes to rest on a paragraph's top with the whole answer
    in view, and a column with more to show fades at that edge."""
    page = tab.page
    page.set_viewport_size({"width": 1280, "height": 650})
    _signed_in_with_a_dreamer(tab)
    page.locator("#exit-bar button[data-direction=up]").click()
    expect(page.locator("#room-title")).to_have_text(UP["title"])
    chips = page.locator("#topics .topic-chip:not(.topic-more)")
    expect(chips.first).to_be_visible()
    expect(page.locator("#scene")).to_have_class(re.compile(r"\bmore-below\b"))

    answers = page.locator("#chat > .evt[data-seq]")
    scrolled = False
    for i in range(3):
        before = answers.count()
        chips.nth(i).click()
        expect(answers).to_have_count(before + 1)
        page.wait_for_timeout(100)  # the settle runs on the frame after the line
        r = page.evaluate(READING)
        if r["scrollTop"] > 0:
            scrolled = True
            assert r["restsOnParagraph"], r  # never mid-paragraph at the top
            assert "more-above" in r["cue"], r
        if r["lastBottom"] - r["lastTop"] <= r["height"]:
            assert -1 <= r["lastTop"] and r["lastBottom"] <= r["height"] + 1, r
        else:
            assert abs(r["lastTop"] - r["pad"]) < 2, r  # a long answer opens at its first line
    assert scrolled, "three answers never needed the column to scroll; the test proves nothing"
    _assert_quiet(tab, engines)


LONG_ANSWER = " ".join(["The clock ticks softly, and dust settles on its gears like snow."] * 30)


def test_a_reader_inside_a_long_answer_keeps_their_place(tab, engines):
    """A line soon after you acted pulled a reader who had scrolled down inside
    a long answer back to its first line (codereview 2026-09-28c). The answer
    still opens at its first line; after that the reader's place holds."""
    page = tab.page
    page.set_viewport_size({"width": 1280, "height": 650})
    _signed_in_with_a_dreamer(tab)
    page.wait_for_timeout(100)  # the arrival's settle has run
    page.evaluate("() => youActed()")
    page.evaluate("(t) => renderEvent({seq: 900000, kind: 'narrate', payload: {text: t}})",
                  LONG_ANSWER)
    page.wait_for_timeout(100)
    opened = page.evaluate(READING)
    assert opened["lastBottom"] - opened["lastTop"] > opened["height"], opened
    assert abs(opened["lastTop"] - opened["pad"]) < 2, opened  # it opens at its first line
    page.evaluate("() => { document.querySelector('.prose').scrollTop += 250; }")
    reading = page.evaluate(READING)["scrollTop"]
    assert reading > opened["scrollTop"] + 200, (reading, opened)
    page.evaluate("() => renderEvent({seq: 900001, kind: 'say', actor_id: 't-someone',"
                  " payload: {name: 'Someone', text: 'hello'}})")
    page.wait_for_timeout(100)
    assert page.evaluate(READING)["scrollTop"] >= reading - 1  # no pull backward
    _assert_quiet(tab, engines)


def test_the_account_panel_buttons_line_up(tab, engines):
    """The blanket panel rule pushed "change password" to the right while "sign
    out" and "close" stacked on the left. The form's action now sits under its
    fields at their right edge, and sign out and close share one row at the
    fields' two edges."""
    page = _signed_in_with_a_dreamer(tab)
    page.locator("#slots-toggle").click()
    page.locator(".account-box summary").click()
    field = page.locator("#password-form input[name=new]").bounding_box()
    submit = page.locator("#password-form button[type=submit]").bounding_box()
    out = page.locator("#sign-out").bounding_box()
    close = page.locator("#slots-close").bounding_box()
    right = field["x"] + field["width"]
    assert abs(submit["x"] + submit["width"] - right) < 2, (submit, field)
    assert abs(out["y"] - close["y"]) < 2, (out, close)
    assert abs(out["x"] - field["x"]) < 2, (out, field)
    assert abs(close["x"] + close["width"] - right) < 2, (close, field)
    _assert_quiet(tab, engines)


def test_walking_up_and_down_tells_where_you_went_and_leaves_nothing_behind(tab, engines):
    """First prod evening, 2026-09-28: up and down from the start room left a
    bare "you go up." / "you go down." in each room, stacked on every return.
    Now each arrival says where you went, and a room you come back to holds
    nothing of your going."""
    page = _signed_in_with_a_dreamer(tab)
    chat = page.locator("#chat")
    page.locator("#exit-bar button[data-direction=up]").click()
    expect(page.locator("#room-title")).to_have_text(UP["title"])
    expect(chat.locator(".evt-arrival")).to_contain_text("You climb up to ")
    # Only what is here links: the room's title holds a resident's alias.
    links = chat.locator(".evt-arrival .entity-link").all_inner_texts()
    things = [t.strip() for t in page.locator("#things .obj").all_inner_texts()]
    assert links and {x.lower() for x in links} <= {t.lower() for t in things}, (links, things)
    page.locator("#exit-bar button[data-direction=down]").click()
    expect(page.locator("#room-title")).to_have_text(START["title"])
    page.locator("#exit-bar button[data-direction=up]").click()
    expect(page.locator("#room-title")).to_have_text(UP["title"])
    page.locator("#exit-bar button[data-direction=down]").click()
    expect(page.locator("#room-title")).to_have_text(START["title"])
    arrival = chat.locator(".evt-arrival")
    expect(arrival).to_have_count(1)
    expect(arrival).to_contain_text("You go down to ")
    expect(chat.locator(".evt-move")).to_have_count(0)
    assert not re.search(r"\byou go (up|down)\.", chat.inner_text(), re.IGNORECASE)
    _assert_quiet(tab, engines)


def test_talking_asks_for_your_words_on_the_page_not_in_a_browser_box(tab, engines):
    """Talk opened the browser's own prompt box ("www.eidolon.com says").
    The words now go on the page's input line: the hint names who you are
    talking to, Enter sends one talk command, and "never mind" lets it go."""
    dialogs, sent, got = [], [], []
    tab.page.on("dialog", lambda d: (dialogs.append(d.message), d.dismiss()))
    tab.page.on("websocket", lambda w: (w.on("framesent", lambda f: sent.append(f)),
                                         w.on("framereceived", lambda f: got.append(f))))
    page = _signed_in_with_a_dreamer(tab)
    page.locator("#exit-bar button[data-direction=up]").click()
    expect(page.locator("#room-title")).to_have_text(UP["title"])
    resident = page.locator("#toons .obj-toon").first
    who = resident.inner_text().split(" (")[0].strip()
    inp = page.locator("#input-text")
    before = inp.get_attribute("placeholder")

    page.locator("#verb-bar button[data-verb=talk]").click()
    resident.click()
    hint = page.locator("#verb-hint")
    expect(hint).to_be_visible()
    expect(hint).to_contain_text(who)
    assert inp.get_attribute("placeholder") != before
    hint.locator(".hint-cancel").click()
    expect(hint).to_be_hidden()
    assert inp.get_attribute("placeholder") == before

    page.locator("#verb-bar button[data-verb=talk]").click()
    resident.click()
    # A same-room re-snapshot (someone comes or goes, a face is painted) keeps
    # the waiting prompt's hint (codereview 2026-09-28g).
    snaps = [json.loads(f) for f in got if isinstance(f, str) and f.startswith("{")]
    page.evaluate("(s) => renderSnapshot(s)",
                  [s for s in snaps if s.get("kind") == "state_snapshot"][-1])
    expect(hint).to_contain_text(who)
    inp.fill("good evening")
    inp.press("Enter")
    expect(hint).to_be_hidden()
    frames = [json.loads(f) for f in sent if isinstance(f, str) and f.startswith("{")]
    talks = [f for f in frames if f.get("kind") == "command" and f.get("verb") == "talk"]
    assert [t["args"] for t in talks] == ["good evening"], frames
    assert dialogs == []
    assert tab.js_errors == [], tab.js_errors
