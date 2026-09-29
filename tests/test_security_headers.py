"""Security headers on every response (SPEC 2026-09-27 criterion 7), and the
client stays CSP-clean: no inline script, inline handler or style attribute,
so the policy can stay strict."""

import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield


def _check(r):
    h = r.headers
    csp = h["content-security-policy"]
    for part in ("default-src 'self'", "script-src 'self'", "style-src 'self'",
                 "frame-ancestors 'none'", "object-src 'none'", "base-uri 'self'"):
        assert part in csp, (part, csp)
    assert "unsafe-inline" not in csp and "unsafe-eval" not in csp
    assert h["x-content-type-options"] == "nosniff"
    assert h["x-frame-options"] == "DENY"
    assert h["referrer-policy"] == "same-origin"
    assert "noindex" in h["x-robots-tag"]


def test_headers_on_pages_assets_api_and_refusals():
    with TestClient(app) as client:
        for r in (client.get("/"), client.get("/assets/main.js"), client.get("/healthz"),
                  client.get("/api/slots"),                     # the gate's 401
                  client.post("/api/login", json={"username": "x", "password": "y"})):
            _check(r)
        authhelp.login(client)
        _check(client.get("/"))
        _check(client.get("/api/slots"))


def test_edge_csp_names_the_public_websocket_origin(monkeypatch):
    monkeypatch.setenv("DAYDREAM_ACCESS", "edge")
    monkeypatch.setenv("DAYDREAM_PUBLIC_ORIGIN", "https://www.example.com")
    with TestClient(app, client=("127.0.0.1", 5000)) as client:
        csp = client.get("/healthz").headers["content-security-policy"]
    assert "connect-src 'self' wss://www.example.com" in csp


def test_the_client_stays_csp_clean():
    offenders = []
    for path in [ROOT / "web" / "index.html", ROOT / "web" / "door.html",
                 *sorted((ROOT / "web" / "assets").glob("*.js"))]:
        text = path.read_text()
        for pat, what in ((r"<script(?![^>]*\bsrc=)[^>]*>", "inline <script>"),
                          (r"\son[a-z]+\s*=\s*[\"']", "inline event handler"),
                          (r"\sstyle\s*=\s*[\"\\\\]", "style attribute"),
                          (r"javascript:", "javascript: URL"),
                          (r"\beval\(|new Function\(", "eval")):
            if re.search(pat, text):
                offenders.append(f"{path.name}: {what}")
    assert not offenders, offenders
