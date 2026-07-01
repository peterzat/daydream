"""Design-token drift probe: DESIGN.md's token table stays synchronized with
the CSS `:root` custom properties.

The interface counterpart to test_drift_constants.py's WHIMSY check. The design
tokens (palette, typography, radius, shadow) are the single source of truth for
the SPA's look; they live once in web/assets/style.css `:root` and are mirrored
in DESIGN.md's "Design tokens" table. This test extracts both, normalizes
whitespace/format, and asserts they are identical, so a one-sided edit fails the
pre-commit gate (tier_short) rather than silently drifting the two apart.

Edit either side and you must edit the other; DESIGN.md is the durable source.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DESIGN_MD = PROJECT_ROOT / "DESIGN.md"
STYLE_CSS = PROJECT_ROOT / "web" / "assets" / "style.css"


def _normalize(value: str) -> str:
    """Canonicalize a token value so cosmetic differences (comment, line wrap,
    space after a comma, wrapping backticks, trailing semicolon) do not register
    as drift, while any real change in content does."""
    value = re.sub(r"/\*.*?\*/", "", value, flags=re.S)  # strip CSS comments
    value = value.replace("`", "")  # tolerate backticked cells in the md table
    value = " ".join(value.split())  # collapse whitespace runs
    value = re.sub(r"\s*,\s*", ",", value)  # normalize comma spacing (font stacks)
    return value.strip().rstrip(";").strip()


def _tokens_from_css() -> dict[str, str]:
    text = STYLE_CSS.read_text()
    m = re.search(r":root\s*\{(.*?)\}", text, flags=re.S)
    assert m, "web/assets/style.css has no `:root { ... }` block"
    tokens: dict[str, str] = {}
    for line in m.group(1).splitlines():
        lm = re.match(r"\s*(--[a-z0-9-]+)\s*:\s*(.+?);\s*(?:/\*.*)?$", line)
        if lm:
            tokens[lm.group(1)] = _normalize(lm.group(2))
    return tokens


def _tokens_from_design() -> dict[str, str]:
    """Parse rows of the DESIGN.md token table: `| \\`--name\\` | value |`.
    The backtick-wrapped name is required, which skips the header and the
    `|---|---|` separator rows automatically."""
    text = DESIGN_MD.read_text()
    tokens: dict[str, str] = {}
    for line in text.splitlines():
        rm = re.match(r"\s*\|\s*`(--[a-z0-9-]+)`\s*\|\s*(.+?)\s*\|\s*$", line)
        if rm:
            tokens[rm.group(1)] = _normalize(rm.group(2))
    return tokens


def test_design_tokens_match_css():
    css = _tokens_from_css()
    design = _tokens_from_design()
    assert css, "no `--tokens` found in web/assets/style.css :root"
    assert design, "no token table rows found in DESIGN.md"

    only_css = sorted(set(css) - set(design))
    only_design = sorted(set(design) - set(css))
    mismatched = sorted(
        k for k in (set(css) & set(design)) if css[k] != design[k]
    )
    detail = "\n".join(
        [f"  value drift  {k}: css={css[k]!r} design={design[k]!r}" for k in mismatched]
        + [f"  css only     {k}: {css[k]!r}" for k in only_css]
        + [f"  design only  {k}: {design[k]!r}" for k in only_design]
    )
    assert css == design, (
        "drift between DESIGN.md 'Design tokens' table and web/assets/style.css "
        ":root.\n" + detail + "\nedit either side to match; DESIGN.md is the "
        "durable design source."
    )


def test_design_tokens_cover_the_core_set():
    """Belt-and-suspenders: even when both sides match, the reconciled core set
    (the mockup adoption) must be present, so a future edit can't quietly drop
    the palette/typography contract by deleting a row on BOTH sides."""
    tokens = _tokens_from_css()
    for required in (
        "--bg", "--paper", "--ink", "--sage", "--sage-deep", "--amber",
        "--line", "--speaker", "--table", "--parch", "--quest",
        "--serif", "--sans", "--hand",
    ):
        assert required in tokens, f"design token {required} missing from :root"
    # The legacy alias was renamed; it must not linger.
    assert "--warm" not in tokens, "--warm was renamed to --amber; drop the alias"
