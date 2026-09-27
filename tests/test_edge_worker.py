"""The edge Worker's own unit tests (edge/test/*.test.js, node's built-in
runner) run as part of tier_short when node is on the box (SPEC 2026-09-27
criterion 14)."""

import shutil
import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

EDGE = Path(__file__).resolve().parent.parent / "edge"


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_edge_worker_unit_tests_pass():
    files = sorted(str(p) for p in (EDGE / "test").glob("*.test.js"))
    assert files
    r = subprocess.run(["node", "--test", *files], cwd=EDGE, capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-2000:]


def test_the_worker_config_keeps_its_guarantees():
    """workers.dev and preview URLs off (nothing skips the zone's rules), the
    routes are the public ones, and no secret is committed."""
    toml = (EDGE / "wrangler.toml").read_text()
    assert "workers_dev = false" in toml and "preview_urls = false" in toml
    assert 'pattern = "www.eidolon.com/daydream*"' in toml
    assert "ACCESS_CLIENT_SECRET" not in toml.split("[vars]")[1].split("[[")[0]
