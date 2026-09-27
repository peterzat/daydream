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


CSS = (WEB / "assets/style.css").read_text()


def test_the_reading_column_is_one_scroll_that_never_clips():
    """Operator 2026-09-27: on a short window the room description was cut
    mid-sentence and the log had no height. The desktop reading column
    scrolls as one (description and log together), the header shrinks with
    the window, new lines pin to the bottom, and entering a room opens on its
    description."""
    shell = CSS[CSS.index("@media (min-width: 641px) {"):]
    assert re.search(r"\.prose \{[^}]*overflow-y: auto", shell)
    assert re.search(r"#chat \{[^}]*overflow: visible", shell)
    assert "clamp(76px" in shell and "max-height: 760px" in CSS
    assert "function pinLog()" in JS and "function showRoomTop()" in JS
    assert "chat.scrollTop = chat.scrollHeight;" in JS.split("function pinLog()")[1][:600]
    assert JS.count("pinLog();") >= 9


def test_input_history_and_topic_overflow():
    assert 'ev.key !== "ArrowUp"' in JS and "inputHistory" in JS
    assert "TOPIC_SHOW = 6" in JS and "topic-more" in JS


def test_phones_never_scroll_sideways():
    phone = CSS[CSS.index("@media (max-width: 640px) {"):]
    assert "overflow-x: hidden" in phone.split("}")[0] + phone.split("}")[1]


# ---- codereview 2026-09-27 ------------------------------------------------


def test_the_drop_cap_stays_in_its_paragraph_and_a_hidden_book_link_hides():
    assert re.search(r"\.room-desc \{[^}]*display: flow-root", CSS)
    assert ".satchel-link.hidden { display: none; }" in CSS


def test_a_slept_note_survives_the_redeploy_reload():
    reload_branch = JS.split("if (triggerUpdateReload()) {")[1][:300]
    assert "stashSleptNote(snap.while_you_slept)" in reload_branch
    assert "else if (carriedNote) showSleptPage(carriedNote);" in JS


def test_the_picker_clears_every_story_surface():
    body = JS.split("function clearSceneAndLog()")[1].split("\nfunction ")[0]
    for call in ("renderTopics([])", "renderFolio(null)", "lastBook = null", "closeBook()",
                 'getElementById("book-toggle").classList.add("hidden")',
                 'getElementById("slept-panel").classList.add("hidden")'):
        assert call in body, call


def test_a_same_room_snapshot_keeps_a_scrolled_up_reader_in_place():
    assert "snap.room.id === lastArrivalRoomId" in JS
    assert "for (const [el, top] of keptScroll) el.scrollTop = top;" in JS


def test_down_never_erases_a_half_typed_line():
    assert 'if (ev.key === "ArrowDown" && !browsing) return;' in JS
    assert "historyDraft = inp.value" in JS


def test_a_clarify_click_carries_the_typed_words():
    assert 'sendCommand(c.verb, opt.id, c.args || "", c.iobj_id)' in JS
    assert 'sendCommand(c.verb, c.dobj_id, c.args || "", opt.id)' in JS
