"""Drift catcher: the WHIMSY_PROMPT_SUFFIX constant in
daydream/images/client.py must match the verbatim text under
WHIMSY.md's '## Prompt suffix' section.

WHIMSY.md is the durable source of truth for the project's tone.
The constant mirrors it because Python prompt construction needs
the string in code. If either side is edited without the other,
this test fails — that's the whole point.

Update path: edit WHIMSY.md '## Prompt suffix', then update the
constant in client.py to match (or vice-versa)."""

from pathlib import Path

import pytest

from daydream.images import client

WHIMSY = Path(__file__).resolve().parent.parent / "WHIMSY.md"


def _extract_prompt_suffix_block() -> str:
    """Pull the verbatim text inside the first triple-backtick block
    under WHIMSY.md's '## Prompt suffix' section."""
    text = WHIMSY.read_text()
    assert "## Prompt suffix" in text, "WHIMSY.md is missing the '## Prompt suffix' section"
    after_heading = text.split("## Prompt suffix", 1)[1]
    parts = after_heading.split("```", 2)
    assert len(parts) >= 3, "WHIMSY.md '## Prompt suffix' section is missing its code block"
    return parts[1].strip()


def _normalize(s: str) -> str:
    """Collapse all whitespace runs to a single space so a line wrap or
    extra newline in WHIMSY.md does not register as drift."""
    return " ".join(s.split())


def test_whimsy_md_block_matches_constant():
    md_block = _normalize(_extract_prompt_suffix_block())
    constant = _normalize(client.WHIMSY_PROMPT_SUFFIX)
    assert md_block == constant, (
        "WHIMSY.md '## Prompt suffix' has drifted from "
        "daydream/images/client.py:WHIMSY_PROMPT_SUFFIX. "
        "Update one to match the other.\n"
        f"  WHIMSY.md normalized:  {md_block!r}\n"
        f"  constant normalized:   {constant!r}"
    )


def test_whimsy_constant_mentions_anchor_terms():
    """Sanity floor: even if WHIMSY.md is rewritten, the suffix should still
    name the touchstones and reject the wrong aesthetics."""
    s = client.WHIMSY_PROMPT_SUFFIX.lower()
    assert "watercolor" in s, "prompt suffix lost the 'watercolor' anchor"
    assert "spiritfarer" in s or "short hike" in s, "prompt suffix lost the touchstone reference"
