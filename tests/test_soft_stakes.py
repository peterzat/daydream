"""Tone tells the truth (SPEC 2026-09-26 criterion 21): WHIMSY's stories
section allows soft stakes, and the safety banlist matches it. A corpus of
soft-stakes lines (wants, loss, missing someone, waiting, gentle time,
bittersweet endings, a remembered death) passes; each still-banned category
still blocks its own words."""

import pytest

from daydream.llm import safety

pytestmark = pytest.mark.tier_short

SOFT_STAKES = [
    "The nap misses Pim, though it could not tell you how.",
    "If no one sings it home, it will fall asleep in a jar in the cellar, kept, and a little sad.",
    "Bell has never seen a dawn, and says it doesn't matter. It matters.",
    "Tace's hands go still; the clock stopped the night Wend died.",
    "The letter was never sent. Fen keeps it anyway, in case.",
    "Some hours go home and some stay; both are a kind of goodbye.",
    "Bell hurries across the square with the ladder, humming.",
    "It has been waiting three days for someone to remember its name.",
    "Mott is a little afraid of the oldest minute in his tin.",
    "The summer can't remember its own name, and it wants to, very much.",
    "She fell asleep before the song, and has wondered about it ever since.",
    "Grief is only love with nowhere to go, Umber says, and labels the jar.",
    "The festival is in three days and nothing is ready, and everyone is laughing about it.",
    "Losing an hour isn't a failing. It's just an hour someone couldn't carry.",
]

STILL_BANNED = {
    "pixel-art": "a crunchy 8-bit sprite of the square",
    "grimdark": "a horror lurks in the cellar",
    "sexual": "a sensual glance across the lanterns",
    "violence": "Bell tries to stab the moth",
    "urgency": "you must hurry up, there's no time to lose",
    "modern-tech": "a smartphone buzzes on the bench",
    "sarcasm": "what a pathetic little idiot you are",
}


@pytest.mark.parametrize("line", SOFT_STAKES)
def test_soft_stakes_pass_the_banlist(line):
    assert safety.first_banned(line) is None, line


@pytest.mark.parametrize("category,line", sorted(STILL_BANNED.items()))
def test_every_banned_category_still_blocks(category, line):
    assert safety.first_banned(line) == category


def test_whimsy_carries_the_stories_section():
    from pathlib import Path

    text = (Path(__file__).resolve().parent.parent / "WHIMSY.md").read_text()
    assert "## Stories: soft stakes" in text
    for word in ("Wants", "Bittersweet", "cruelty", "horror", "grimdark"):
        assert word in text
