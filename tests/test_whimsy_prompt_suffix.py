"""The WHIMSY prompt-suffix drift guard (plan 2026-07-02, prompt audit).

WHIMSY.md's `## Prompt suffix` block is the canonical tone suffix; the
runtime copy is `daydream.images.client.WHIMSY_PROMPT_SUFFIX`. Both
CLAUDE.md and the constant's own comment have cited this test since the
suffix landed — the audit found it had never actually been written. Same
one-sided-edit model as tests/drift/test_design_tokens.py: change either
side alone and this fails."""

import re
from pathlib import Path

import pytest

from daydream.images.client import (
    PORTRAIT_FRAMING_CLAUSE,
    PORTRAIT_PROMPT_SUFFIX,
    WHIMSY_PROMPT_SUFFIX,
)

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent


def _doc_block(section_header: str) -> str:
    text = (ROOT / "WHIMSY.md").read_text()
    section = text.split(section_header, 1)[1]
    m = re.search(r"```\n(.*?)```", section, re.DOTALL)
    assert m, f"WHIMSY.md {section_header!r} section lost its code block"
    # The doc wraps the one-line suffix for readability; collapse whitespace.
    return " ".join(m.group(1).split())


def test_whimsy_suffix_matches_the_tone_bible():
    assert " ".join(WHIMSY_PROMPT_SUFFIX.split()) == _doc_block("## Prompt suffix"), (
        "WHIMSY_PROMPT_SUFFIX and WHIMSY.md '## Prompt suffix' have drifted; "
        "update both together (cache keys do NOT fold the suffix, but new "
        "renders and the aesthetic goldens follow it)"
    )


def test_portrait_framing_clause_matches_the_tone_bible():
    """The portrait suffix's framing clause mirrors WHIMSY.md '## Portrait
    prompt suffix' — same one-sided-edit drift model as the room suffix."""
    assert " ".join(PORTRAIT_FRAMING_CLAUSE.split()) == _doc_block(
        "## Portrait prompt suffix"
    ), (
        "PORTRAIT_FRAMING_CLAUSE and WHIMSY.md '## Portrait prompt suffix' "
        "have drifted; update both together"
    )
    # The full portrait suffix is the clause + the shared WHIMSY suffix.
    assert PORTRAIT_PROMPT_SUFFIX == f"{PORTRAIT_FRAMING_CLAUSE}, {WHIMSY_PROMPT_SUFFIX}"
