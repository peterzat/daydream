"""The web client is base-relative (SPEC 2026-09-27 criterion 6): the same
build serves at "/" (dev) and under "/daydream/" behind the edge Worker, which
strips the prefix before proxying. A root-absolute path anywhere in the client
would escape the base, so this gate fails on one."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
WEB_FILES = [ROOT / "web" / "index.html", *sorted((ROOT / "web" / "assets").glob("*.js")),
             *sorted((ROOT / "web" / "assets").glob("*.css"))]
# A quote, backtick or url( followed by a root-absolute app path.
ROOT_ABSOLUTE = re.compile(r"""["'`(]\s*/(api|assets|cache|ws|login|status|invite)\b""")


def test_the_gate_sees_the_client():
    names = {p.name for p in WEB_FILES}
    assert {"index.html", "main.js", "style.css"} <= names


def test_no_root_absolute_paths_in_the_web_client():
    offenders = []
    for path in WEB_FILES:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            if ROOT_ABSOLUTE.search(line):
                offenders.append(f"{path.relative_to(ROOT)}:{n}: {line.strip()}")
    assert not offenders, "root-absolute paths escape the public base:\n" + "\n".join(offenders)


def test_every_image_sink_rebases_through_asset_url():
    """Server-emitted image URLs are origin paths, some persisted in old
    events; every place the SPA assigns one must rebase it onto the base."""
    js = (ROOT / "web" / "assets" / "main.js").read_text()
    assert "function assetUrl(" in js and "document.baseURI" in js
    for line in js.splitlines():
        if re.search(r"\.src\s*=", line):
            assert "assetUrl(" in line or "target" in line or "PLACEHOLDER_BG" in line, line
    assert "new URL(\"ws\", document.baseURI)" in js


def _login(client):
    r = client.post("/api/login", data={"password": "test-password"}, follow_redirects=False)
    assert r.status_code in (200, 303)


@pytest.mark.parametrize("base", ["/", "/daydream/"])
def test_the_shell_carries_the_configured_base(monkeypatch, tmp_path, base):
    from daydream.server import app

    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DAYDREAM_PUBLIC_BASE", base)
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert r.status_code == 200
    assert f'<base href="{base}">' in r.text
    assert r.text.count("<base ") == 1


def test_redirects_stay_inside_the_base(monkeypatch, tmp_path):
    from daydream.server import app

    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("DAYDREAM_PUBLIC_BASE", "/daydream/")
    with TestClient(app) as client:
        r = client.get("/", follow_redirects=False)
    assert r.status_code in (302, 303)
    assert r.headers["location"].startswith("/daydream/")
