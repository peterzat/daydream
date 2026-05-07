"""Tests for daydream/toons.py read + write helpers.

The read helpers (`get_toon`, `get_toons_in_room`, `find_toon_in_room_by_name`)
are exercised end-to-end through `tests/test_ws*.py` and `tests/test_skills.py`;
this module pins the write helpers directly so the contract is clear.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from daydream import db, events, toons


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


@pytest.mark.tier_medium
def test_set_mood_persists_to_db():
    """`set_mood` updates the toons row; the next `get_toon` reflects
    the change."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    rook = toons.get_toon("t-rook")
    assert rook is not None
    assert rook.mood == "content"

    toons.set_mood("t-rook", "weary")

    rook_after = toons.get_toon("t-rook")
    assert rook_after is not None
    assert rook_after.mood == "weary"


@pytest.mark.tier_medium
def test_set_mood_unknown_toon_is_no_op():
    """An unknown toon id matches zero rows; no exception."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    # Should not raise.
    toons.set_mood("t-nonexistent", "weary")
    # And no real toon's mood was disturbed.
    rook = toons.get_toon("t-rook")
    assert rook is not None
    assert rook.mood == "content"


@pytest.mark.tier_medium
def test_set_mood_accepts_arbitrary_string():
    """`mood` has no FK or check-constraint; any string is persisted
    as-is. Sanity-check that the helper doesn't reject unfamiliar
    values, which a future v1 mood-vocabulary expansion would need."""
    from daydream import config
    db.init_live(migrations_dir=config.MIGRATIONS_DIR)
    toons.set_mood("t-rook", "deeply curious about the kettle")
    rook = toons.get_toon("t-rook")
    assert rook is not None
    assert rook.mood == "deeply curious about the kettle"
