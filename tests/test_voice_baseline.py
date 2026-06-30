"""Probe over the captured voice-samples baselines that catches the
class of template-induced opener tic that surfaced in the 04-24 AWQ
baseline. Parses the markdown the harness writes (no GPU), extracts
the body-language opener of each of the 5 narrate sections, and
asserts pairwise-distinct openers as the durable post-fix property.

The parametrization is GLOB-DERIVED, not a hand-edited list: every
`docs/pretty/voice-samples/*.md` is classified by an optional
`<!-- baseline-class: ... -->` marker (`_discover_baselines`). A tracked
baseline (the default for an unmarked file) must show 5/5 distinct openers;
the frozen pre-fix `regression-demo` must retain its tic; the two rejected
Mistral-Nemo `documented-failure` captures are excluded. So dropping a new
committed voice-bench markdown extends the regression set with no code edit
(BACKLOG voice-baseline-add-model-helper), and a future PR that introduces a
new template tic surfaces here as a tier_short failure.

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


# An optional `<!-- baseline-class: ... -->` marker classifies each committed
# baseline so the parametrization is glob-derived, not a hand-edited list:
#   tracked            -> openers must be 5/5 distinct (a known-good capture).
#   regression-demo    -> openers must NOT be distinct (a frozen pre-fix
#                         before-shot that proves the probe catches the tic).
#   documented-failure -> excluded entirely (a frozen rejected-model capture).
# UNMARKED defaults to 'tracked', so a fresh capture of the production model
# (or a future successful A/B) auto-extends the regression set with no code
# edit; a future failure is opted out with one marker line.
_CLASS_RE = re.compile(r"<!--\s*baseline-class:\s*([a-z-]+)")


def _baseline_class(md: str) -> str:
    m = _CLASS_RE.search(md)
    return m.group(1) if m else "tracked"


def _discover_baselines() -> list:
    """Glob the committed voice-sample markdown and turn each non-excluded
    file into a parametrize case (filename, expect_distinct)."""
    params = []
    for p in sorted(VOICE_SAMPLES_DIR.glob("*.md")):
        cls = _baseline_class(p.read_text())
        if cls == "documented-failure":
            continue
        # tracked (and any unrecognized class) -> distinct; demo -> not distinct.
        params.append(pytest.param(p.name, cls != "regression-demo", id=p.stem))
    return params


@pytest.mark.parametrize("baseline_name,expect_distinct", _discover_baselines())
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


def test_baseline_class_discriminator() -> None:
    """Unmarked defaults to tracked; the two non-default markers are read."""
    assert _baseline_class("# Voice samples\n\nno marker here") == "tracked"
    assert _baseline_class("x <!-- baseline-class: documented-failure --> y") == "documented-failure"
    assert _baseline_class("<!--baseline-class:  regression-demo  -->") == "regression-demo"


def test_discovery_excludes_failures_and_auto_covers_tracked() -> None:
    """The glob-derived param set excludes the Mistral-Nemo documented-failures
    and auto-covers every tracked AWQ baseline (including ones added after this
    test was written), plus the regression-demo before-shot. This is the
    'add a baseline with no code edit' contract."""
    ids = {p.id for p in _discover_baselines()}
    # Both rejected-model captures are opted out.
    assert "2026-05-06-mn-12b-rp-ink-q4_k_m" not in ids
    assert "2026-05-07-mistral-nemo-instruct-2407" not in ids
    # The pre-fix before-shot stays (as a regression-demo) and the post-fix +
    # latest AWQ captures are both covered without being named in any list.
    assert "2026-04-24-qwen2.5-7b-instruct-awq" in ids
    assert "2026-05-06-qwen2.5-7b-instruct-awq" in ids
    assert "2026-06-30-qwen2.5-7b-instruct-awq" in ids
