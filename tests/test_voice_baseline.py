"""Probe over the captured voice-samples baselines that catches the
class of template-induced opener tic that surfaced in the 04-24 AWQ
baseline. Parses the markdown the harness writes (no GPU), extracts
the body-language opener of each of the 5 narrate sections, and
asserts pairwise-distinct openers as the durable post-fix property.

The probe is regression-demonstrated: it passes against the 05-06
baseline (the post-fix substrate; 5/5 distinct) and FAILS against the
04-24 baseline (the pre-fix substrate; 4/5 share an opener). Both
behaviors are verified via a parametrized test so a future PR that
introduces a new template tic surfaces here as a tier_short failure.

Heuristic for the body-language opener: substring of the narrate text
from its start through the dialog-opening single-quote that precedes
Rook's spoken line. Apostrophes inside words ("Rook's", "today's")
are skipped via a negative lookbehind so the first MATCHED quote is
the dialog open, not a possessive."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short


VOICE_SAMPLES_DIR = Path(__file__).parent.parent / "docs" / "pretty" / "voice-samples"

# Match each captured prompt section: `### <name>` ... `**Narrate:**` ... `> <narrate>`
# Stops at the next `### ` heading or EOF. The harness writes one narrate per
# section as a single blockquote line, so `(.+?)` captures the full text.
_SECTION_RE = re.compile(
    r"### (\w+)\s*\n"
    r".*?\*\*Narrate:\*\*\s*\n\n"
    r"> (.+?)(?=\n\n### |\Z)",
    re.DOTALL,
)

# Match a single-quote not preceded by a letter — the dialog-opening quote,
# not a possessive apostrophe inside a word.
_DIALOG_QUOTE_RE = re.compile(r"(?<![A-Za-z])'")


def _parse_narrate_sections(md: str) -> list[tuple[str, str]]:
    """Return [(name, narrate_text), ...] for each captured prompt."""
    return [(name, narrate.strip()) for name, narrate in _SECTION_RE.findall(md)]


def _opener_of(narrate: str) -> str:
    """Body-language opener: substring through the dialog-opening single-quote."""
    m = _DIALOG_QUOTE_RE.search(narrate)
    return narrate[: m.start()] if m else narrate


@pytest.mark.parametrize(
    "baseline_name,expect_distinct",
    [
        # Post-fix substrate (this turn's prompt-template variety pass).
        # Strict criterion 2 of the 2026-05-06 prior spec: 5/5 distinct.
        ("2026-05-06-qwen2.5-7b-instruct-awq.md", True),
        # Pre-fix substrate (frozen in tree as durable before-shot).
        # 4/5 share the "Rook pauses the steady rhythm of the bellows,
        # wiping hands on the apron, and says," tic. Asserting that
        # duplicates exist here is what proves the probe catches the
        # regression class — if someone re-introduces the tic in a
        # future template change, the post-fix baseline check fails.
        ("2026-04-24-qwen2.5-7b-instruct-awq.md", False),
    ],
)
def test_voice_baseline_opener_distinctness(baseline_name: str, expect_distinct: bool) -> None:
    path = VOICE_SAMPLES_DIR / baseline_name
    assert path.exists(), f"baseline file missing: {path}"
    sections = _parse_narrate_sections(path.read_text())
    assert len(sections) == 5, (
        f"{baseline_name}: expected 5 narrate sections, got {len(sections)} "
        f"({[name for name, _ in sections]})"
    )
    openers = [_opener_of(narrate) for _, narrate in sections]
    distinct = len(set(openers)) == 5
    if expect_distinct:
        if not distinct:
            dupes = [o for o in openers if openers.count(o) > 1]
            pytest.fail(
                f"{baseline_name}: expected 5 distinct body-language openers, "
                f"but found duplicates: {sorted(set(dupes))}"
            )
    else:
        assert not distinct, (
            f"{baseline_name}: expected pre-fix baseline to retain its "
            f"opener tic (4/5 share an opener), but all 5 openers are now "
            f"distinct. Did the file get re-captured or overwritten?"
        )


def test_dialog_quote_skips_apostrophes() -> None:
    """The opener heuristic must skip apostrophes inside words. A narrate
    like 'Rook's eyes drift up...' should yield the full body-language
    clause, not just 'Rook'."""
    narrate = "Rook's eyes drift up from the bellows, and they say, 'hello there.'"
    assert _opener_of(narrate) == "Rook's eyes drift up from the bellows, and they say, "


def test_dialog_quote_handles_no_quote() -> None:
    """If a narrate contains no dialog quote (degenerate case, e.g. a
    truncated model response), the heuristic returns the full text rather
    than crashing."""
    assert _opener_of("Rook nods and goes back to work") == "Rook nods and goes back to work"
