"""Benign-refusal regression corpus (SPEC 2026-07-07 criterion 8; closes
BACKLOG dialogue-refusal-fallback-on-benign-input).

The live-LLM attribution probe (tests/drift/test_dialogue_refusal_probe.py)
measured 0/21 fallbacks across Tace/Bell/Mott x 7 greetings on 2026-07-07
(evidence: tests/baselines/dialogue_refusal_probe.latest.json). These are the
deterministic halves that keep the benign path benign with zero LLM:

- the input banlist NEVER fires on greeting-class player text;
- the in-world craft vocabulary the loft/bunny NPCs actually speak (clocks,
  forges, lanterns) never trips the output banlist — the false-positive
  class the original observation suspected;
- blocked stays blocked: each banlist category still hits its own words, so
  loosening a pattern to fix a false positive can't silently disarm it."""

import pytest

from daydream.llm import safety

pytestmark = pytest.mark.tier_short

GREETINGS = [
    "hello", "hi", "hi there", "hello!", "good evening", "good day",
    "how are you?", "hello, friend", "what a lovely evening",
    "how goes the work?", "it's a quiet night", "greetings",
    "hullo", "hey", "good dusk to you", "may I watch you work?",
    "you keep a lovely shop", "evening", "hello there", "well met",
]

# Vocabulary the shipped worlds' NPCs naturally speak: horology, forge-craft,
# lantern-craft. None of it is "modern tech" in WHIMSY terms and none of it
# may hit any banlist category.
CRAFT_LINES = [
    "Tace turns the escapement gear in the lamplight and smiles at the clock's slow mechanism.",
    "The pendulum swings true; the whole movement ticks like a settled heart.",
    "Bell trims the lantern's wick and the square warms by one small pool of light.",
    "Rook works the bellows until the coals breathe; the anvil rings once, softly.",
    "Mott sweeps brass filings into a neat little drift beside the workbench.",
    "The kettle clicks on the hearthstone as the gears of the great clock settle.",
]

BLOCKED_BY_CATEGORY = {
    "pixel-art": "a crunchy pixel-art dungeon",
    "grimdark": "a grimdark dystopian wasteland",
    "modern-tech": "a laptop glowing on the desk",
    "urgency": "hurry, you must go immediately",
    "sarcasm": "don't be stupid about it",
}


@pytest.mark.parametrize("text", GREETINGS)
def test_greetings_never_trip_the_input_banlist(text):
    assert safety.first_banned(text) is None, text


@pytest.mark.parametrize("text", CRAFT_LINES)
def test_craft_vocabulary_never_trips_the_output_banlist(text):
    assert safety.first_banned(text) is None, text


@pytest.mark.parametrize("category,text", sorted(BLOCKED_BY_CATEGORY.items()))
def test_blocked_stays_blocked(category, text):
    assert safety.first_banned(text) == category
