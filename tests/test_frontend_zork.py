"""The Reading Room's Zork affordances (SPEC 2026-07-02 criterion 12),
tested at the served-asset grain the frontend suite uses: the behaviors
live in main.js/index.html/style.css and their server-data halves are
covered by the WS suites. The no-verb-name-hardcode requirement is
grep-provable here by contract."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

WEB = Path(__file__).resolve().parent.parent / "web"
MAIN_JS = (WEB / "assets" / "main.js").read_text()
INDEX = (WEB / "index.html").read_text()
CSS = (WEB / "assets" / "style.css").read_text()


def test_status_ribbon_renders_from_snapshot_status():
    assert 'id="status-ribbon"' in INDEX
    assert "renderStatusRibbon(snap.status)" in MAIN_JS
    # Ribbon shows only for worlds that author a rank ladder.
    assert "status.rank === null" in MAIN_JS
    for part in ("st-score", "st-rank", "st-moves", "st-light"):
        assert part in MAIN_JS


def test_free_text_prompting_is_verb_data_no_hardcode():
    """Criterion 12, grep-provable: the free-text prompt flow keys ONLY on
    verb_bar data (needs_text/text_prompt) — no verb-name string equality
    for prompting anywhere in main.js."""
    assert "needs_text" in MAIN_JS and "text_prompt" in MAIN_JS
    assert not re.search(r'verb\s*===\s*"talk"', MAIN_JS)
    assert not re.search(r'verb\s*===\s*"plant"', MAIN_JS)
    # The old hand-written prompts are gone with the hardcode.
    assert "say what to them?" not in MAIN_JS
    assert "where does the new way lead?" not in MAIN_JS


def test_container_contents_render_nested():
    assert "obj-nest" in MAIN_JS and "o.contents" in MAIN_JS
    assert ".obj-nest" in CSS


def test_darkness_veils_art_and_keeps_inventory():
    # The plate-dark class rides snapshot room.dark; CSS blacks the art.
    assert "plate-dark" in MAIN_JS and "snap.room.dark" in MAIN_JS
    assert ".plate-dark #room-bg" in CSS
    # Inventory rendering is unconditional (usable in the dark).
    assert 'renderObjects("inventory", lastInventory' in MAIN_JS


def test_death_interstitial_before_respawn_snapshot():
    assert 'id="death-overlay"' in INDEX
    assert "showDeathOverlay" in MAIN_JS
    assert "e.payload.died" in MAIN_JS
    assert ".death-overlay" in CSS


def test_clarify_options_render_as_buttons():
    assert 'data.kind === "clarify"' in MAIN_JS
    assert "renderClarify" in MAIN_JS and "clarify-opt" in MAIN_JS
    # Both slots resolve through the normal command frame.
    assert 'c.slot === "iobj"' in MAIN_JS
    assert ".evt-clarify .clarify-opt" in CSS


def test_put_staging_hint_uses_authored_preps():
    assert "spec.preps && spec.preps[0]" in MAIN_JS
