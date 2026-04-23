"""WHIMSY.md exists with the named sections SPEC criterion 1 requires."""

from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

WHIMSY = Path(__file__).resolve().parent.parent / "WHIMSY.md"


def test_whimsy_file_exists():
    assert WHIMSY.exists(), "WHIMSY.md must live at the project root"
    assert WHIMSY.stat().st_size > 500, "WHIMSY.md must be a real document, not a stub"


@pytest.mark.parametrize(
    "section",
    ["## Touchstones", "## Palette", "## Voice samples", "## Banned moods", "## Prompt suffix"],
)
def test_whimsy_named_sections(section: str):
    text = WHIMSY.read_text()
    assert section in text, f"WHIMSY.md must contain the {section!r} section"


def test_whimsy_anchors_spiritfarer_and_short_hike():
    text = WHIMSY.read_text()
    assert "Spiritfarer" in text
    assert "Short Hike" in text


def test_whimsy_explicitly_rejects_pixel_art():
    text = WHIMSY.read_text().lower()
    assert "pixel-art" in text or "pixel art" in text
    # And the rejection is in the right direction — appears under banned moods.
    banned_section = text.split("## banned moods", 1)[1]
    assert "pixel" in banned_section
