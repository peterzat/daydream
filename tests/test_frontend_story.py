"""The SPA's story surfaces (SPEC 2026-09-26 criteria 6, 12, 15), checked
statically against the committed assets: topic chips send the ask verb (a
click, never an id typed by a player), the folio shows the village's time,
the satchel opens the per-player Book of Stray Minutes, and a dream's
"while you slept" note opens as a dismissible leaf."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

WEB = Path(__file__).resolve().parent.parent / "web"
HTML = (WEB / "index.html").read_text()
JS = (WEB / "assets/main.js").read_text()


def test_the_shell_has_the_story_surfaces():
    for el in ('id="topics"', 'id="folio"', 'id="book-toggle"', 'id="book-panel"',
               'id="slept-panel"', 'id="slept-close"', 'id="book-close"'):
        assert el in HTML, el


def test_topic_chips_send_the_ask_verb():
    assert re.search(r'sendCommand\("ask", t\.id, label\)', JS)
    assert "renderTopics(others)" in JS


def test_while_you_slept_opens_a_dismissible_leaf():
    assert "if (snap.while_you_slept) showSleptPage(snap.while_you_slept);" in JS
    assert 'getElementById("slept-close").addEventListener("click"' in JS


def test_the_book_renders_from_the_snapshot_and_the_folio_shows_time():
    assert "lastBook = snap.book || null;" in JS
    assert "renderFolio(snap.time);" in JS
    assert '"day " + time.day' in JS
