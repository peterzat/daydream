"""Build SHA capture + WORLD_VERSION boot gate (daydream/version.py)."""

import logging
import sqlite3

import pytest

from daydream import config, version

pytestmark = pytest.mark.tier_short


def _worlds_conn(stamp, *, with_column=True):
    """An in-memory DB with a minimal `worlds` table, optionally carrying the
    world_version column (absent => a pre-012 / non-daydream DB)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    if with_column:
        conn.execute("CREATE TABLE worlds (id TEXT PRIMARY KEY, world_version TEXT)")
        conn.execute(
            "INSERT INTO worlds (id, world_version) VALUES ('w-bunny', ?)", (stamp,)
        )
    else:
        conn.execute("CREATE TABLE worlds (id TEXT PRIMARY KEY)")
        conn.execute("INSERT INTO worlds (id) VALUES ('w-bunny')")
    return conn


def test_parse_version():
    assert version.parse_version("1.0") == (1, 0)
    assert version.parse_version("2.7") == (2, 7)
    assert version.parse_version("3") == (3, 0)
    assert version.parse_version(None) == (0, 0)
    assert version.parse_version("") == (0, 0)
    assert version.parse_version("garbage") == (0, 0)
    assert version.parse_version("1.x") == (1, 0)  # minor unparseable -> 0


def test_build_sha_env_override(monkeypatch):
    monkeypatch.setenv("DAYDREAM_BUILD_SHA", "deadbeef99")
    version.build_sha.cache_clear()
    try:
        assert version.build_sha() == "deadbeef99"
    finally:
        version.build_sha.cache_clear()


def test_build_sha_degrades_to_unknown_off_git(monkeypatch, tmp_path):
    monkeypatch.delenv("DAYDREAM_BUILD_SHA", raising=False)
    monkeypatch.setattr(config, "PROJECT_ROOT", tmp_path)  # tmp_path is not a git repo
    version.build_sha.cache_clear()
    try:
        assert version.build_sha() == "unknown"
    finally:
        version.build_sha.cache_clear()


def test_check_world_compat_matching_is_silent():
    conn = _worlds_conn(version.WORLD_VERSION)
    try:
        version.check_world_compat(conn)  # exact match: no raise, no gate
    finally:
        conn.close()


def test_check_world_compat_major_mismatch_blocks():
    code_major = version.parse_version(version.WORLD_VERSION)[0]
    conn = _worlds_conn(f"{code_major + 1}.0")  # one major ahead: incompatible
    try:
        with pytest.raises(SystemExit, match="world reset"):
            version.check_world_compat(conn)
    finally:
        conn.close()


def test_check_world_compat_minor_mismatch_warns(caplog):
    code_major, code_minor = version.parse_version(version.WORLD_VERSION)
    conn = _worlds_conn(f"{code_major}.{code_minor + 1}")  # same major, newer minor
    try:
        with caplog.at_level(logging.WARNING):
            version.check_world_compat(conn)  # warns, never blocks
        assert "content version" in caplog.text
    finally:
        conn.close()


def test_check_world_compat_null_warns(caplog):
    conn = _worlds_conn(None)  # legacy world, no stamp
    try:
        with caplog.at_level(logging.WARNING):
            version.check_world_compat(conn)
        assert "no world_version" in caplog.text
    finally:
        conn.close()


def test_check_world_compat_missing_column_fails_open():
    conn = _worlds_conn(None, with_column=False)  # pre-012 / non-daydream DB
    try:
        version.check_world_compat(conn)  # must not raise: fail open on the unknown
    finally:
        conn.close()
