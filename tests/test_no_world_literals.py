"""Criterion 2 (SPEC 2026-07-02): Zork ships as DATA; the engine stays
world-agnostic. Engine code (daydream/**, web/assets/**) contains no
Zork-specific literals — every Zork behavior loads from the format-2 world
envelope, and engine primitives carry generic names and authored text. The
worlds/, tests/, and docs trees are exempt (that's where the world lives)."""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
LITERALS = ("zork", "grue", "troll", "cyclops", "frobozz", "zorkmid", "barrow")

ENGINE_GLOBS = ("daydream/**/*.py", "web/assets/*.js", "web/assets/*.css",
                "web/*.html")


def engine_files():
    for pattern in ENGINE_GLOBS:
        yield from ROOT.glob(pattern)


def test_engine_code_has_no_zork_literals():
    # Word boundaries: "troll" must not fire inside "controller_session".
    pattern = re.compile(r"\b(" + "|".join(LITERALS) + r")\b", re.IGNORECASE)
    offenders: list[str] = []
    for path in engine_files():
        if "__pycache__" in str(path):
            continue
        for lineno, line in enumerate(path.read_text().splitlines(), 1):
            if pattern.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}: {line.strip()}")
    assert not offenders, (
        "Zork literals in engine code (world content belongs in worlds/):\n"
        + "\n".join(offenders[:20])
    )


def test_the_gate_itself_sees_engine_files():
    # The guard is only meaningful if the globs actually match the engine.
    files = list(engine_files())
    names = {f.name for f in files}
    assert "verbs.py" in names and "main.js" in names and len(files) > 30
