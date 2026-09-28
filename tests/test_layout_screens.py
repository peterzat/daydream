"""The page fits the screens friends use, in more than one engine (playtest
2026-09-28: on an iPad mini in Safari the compass and the footer sat on the
screen's bottom edge, under the home indicator).

Layout rules, not pixel baselines: each screen opens an invitation and the
front door, signs in, lands in the start room, then leaves the dream. At each
stop the page must not scroll sideways; the door's whole form must be
reachable; on the desktop shell (wider than 640px) the whole leaf must fit
the window with its foot clear of the bottom edge; on a phone the page
scrolls and its foot ends clear of the bottom. Pixel snapshots churn with every
painting and font; these rules hold across both. Set DAYDREAM_LAYOUT_SHOTS
to a directory to also save a screenshot of every stop, for grading by eye.

What emulation cannot show: Playwright's WebKit is desktop WebKit, with no
collapsing toolbar (dvh acts like vh) and safe-area insets of 0. The iOS fix
itself (dvh and the safe-area inset, index.html's viewport-fit=cover) is held
by the static test at the end; a real device is the final check.

Engines: Chromium and Firefox run here; WebKit needs system libraries once
(`sudo .venv/bin/python -m playwright install-deps webkit`) and skips with
that reason until then."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

from daydream import accounts, toons  # noqa: E402
from tests.test_browser_flow import PASSWORD, START, live_server  # noqa: E402,F401 (fixture)

pytestmark = pytest.mark.tier_medium

ROOT = Path(__file__).resolve().parent.parent
FOOT_CLEARANCE = 8  # px between the leaf's foot and the window's bottom edge
WEBKIT_DEPS = "sudo .venv/bin/python -m playwright install-deps webkit"


@dataclass(frozen=True)
class Screen:
    name: str
    engine: str
    width: int
    height: int  # the area a page gets, the browser's own bars excluded
    touch: bool = False


SCREENS = [
    Screen("desktop", "chromium", 1440, 900),
    Screen("laptop-short", "chromium", 1280, 650),
    Screen("laptop-firefox", "firefox", 1366, 768),
    Screen("ipad-mini-portrait", "chromium", 744, 1063, touch=True),
    Screen("ipad-mini-landscape", "chromium", 1133, 702, touch=True),
    Screen("ipad-mini-safari", "webkit", 744, 1063, touch=True),
    Screen("iphone-safari", "webkit", 390, 664, touch=True),
    Screen("phone", "chromium", 390, 664, touch=True),
]

MEASURE = """() => {
  const box = (sel) => {
    const e = document.querySelector(sel);
    if (!e || !e.getClientRects().length) return null;
    const b = e.getBoundingClientRect();
    return {top: b.top, bottom: b.bottom, left: b.left, right: b.right};
  };
  const de = document.documentElement;
  return {vw: window.innerWidth, vh: window.innerHeight, sw: de.scrollWidth,
          sh: de.scrollHeight, page: box("main.page"), footer: box("footer"),
          ways: box(".ways"), prose: box(".prose")};
}"""


@pytest.fixture(scope="module")
def engines():
    """One browser per engine for the module, or the reason it cannot run."""
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as e:
        pytest.skip(f"playwright driver unavailable: {e}")
    launched: dict[str, object] = {}
    for name in ("chromium", "firefox", "webkit"):
        try:
            launched[name] = getattr(pw, name).launch()
        except Exception as e:
            first = (str(e).strip().splitlines() or [""])[0]
            hint = f"; once: {WEBKIT_DEPS}" if name == "webkit" else ""
            launched[name] = f"{name} cannot run here ({first[:120]}){hint}"
    yield launched
    for b in launched.values():
        if not isinstance(b, str):
            b.close()
    pw.stop()


def _shot(page, screen: Screen, stop: str) -> None:
    out = os.environ.get("DAYDREAM_LAYOUT_SHOTS")
    if out:
        Path(out).mkdir(parents=True, exist_ok=True)
        page.screenshot(path=str(Path(out) / f"{screen.name}-{stop}.png"))


def _scrolls_sideways(page) -> bool:
    return page.evaluate("""() => {
      window.scrollTo(400, window.scrollY);
      const moved = window.scrollX > 0;
      window.scrollTo(0, window.scrollY);
      return moved;
    }""")


def _at_the_end(page) -> dict:
    """Measure with the page scrolled as far down as it goes."""
    page.evaluate("() => window.scrollTo(0, document.documentElement.scrollHeight)")
    m = page.evaluate(MEASURE)
    page.evaluate("() => window.scrollTo(0, 0)")
    return m


def _fits(page, screen: Screen, stop: str) -> None:
    """The layout rules, checked where the page stands now."""
    m = page.evaluate(MEASURE)
    where = f"{screen.name} at {stop}: {m}"
    assert not _scrolls_sideways(page), "the page scrolls sideways; " + where
    if m["footer"] is None:
        # The front door: its whole form can be reached, however short the window.
        end = _at_the_end(page)
        assert end["page"]["bottom"] <= end["vh"] + 1, "the door's foot is out of reach; " + where
    elif screen.width > 640:
        # The desktop shell: the whole leaf in the window, its foot clear.
        assert m["page"]["bottom"] <= m["vh"] - FOOT_CLEARANCE, "the leaf's foot; " + where
        assert m["footer"]["bottom"] <= m["vh"] - FOOT_CLEARANCE, "the footer; " + where
        if m["ways"] is not None:
            assert m["ways"]["bottom"] <= m["footer"]["top"] + 1, where
        if m["prose"] is not None:
            assert m["prose"]["bottom"] - m["prose"]["top"] >= 120, (
                "the reading column has almost no height; " + where)
    else:
        # A phone: the page scrolls, and at its end the leaf's foot is clear.
        end = _at_the_end(page)
        assert end["page"]["bottom"] <= end["vh"] - FOOT_CLEARANCE, "the leaf's foot; " + where
        for part in ("ways", "footer"):
            if end[part] is not None:
                assert end[part]["right"] <= end["vw"] + 1, f"{part} runs off the side; " + where
    _shot(page, screen, stop)


@pytest.mark.parametrize("screen", SCREENS, ids=[s.name for s in SCREENS])
def test_the_page_fits_the_screen(screen: Screen, engines, live_server):
    browser = engines[screen.engine]
    if isinstance(browser, str):
        pytest.skip(browser)
    friend = accounts.create_account("marlo", PASSWORD, display_name="A Friend")
    toons.create_toon_in_slot(1, "Marlo", "a tall heron in a patched blue coat",
                              "s-an-earlier-evening", owner_account=friend["id"])
    opts = {"base_url": live_server,
            "viewport": {"width": screen.width, "height": screen.height}}
    if screen.touch:
        opts["has_touch"] = True
        if screen.engine != "firefox":
            opts["is_mobile"] = True
    context = browser.new_context(**opts)
    context.set_default_timeout(10_000)
    page = context.new_page()
    errors: list[str] = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script("try { localStorage.setItem('dd-help-seen', '1'); } catch (e) {}")
    try:
        slug, _ = accounts.create_invite("A Friend")
        page.goto(f"/invite/{slug}")
        sync_api.expect(page.locator("#invite-form")).to_be_visible()
        _fits(page, screen, "invite")
        page.goto("/login")
        _fits(page, screen, "door")
        form = page.locator("#login-form")
        form.locator("input[name=username]").fill("marlo")
        form.locator("input[name=password]").fill(PASSWORD)
        form.locator("button[type=submit]").click()
        page.wait_for_url(live_server + "/")
        sync_api.expect(page.locator("#room-title")).to_have_text(START["title"])
        page.wait_for_timeout(300)  # the arrival settles (fonts, the plate)
        _fits(page, screen, "room")
        page.locator("#leave-dream").click()
        sync_api.expect(page.locator("#awake")).to_be_visible()
        _fits(page, screen, "awake")
        assert errors == [], errors
    finally:
        context.close()


def test_the_shell_uses_the_visible_height_and_keeps_clear_of_the_home_indicator():
    """What emulation cannot reproduce, held statically: iOS Safari's 100vh
    counts the space behind its own bars, so the shell sizes by dvh (with vh
    as the fallback) and keeps the safe-area inset under its foot, and the
    page asks for the inset with viewport-fit=cover."""
    css = (ROOT / "web/assets/style.css").read_text()
    html = (ROOT / "web/index.html").read_text()
    assert "viewport-fit=cover" in html
    shell = css[css.index("@media (min-width: 641px) {"):]
    for rule in ("height: calc(100dvh - 24px - env(safe-area-inset-bottom, 0px));",
                 "height: calc(100dvh - 16px - env(safe-area-inset-bottom, 0px));",
                 "margin: 12px auto calc(12px + env(safe-area-inset-bottom, 0px));",
                 "margin: 8px auto calc(8px + env(safe-area-inset-bottom, 0px));"):
        assert rule in shell, rule
    phone = css[css.index("@media (max-width: 640px) {"):]
    assert "calc(24px + env(safe-area-inset-bottom, 0px))" in phone
