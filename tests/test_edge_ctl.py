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
