"""Keepsakes for the asleep page (SPEC 2026-09-27 criterion 16): the export
carries each enabled account's own journal, book, portrait and the village
chronicle, plus a pass list of session-token hashes; the sync writes only
what changed and removes what no longer exists (a disabled account)."""

import json

import pytest
from fastapi.testclient import TestClient

from daydream import accounts, db, edge, events, keepsakes, objects
from daydream.server import app
from tests import authhelp

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _two_players():
    with TestClient(app) as c:
        authhelp.login(c, "robin")
        mira = c.post("/api/dreamer/create", json={"name": "Mira", "appearance_seed": "a fox"}).json()
        objects.set_property(mira["id"], "journal", [{"text": "I mended a clock.", "at": "x"}])
        c.cookies.clear()
        authhelp.login(c, "juniper")
        c.post("/api/dreamer/create", json={"name": "Ivo", "appearance_seed": "a heron"})
    db.close_db()
    return mira


def test_export_is_per_account_and_carries_passes(tmp_path):
    _two_players()
    out = tmp_path / "k"
    doc = keepsakes.export(out)
    assert json.loads((out / "keepsakes.json").read_text()) == doc
    by_name = {e["display_name"]: e for e in doc["accounts"].values()}
    assert by_name["robin"]["toons"][0]["journal"] == [{"text": "I mended a clock.", "at": "x"}]
    assert by_name["juniper"]["toons"][0]["name"] == "Ivo"
    # Every live session's hash maps to its own account; tokens never appear.
    live = accounts.live_passes()
    assert set(doc["passes"]) == {r["token_hash"] for r in live}
    assert all(p["account"] in doc["accounts"] for p in doc["passes"].values())


def test_a_disabled_account_drops_out_of_the_export(tmp_path):
    _two_players()
    accounts.init()
    accounts.set_disabled("juniper", True)
    doc = keepsakes.export(tmp_path / "k")
    assert {e["display_name"] for e in doc["accounts"].values()} == {"robin"}
    assert all(p["account"] == accounts.get_account("robin")["id"] for p in doc["passes"].values())


def test_the_sync_writes_only_what_changed_and_deletes_what_went(tmp_path):
    _two_players()
    doc = keepsakes.export(tmp_path / "k")
    desired = edge.desired_keys(doc)
    manifest, write, delete = edge.plan_sync(desired, {})
    assert "passes" in write and "chronicle" in write
    assert sum(key.startswith("keepsakes:") for key in write) == 2
    assert delete == []
    # Nothing changed: nothing to write.
    again, write2, delete2 = edge.plan_sync(desired, manifest)
    assert (write2, delete2) == ([], [])
    # An account gone since the last sync: its keys are deleted.
    stale = dict(manifest)
    stale["keepsakes:a-gone"] = "x"
    stale["portrait:a-gone"] = "y"
    _, _, delete3 = edge.plan_sync(desired, stale)
    assert delete3 == ["keepsakes:a-gone", "portrait:a-gone"]


def test_the_door_preview_rides_to_the_edge(tmp_path):
    """A link shared while the village sleeps unfurls from the edge, so the
    sync carries the door's preview words and its card and icons."""
    import base64

    from daydream import config, instance

    _two_players()
    doc = keepsakes.export(tmp_path / "k")
    door = doc["door"]
    assert door["words"] == instance.preview()
    assert door["words"]["invite_title"] == "An invitation to The Village of Lost Hours"
    assert set(door["assets"]) == {"assets/card-village.jpg", *instance.ICONS.values()}
    assert door["icons"] == instance.ICONS
    for rel, b64 in door["assets"].items():
        assert base64.b64decode(b64) == (config.WEB_DIR / rel).read_bytes()
    desired = edge.desired_keys(doc)
    words = json.loads(desired["door"][0])
    assert words["card"] == "assets/card-village.jpg"
    assert words["assets"] == sorted(door["assets"])
    assert words["icons"] == instance.ICONS
    assert desired["asset:assets/card-village.jpg"] == (door["assets"]["assets/card-village.jpg"],
                                                        True)
    # Only door-image paths become keys (the shape the Worker serves).
    odd = {**doc, "door": {**door, "assets": {**door["assets"], "../x.png": "eA==",
                                              "assets/a.svg": "eA=="}}}
    assert not any(k in edge.desired_keys(odd) for k in ("asset:../x.png", "asset:assets/a.svg"))
    # An older release's export carries no door: the edge forgets the preview.
    manifest, _, _ = edge.plan_sync(desired, {})
    old = {k: v for k, v in doc.items() if k != "door"}
    _, _, delete = edge.plan_sync(edge.desired_keys(old), manifest)
    assert delete == sorted(["door", *(f"asset:{p}" for p in door["assets"])])


def test_a_missing_door_image_is_left_out(tmp_path, monkeypatch):
    from daydream import config

    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "assets" / "icon-32.png").write_bytes(b"\x89PNG")
    monkeypatch.setattr(config, "WEB_DIR", web)
    door = keepsakes._door()
    assert set(door["assets"]) == {"assets/icon-32.png"}



def test_a_planted_symlink_never_becomes_a_friends_portrait(tmp_path):
    """SECURITY WARN 2026-09-27: code running as the service user could point
    a portrait cache file at any file the operator can read; the export (now
    run as the service user anyway) refuses to follow it."""
    from daydream.images import cache, client

    mira = _two_players()
    db.init_live()
    t = objects.get(mira["id"])
    seed = t.properties["appearance_seed"]
    target = client.portrait_target(t.world_id, t.id, seed)
    path = cache.cache_path(t.world_id, "toon", t.id, seed, client.load_workflow_for(target))
    secret = tmp_path / "operator-secret.env"
    secret.write_text("CLOUDFLARE_API_TOKEN=do-not-publish")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.symlink_to(secret)
    db.close_db()
    doc = keepsakes.build()
    assert doc["portraits"] == {}
    assert "do-not-publish" not in json.dumps(doc)
