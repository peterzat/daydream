"""`bin/game edge` (daydream/edge.py): the flag the Worker reads, written
through the Cloudflare API with the operator's token (SPEC 2026-09-27
criterion 15). The API is mocked; no token exists in the test HOME."""

import json

import pytest

from daydream import edge

pytestmark = pytest.mark.tier_short


def test_unconfigured_by_default(tmp_path, monkeypatch):
    monkeypatch.setattr(edge, "CREDENTIALS", tmp_path / "none.env")
    monkeypatch.delenv("CLOUDFLARE_API_TOKEN", raising=False)
    assert not edge.configured()


def test_kv_id_is_read_from_wrangler_toml(tmp_path, monkeypatch):
    (tmp_path / "wrangler.toml").write_text(
        'name = "x"\n[[kv_namespaces]]\nbinding = "STATE"\nid = "abc123"\n[assets]\n')
    monkeypatch.setattr(edge, "EDGE", tmp_path)
    assert edge.kv_namespace_id() == "abc123"
    (tmp_path / "wrangler.toml").write_text('[[kv_namespaces]]\nid = "REPLACE_WITH_KV_NAMESPACE_ID"\n')
    assert edge.kv_namespace_id() is None


def test_the_public_status_url_comes_from_wrangler_toml(tmp_path, monkeypatch):
    """codereview WARN 2026-09-28b: the URL was hardcoded to this instance, so
    a fork's `bin/game edge status` probed someone else's village."""
    import re

    assert re.fullmatch(r"https://[a-z0-9.-]+/([a-z0-9-]+/)?edge/status", edge.public_status_url())
    monkeypatch.setattr(edge, "EDGE", tmp_path)
    (tmp_path / "wrangler.toml").write_text(
        '[vars]\nORIGIN = "https://origin.example.org"\nPUBLIC_HOST = "play.example.org"\n'
        'BASE = "/village/"\n')
    assert edge.public_status_url() == "https://play.example.org/village/edge/status"
    (tmp_path / "wrangler.toml").write_text('[vars]\nPUBLIC_HOST = "example.org"\nBASE = "/"\n')
    assert edge.public_status_url() == "https://example.org/edge/status"
    (tmp_path / "wrangler.toml").write_text('[vars]\nBASE = "/village/"\n')
    with pytest.raises(edge.EdgeError):
        edge.public_status_url()


def test_set_and_describe_state(tmp_path, monkeypatch):
    creds = tmp_path / "cloudflare.env"
    creds.write_text("CLOUDFLARE_API_TOKEN=t0k\nCLOUDFLARE_ACCOUNT_ID=acct\n")
    monkeypatch.setattr(edge, "CREDENTIALS", creds)
    monkeypatch.setattr(edge, "kv_namespace_id", lambda: "ns1")
    store = {}

    def fake_api(method, path, body=None, content_type="application/json"):
        assert path.startswith("/accounts/acct/storage/kv/namespaces/ns1/values/")
        key = path.rsplit("/", 1)[1]
        if method == "PUT":
            store[key] = body.decode()
            return b"{}"
        if method == "GET":
            if key not in store:
                raise edge.EdgeError("Cloudflare API GET x: 404 not found")
            return store[key].encode()
        raise AssertionError(method)

    monkeypatch.setattr(edge, "_api", fake_api)
    assert edge.configured()
    assert edge.get_state()["state"] == "awake"  # nothing written yet
    s = edge.set_state("asleep", "back Sunday")
    assert json.loads(store["state"]) == s and s["note"] == "back Sunday" and s["since"]
    assert edge.describe_state().startswith("asleep (back Sunday) since ")
    with pytest.raises(edge.EdgeError):
        edge.set_state("dozing")


def test_public_status_names_its_user_agent(monkeypatch):
    """Cloudflare's Browser Integrity Check answers urllib's default
    User-Agent with a 403 (error 1010), which read as "no answer"."""
    seen = {}

    class Resp:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def read(self):
            return b'{"state": "asleep"}'

    def fake_urlopen(req, timeout):
        seen["ua"] = req.get_header("User-agent")
        return Resp()

    monkeypatch.setattr(edge.urllib.request, "urlopen", fake_urlopen)
    assert edge.public_status() == {"state": "asleep"}
    assert seen["ua"] and not seen["ua"].startswith("Python-urllib")


def test_node_is_found_under_nvm_when_path_lacks_it(tmp_path, monkeypatch):
    """Codereview WARN 2026-09-28: the weekly offsite timer's PATH has no
    ~/.nvm, so npx went unfound. The newest nvm install goes first on PATH."""
    for v in ("v9.1.0", "v24.14.1", "v18.2.0"):
        (tmp_path / ".nvm" / "versions" / "node" / v / "bin").mkdir(parents=True)
        (tmp_path / ".nvm" / "versions" / "node" / v / "bin" / "node").touch()
    monkeypatch.setattr(edge.Path, "home", lambda: tmp_path)
    monkeypatch.setattr(edge.shutil, "which", lambda name: None)
    monkeypatch.setenv("PATH", "/usr/bin:/bin")
    first = edge._node_env()["PATH"].split(":")[0]
    assert first == str(tmp_path / ".nvm" / "versions" / "node" / "v24.14.1" / "bin")


def test_the_uptime_watch_is_described_plainly():
    from daydream import edge

    assert edge.describe_uptime({"down_since": None, "outages": []}) == \
        "up; no unplanned outage recorded"
    assert edge.describe_uptime({"down_since": "2026-09-28T10:05:00Z", "outages": []}).startswith(
        "DOWN since 2026-09-28T10:05:00Z")
    one = {"down_since": None, "outages": [{"from": "a", "to": "b"}]}
    assert edge.describe_uptime(one) == "up; last unplanned outage a to b (1 recorded)"
