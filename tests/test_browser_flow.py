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
        # The question, told back, and its answer (playtest 2026-09-28b).
        expect(answers).to_have_count(before + 2)
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


def test_the_columns_name_what_lies_below_their_fold(tab, engines):
    """A visual reader on a short window missed what sat below the columns'
    fold: the reading column's tail and a resident's ask-about chips under
    them (playthrough 2026-10-01). The reading column now says "more" at its
    foot, and the margin names the resident whose chips are cut off; each
    tab scrolls to what it names."""
    page = tab.page
    page.set_viewport_size({"width": 1280, "height": 600})
    _signed_in_with_a_dreamer(tab)
    prose = page.locator(".prose")
    more = page.locator("#prose-index .index-tab")
    expect(prose).to_have_class(re.compile(r"\bmore-below\b"))
    expect(more).to_have_text("↓ more")
    expect(more).to_be_visible()
    # The band only shows the way: a click beside its tab reaches the column.
    assert page.evaluate("""() => {
      const b = document.getElementById('prose-index').getBoundingClientRect();
      const el = document.elementFromPoint(b.left + 12, b.top + b.height / 2);
      return !!el && !el.closest('#prose-index');
    }"""), "the prose index band takes clicks beside its tab"
    more.click()
    page.wait_for_function("() => document.querySelector('.prose').scrollTop > 0")

    page.locator("#exit-bar button[data-direction=up]").click()
    expect(page.locator("#room-title")).to_have_text(UP["title"])
    resident = next(t["name"] for t in ENVELOPE["toons"] if t.get("room") == UP["id"])
    ask = page.locator("#margin-index .index-tab", has_text=f"ask {resident}")
    expect(ask).to_have_text(f"↓ ask {resident}")
    lines = page.evaluate("""() => new Set([...document.querySelectorAll(
        '#margin-index .index-tab:not(.folded)')].map((b) => b.offsetTop)).size""")
    assert lines == 1, "the margin's band keeps to one line (playthrough 2026-10-01b)"
    row = page.locator("#topics .topic-row").first
    # A snapshot rebuilds the rows while the band keeps its buttons
    # (codereview 2026-10-01b): the tab must find the row when clicked.
    page.evaluate("""() => document.querySelectorAll('#topics .topic-row')
      .forEach((r) => r.replaceWith(r.cloneNode(true)))""")
    page.evaluate("() => { document.getElementById('scene').scrollTop = 0; }")
    expect(ask).to_be_visible()
    ask.click()
    page.wait_for_function("""() => {
      const m = document.getElementById('scene');
      const r = document.querySelector('#topics .topic-row').getBoundingClientRect();
      const b = m.getBoundingClientRect();
      return r.top >= b.top && r.top + 20 <= b.bottom;
    }""")
    expect(row).to_be_visible()
    _assert_quiet(tab, engines)


def test_an_answer_stays_in_view_through_a_rerender_that_adds_lines_above(tab, engines):
    """A give's answer sat below the fold behind "more": the room's
    re-render after the give rebuilt the log with more above the answer and
    put the reader back at the old pixel offset (playthrough 2026-10-01c).
    The answer to what you just did stays in view instead."""
    page = tab.page
    page.set_viewport_size({"width": 1280, "height": 600})
    snaps: list = []
    later: list = []

    def on_frame(f):
        if '"state_snapshot"' in str(f):
            snaps.append(f)
        elif '"kind": "event"' in str(f) or '"kind":"event"' in str(f):
            later.append(json.loads(f)["event"])

    def on_ws(ws):
        ws.on("framereceived", on_frame)

    page.on("websocket", on_ws)
    _signed_in_with_a_dreamer(tab)
    page.locator("#things .obj").first.click()  # examine: an answer to your own act
    card = page.locator("#chat .detail-inset").last
    expect(card).to_be_visible()
    snap = json.loads(snaps[-1])
    # What the server's own re-render would hold: every line since, the answer too.
    snap["events"] += [e for e in later if e["seq"] > snap["last_seq"]]
    snap["last_seq"] = max([snap["last_seq"]] + [e["seq"] for e in later])
    low = min([e["seq"] for e in snap["events"]] or [1000])
    earlier = [{"seq": low - 40 + i, "kind": "narrate", "actor_type": "system", "actor_id": None,
                "room_id": snap["room"]["id"], "created_at": "2026-10-01T16:00:00+00:00",
                "payload": {"text": f"An earlier line, the {i}th, about the quiet of the tower."}}
               for i in range(1, 30)]
    snap["events"] = earlier + snap["events"]
    page.evaluate("(s) => renderSnapshot(s)", snap)
    page.wait_for_timeout(100)
    shown = page.evaluate("""() => {
      const sc = document.querySelector('.prose');
      const c = [...document.querySelectorAll('#chat .detail-inset')].pop().getBoundingClientRect();
      const b = sc.getBoundingClientRect();
      return c.top >= b.top - 2 && c.top < b.bottom - 20;
    }""")
    assert shown, "the answer card fell out of view on the re-render"
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
    """Talk opened the browser's own prompt box ("www.example.com says").
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


def test_your_own_words_told_back_keep_the_waiting_line(tab, engines):
    """Your words to a resident are told back before the reply, and cleared
    "the dream stirs..." for the whole of the model's call (codereview
    2026-09-28h). They now sit above the waiting line; the reply clears it."""
    page = _signed_in_with_a_dreamer(tab)
    page.evaluate("() => { youActed(); showPending(); }")
    page.evaluate("() => renderEvent({seq: 900000, kind: 'say', actor_id: selfToonId,"
                  " recipient_id: selfToonId, payload: {name: 'Marlo', to: 'Wren', text: 'hi'}})")
    last_two = "() => [...document.getElementById('chat').children].slice(-2).map(e => e.className)"
    assert page.evaluate(last_two) == ["evt evt-say", "evt evt-pending"]
    page.evaluate("() => renderEvent({seq: 900001, kind: 'narrate', payload: {text: 'Wren nods.'}})")
    expect(page.locator("#chat .evt-pending")).to_have_count(0)
    assert page.evaluate(last_two) == ["evt evt-say", "evt evt-narrate"]
    _assert_quiet(tab, engines)


_WATCH_OVERLAY = """() => {
  window.__overlaySeen = false;
  const o = document.getElementById("dream-overlay");
  new MutationObserver(() => {
    if (!o.classList.contains("hidden")) window.__overlaySeen = true;
  }).observe(o, { attributes: true, attributeFilter: ["class"] });
}"""

# Every new socket dials a path the server refuses, so each retry fails as in
# an outage. Same origin: the CSP blocks another port, and a blocked socket
# never fires its close.
_DEAD_SOCKETS = """() => {
  window.__RealWebSocket = window.__RealWebSocket || WebSocket;
  window.WebSocket = class extends window.__RealWebSocket {
    constructor() { super("ws://" + location.host + "/nowhere"); }
  };
}"""


def test_a_dropped_socket_that_comes_straight_back_shows_nothing(tab, engines):
    """Seen live 2026-09-29: a flash of "the dream is sleeping" five seconds
    into a first entry, healed in under two. A blip replays what was missed
    and shows no overlay."""
    page = _signed_in_with_a_dreamer(tab)
    page.evaluate(_WATCH_OVERLAY)
    page.evaluate("() => { window.__old = ws; ws.close(); }")
    page.wait_for_function("() => ws && ws !== window.__old && ws.readyState === 1")
    page.wait_for_timeout(3000)  # past the grace: nothing waiting to show
    assert page.evaluate("() => window.__overlaySeen") is False
    expect(page.locator("#dream-overlay")).to_be_hidden()
    _assert_quiet(tab, engines)


def test_a_drop_that_lasts_says_so_and_acting_in_it_keeps_your_words(tab, engines):
    page = _signed_in_with_a_dreamer(tab)
    page.evaluate(_DEAD_SOCKETS)
    page.evaluate("() => ws.close()")
    page.wait_for_timeout(1000)
    expect(page.locator("#dream-overlay")).to_be_hidden()  # still in the grace
    page.locator("#input-text").fill("look at the clock")
    page.locator("#input-text").press("Enter")
    # Acting in the gap shows the note at once, and the words stay to resend.
    expect(page.locator("#dream-overlay")).to_have_text("the dream is sleeping...", timeout=500)
    expect(page.locator("#input-text")).to_have_value("look at the clock")
    page.evaluate("() => { window.WebSocket = window.__RealWebSocket; }")
    expect(page.locator("#dream-overlay")).to_be_hidden(timeout=15_000)
    _in_the_start_room(page, "Marlo")
    _assert_quiet(tab, engines)


def test_a_drop_nobody_acts_in_shows_the_note_after_the_grace(tab, engines):
    page = _signed_in_with_a_dreamer(tab)
    page.evaluate(_DEAD_SOCKETS)
    page.evaluate("() => ws.close()")
    expect(page.locator("#dream-overlay")).to_have_text("the dream is sleeping...", timeout=4000)
    _assert_quiet(tab, engines)


def test_you_carry_names_the_satchel_and_the_book_and_not_empty_hands(tab, engines):
    """Playtest 2026-09-29: "your hands are empty" was the first line under
    "you carry", "open the satchel · 1 thread" read as a riddle, and the book
    beside it said nothing of what it was."""
    page = _signed_in_with_a_dreamer(tab)
    carry = page.locator("#carrying-region")
    expect(carry).not_to_contain_text("empty")
    expect(page.locator("#inventory")).to_be_hidden()  # nothing in your hands: nothing said
    expect(page.locator("#backpack-toggle .carry-name")).to_have_text("your satchel")
    expect(page.locator("#backpack-toggle .carry-sketch")).to_be_visible()
    # A page's first threads are not new: no glint on arrival (review 2026-09-29).
    expect(page.locator("#backpack-toggle")).not_to_have_class(re.compile("glint"))
    expect(page.locator("#book-name")).to_have_text("Book of Stray Minutes")
    expect(page.locator(".carry-note")).to_have_count(0)  # names alone (playtest 2026-09-29b)
    page.locator("#backpack-toggle").click()
    expect(page.locator("#backpack-panel")).to_be_visible()
    expect(page.locator("#threads li")).to_have_count(1)
    _assert_quiet(tab, engines)


def _in_the_loft(tab: Tab):
    """A dreamer standing in the loft with Tace and the little brass clock,
    its chip on Tace's row (the room names the clock to the player)."""
    from daydream import objects
    page = _signed_in_with_a_dreamer(tab)
    toon = next(t for t in toons.owned_toons(accounts.get_account("marlo")["id"]))
    page.locator("#exit-bar button", has_text="up").click()
    expect(page.locator("#room-title")).to_contain_text("Loft")
    assert objects.get(toon.id).location_id == "r-loft"
    expect(page.locator("#topics .topic-chip", has_text="the little brass clock")).to_be_visible()
    sent: list[dict] = []
    return page, sent


def _record_frames(page, sent: list) -> None:
    def on_ws(ws):
        ws.on("framesent", lambda payload: sent.append(json.loads(payload)))
    page.on("websocket", on_ws)


def test_a_staged_verb_and_a_chip_naming_a_thing_act_on_the_thing(tab, engines):
    """Playtest 2026-09-29: Wind staged, then a touch on Tace's "the little
    brass clock" chip asked Tace about the clock instead of winding it."""
    page, sent = _in_the_loft(tab)
    _record_frames(page, sent)
    page.reload()  # a fresh socket, so its frames are recorded
    expect(page.locator("#room-title")).to_contain_text("Loft")
    page.locator("#verb-bar button", has_text="Wind").click()
    clock_chip = page.locator("#topics .topic-chip", has_text="the little brass clock")
    expect(clock_chip).not_to_have_class(re.compile("topic-quiet"))
    expect(page.locator("#topics .topic-chip", has_text="the great clock")).to_have_class(
        re.compile("topic-quiet"))
    clock_chip.click()
    expect(page.locator("#chat")).to_contain_text("Not that one, friend")
    commands = [f for f in sent if f.get("kind") == "command"]
    assert [(c["verb"], c["dobj_id"]) for c in commands] == [("wind", "o-tace-hour-clock")]
    _assert_quiet(tab, engines)


def test_ask_staged_then_a_chip_still_asks(tab, engines):
    page, sent = _in_the_loft(tab)
    _record_frames(page, sent)
    page.reload()  # a fresh socket, so its frames are recorded
    expect(page.locator("#room-title")).to_contain_text("Loft")
    page.locator("#verb-bar button", has_text="Ask").click()
    expect(page.locator("#topics .topic-quiet")).to_have_count(0)
    page.locator("#topics .topic-chip", has_text="the little brass clock").click()
    expect(page.locator("#chat")).to_contain_text("You ask Tace about the little brass clock")
    commands = [f for f in sent if f.get("kind") == "command"]
    assert [(c["verb"], c["args"]) for c in commands] == [("ask", "the little brass clock")]
    _assert_quiet(tab, engines)


def test_words_for_a_chosen_verb_wait_out_a_drop(tab, engines):
    """Review NOTE 2026-09-29: words typed after choosing Talk were cleared,
    and the chosen verb dropped, when the socket could not take them."""
    page, _ = _in_the_loft(tab)
    page.locator("#verb-bar button", has_text="Talk").click()
    page.locator("#toons .obj", has_text="Tace").click()
    expect(page.locator("#verb-hint")).to_contain_text("Tace")
    page.evaluate(_DEAD_SOCKETS)
    page.evaluate("() => ws.close()")
    # onclose arms the drop timer; readyState turns CLOSED in the task that
    # fires it, so Enter after this finds the timer (review 2026-09-29f).
    page.wait_for_function("() => ws.readyState === WebSocket.CLOSED")
    page.locator("#input-text").fill("what is that little clock?")
    page.locator("#input-text").press("Enter")
    expect(page.locator("#dream-overlay")).to_have_text("the dream is sleeping...", timeout=500)
    expect(page.locator("#input-text")).to_have_value("what is that little clock?")
    page.evaluate("() => { window.WebSocket = window.__RealWebSocket; }")
    expect(page.locator("#dream-overlay")).to_be_hidden(timeout=15_000)
    expect(page.locator("#verb-hint")).to_contain_text("Tace")  # still talking to Tace
    expect(page.locator("#input-text")).to_have_value("what is that little clock?")
    _assert_quiet(tab, engines)
