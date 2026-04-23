"""Lifecycle dispatcher: bin/game arg parsing + status/down on stopped state.

Real start/stop integration is hand-verified in Inc 9; this stays fast and
side-effect free."""

import os
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_medium

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GAME = PROJECT_ROOT / "bin" / "game"
SMOKE_SH = PROJECT_ROOT / "tests" / "test_game_script.sh"


def test_game_script_is_executable():
    assert GAME.exists(), "bin/game must exist"
    assert os.access(GAME, os.X_OK), "bin/game must be chmod +x"


def test_smoke_shell_passes(tmp_path):
    """Run the bash smoke test script and verify all checks pass."""
    r = subprocess.run(
        ["bash", str(SMOKE_SH)],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert r.returncode == 0, f"smoke script failed:\nstdout={r.stdout}\nstderr={r.stderr}"
    assert "PASS" in r.stdout
