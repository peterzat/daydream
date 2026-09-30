"""The agent guard runs from an installed copy (2026-09-30): `bin/game guard
status` says whether the repo's tools/agent_guard.py is what runs, and
`bin/game guard install` promotes it after its tests pass. Run under a
temporary install location (DAYDREAM_GUARD_HOME), so the real installed
guard is never touched."""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_medium

ROOT = Path(__file__).resolve().parent.parent


def _game(home: Path, *args: str, skip_tests: bool = True) -> str:
    env = {**os.environ, "DAYDREAM_GUARD_HOME": str(home / "guard")}
    if skip_tests:
        env["DAYDREAM_GUARD_SKIP_TESTS"] = "1"
    r = subprocess.run([str(ROOT / "bin/game"), "guard", *args], capture_output=True,
                       text=True, env=env, timeout=120, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr
    return r.stdout


def test_install_promotes_the_repo_guard_and_status_follows(tmp_path):
    live = tmp_path / "guard/agent_guard.py"
    assert "not installed" in _game(tmp_path, "status")
    out = _game(tmp_path, "install")
    assert "guard: installed" in out and str(live) in out
    assert live.read_bytes() == (ROOT / "tools/agent_guard.py").read_bytes()
    assert oct(live.stat().st_mode & 0o777) == "0o644"
    assert "matches tools/agent_guard.py" in _game(tmp_path, "status")
    live.write_text(live.read_text() + "\n# changed\n")
    assert "differs from the installed guard" in _game(tmp_path, "status")


def test_install_runs_the_guards_tests_first(tmp_path):
    out = _game(tmp_path, "install", skip_tests=False)
    assert "passed" in out and "guard: installed" in out
