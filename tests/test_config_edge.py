"""Config seams for going live (SPEC 2026-09-27 criterion 1): the public base
and origin, the bind host, and the fail-closed boot guard."""

import pytest
from fastapi.testclient import TestClient

from daydream import config

pytestmark = pytest.mark.tier_short

PROD_OK = {
    "DAYDREAM_ENV": "prod",
    "DAYDREAM_ACCESS": "edge",
    "DAYDREAM_PUBLIC_ORIGIN": "https://www.example.com",
    "DAYDREAM_PUBLIC_BASE": "/daydream/",
    "DAYDREAM_BIND_HOST": "127.0.0.1",
}


@pytest.mark.parametrize("raw,want", [
    ("", "/"), ("/", "/"), ("/daydream/", "/daydream/"), ("/daydream", "/daydream/"),
    ("daydream", "/daydream/"), ("  /daydream/  ", "/daydream/"),
])
def test_public_base_is_normalized(monkeypatch, raw, want):
    monkeypatch.setenv("DAYDREAM_PUBLIC_BASE", raw)
    assert config.public_base() == want


def test_public_origin_drops_trailing_slash(monkeypatch):
    monkeypatch.setenv("DAYDREAM_PUBLIC_ORIGIN", "https://www.example.com/")
    assert config.public_origin() == "https://www.example.com"
    monkeypatch.delenv("DAYDREAM_PUBLIC_ORIGIN")
    assert config.public_origin() == ""


def _set(monkeypatch, env: dict):
    for k in ("DAYDREAM_ENV", "DAYDREAM_ACCESS", "DAYDREAM_PUBLIC_ORIGIN",
              "DAYDREAM_PUBLIC_BASE", "DAYDREAM_BIND_HOST"):
        monkeypatch.delenv(k, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)


def test_dev_defaults_boot(monkeypatch):
    _set(monkeypatch, {})
    assert config.boot_problems() == []


def test_a_complete_prod_config_boots(monkeypatch):
    _set(monkeypatch, PROD_OK)
    assert config.boot_problems() == []


@pytest.mark.parametrize("override,needle", [
    ({"DAYDREAM_ACCESS": "tailscale"}, "edge"),
    ({"DAYDREAM_ACCESS": "public"}, "edge"),
    ({"DAYDREAM_PUBLIC_ORIGIN": ""}, "PUBLIC_ORIGIN"),
    ({"DAYDREAM_PUBLIC_ORIGIN": "http://www.example.com"}, "https"),
    ({"DAYDREAM_PUBLIC_BASE": ""}, "PUBLIC_BASE"),
    ({"DAYDREAM_BIND_HOST": "0.0.0.0"}, "loopback"),
    ({"DAYDREAM_BIND_HOST": "100.64.0.1"}, "loopback"),  # a tailnet address
])
def test_prod_refuses_each_missing_guard(monkeypatch, override, needle):
    env = dict(PROD_OK)
    env.update(override)
    _set(monkeypatch, {k: v for k, v in env.items() if v != ""})
    problems = config.boot_problems()
    assert problems and any(needle in p for p in problems), problems


def test_unknown_access_mode_is_a_boot_error(monkeypatch):
    _set(monkeypatch, {"DAYDREAM_ACCESS": "tailsale"})
    assert any("tailsale" in p for p in config.boot_problems())


def test_edge_mode_needs_a_public_origin_even_outside_prod(monkeypatch):
    _set(monkeypatch, {"DAYDREAM_ACCESS": "edge"})
    assert any("PUBLIC_ORIGIN" in p for p in config.boot_problems())


def test_the_server_refuses_to_boot_a_misconfigured_prod(monkeypatch, tmp_path):
    from daydream.server import app

    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    _set(monkeypatch, {"DAYDREAM_ENV": "prod", "DAYDREAM_ACCESS": "tailscale"})
    with pytest.raises(RuntimeError, match="refuses to boot"):
        with TestClient(app):
            pass
    # Nothing was created: the guard runs before any directory or DB work.
    assert not (tmp_path / "worlds-prod").exists()


def test_no_api_docs_routes(monkeypatch, tmp_path):
    from daydream.server import app

    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    paths = {getattr(r, "path", None) for r in app.routes}
    assert not paths & {"/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"}
