"""A first friend's ten minutes, in a real browser (playtest 2026-09-28b,
docs/playtests/2026-09-28-first-friend.md). Each test holds one fix from that
pass against headless Chromium, on the harness test_browser_flow.py built."""

from __future__ import annotations

import re

import pytest

from daydream import accounts, objects, toons
from tests.test_browser_flow import (  # noqa: F401 (fixtures)
    PASSWORD, START, UP, Tab, _assert_quiet, _in_the_start_room, _signed_in_with_a_dreamer,
    browser, engines, expect, live_server, tab,
)

pytestmark = pytest.mark.tier_medium


def _sign_in_fresh_browser(tab: Tab, name: str = "Marlo"):
    """A friend with a dreamer signs in from a browser that has never shown
    the guide (a second device)."""
    friend = accounts.create_account(name.lower(), PASSWORD, display_name="A Friend")
    toons.create_toon_in_slot(1, name, "round spectacles, a patched blue coat",
                              "s-an-earlier-evening", owner_account=friend["id"])
    page = tab.page
    page.goto("/login")
    form = page.locator("#login-form")
    form.locator("input[name=username]").fill(name.lower())
    form.locator("input[name=password]").fill(PASSWORD)
    form.locator("button[type=submit]").click()
    page.wait_for_url(tab.base + "/")
    _in_the_start_room(page, name)
    return page


def test_leaving_from_a_second_device_does_not_open_the_guide(tab, engines):
    """A second device walked straight in (no guide), and leaving there opened
    the guide as the friend went. The guide is for a first visit only."""
    page = _sign_in_fresh_browser(tab)
    expect(page.locator("#help-panel")).to_be_hidden()
    page.locator("#leave-dream").click()
    expect(page.locator("#awake-text")).to_contain_text("Marlo is resting in the village")
    page.wait_for_timeout(300)  # the dreamer read has settled
    expect(page.locator("#help-panel")).to_be_hidden()
    _assert_quiet(tab, engines)


def test_typing_help_opens_the_guide(tab, engines):
    page = _signed_in_with_a_dreamer(tab)
    page.locator("#input-text").fill("help")
    page.locator("#input-text").press("Enter")
    expect(page.locator("#help-panel")).to_be_visible()
    expect(page.locator("#chat")).not_to_contain_text("help")
    _assert_quiet(tab, engines)


WELCOME = "Tace looks up from the bench and beckons you over to the warm lamp."


def test_a_welcome_a_move_causes_follows_the_arrival_line_undimmed(tab, engines):
    """A resident's welcome (a room enter rule) landed above the arrival line,
    dimmed as an earlier line."""
    objects.set_property(UP["id"], "rules", [
        {"on": "enter", "do": [{"kind": "narrate", "to": "@actor", "text": WELCOME}]}])
    page = _signed_in_with_a_dreamer(tab)
    page.locator("#exit-bar button[data-direction=up]").click()
    expect(page.locator("#room-title")).to_have_text(UP["title"])
    welcome = page.locator("#chat .evt", has_text="beckons you over")
    expect(welcome).to_have_count(1)
    order = page.evaluate("""() => [...document.querySelectorAll('#chat > .evt')]
        .map((e) => [e.classList.contains('evt-arrival') ? 'arrival' : e.textContent.slice(0, 24),
                     e.classList.contains('evt-earlier')])""")
    names = [o[0] for o in order]
    assert names.index("arrival") < next(i for i, o in enumerate(order) if o[0].startswith("Tace looks")), order
    assert not re.search(r"evt-earlier", welcome.get_attribute("class")), order
    # The resident named in the welcome does not greet again.
    expect(page.locator("#chat .evt", has_text=re.compile(r"^Tace (stands|is|works)"))).to_have_count(0)
    _assert_quiet(tab, engines)
