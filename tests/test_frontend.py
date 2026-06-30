"""Frontend assets: SPA shell, watercolor PNG, JS/CSS served. SPEC criterion 9
plus the SPA-load half of criterion 4."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import db, events
from daydream.server import app

WEB = Path(__file__).resolve().parent.parent / "web"

pytestmark = pytest.mark.tier_medium


@pytest.fixture(autouse=True)
def fresh_state(tmp_path: Path, monkeypatch):
    db.close_db()
    events.reset_subscribers()
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    yield
    db.close_db()
    events.reset_subscribers()


def _login(client: TestClient) -> None:
    r = client.post("/api/login", data={"password": "test-password"})
    assert r.status_code in (200, 303)


def test_authed_root_serves_spa_shell():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert r.status_code == 200
    assert "<title>daydream</title>" in r.text
    assert "/assets/main.js" in r.text
    assert "/assets/style.css" in r.text
    assert "/assets/placeholder-meadow.png" in r.text


def test_root_stamps_asset_urls_with_build_version():
    """The SPA shell stamps main.js/style.css with ?v=<build> so a redeployed
    server serves fresh-URL'd assets (belt-and-suspenders with no-store)."""
    from daydream import version

    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert f"/assets/main.js?v={version.build_sha()}" in r.text
    assert f"/assets/style.css?v={version.build_sha()}" in r.text


def test_placeholder_png_is_committed_and_substantial():
    asset = WEB / "assets" / "placeholder-meadow.png"
    assert asset.exists(), "v0 watercolor placeholder must be committed at web/assets/"
    # Real PNG, not a 1x1 stub: header bytes plus a meaningful payload.
    data = asset.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", "must be a real PNG"
    assert len(data) > 5_000, f"placeholder PNG looks too small: {len(data)} bytes"


def test_placeholder_png_served_at_assets():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/placeholder-meadow.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert len(r.content) > 5_000


def test_main_js_served_with_websocket_logic():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert r.status_code == 200
    assert "WebSocket" in r.text
    assert "state_snapshot" in r.text
    assert "kind" in r.text


def test_main_js_handles_room_image_ready_and_painting_state():
    """SPA hooks for SPEC criterion 5: painting overlay + bg swap."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "room_image_ready" in r.text
    assert "setRoomBackground" in r.text or "image_url" in r.text
    assert "painting-overlay" in r.text


def test_style_css_served_with_cozy_palette():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert r.status_code == 200
    # Sage/cream palette tokens locked in by the WHIMSY anchor.
    assert "--sage" in r.text
    assert "--paper" in r.text


def test_style_css_has_painting_overlay():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert "#painting-overlay" in r.text


def test_index_html_has_painting_overlay_element():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="painting-overlay"' in r.text


def test_index_html_has_dream_overlay_element():
    """C10 (SPEC 2026-06-30): the calm connection-state overlay element."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="dream-overlay"' in r.text


def test_main_js_calm_reconnect_backoff_and_world_changed():
    """C10: a single 'sleeping' overlay + capped-backoff reconnect + the
    world_changed 'dream shifts' beat, with no growing pile of disconnect
    chat lines."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "the dream is sleeping" in r.text
    assert "the dream shifts" in r.text
    assert "world_changed" in r.text
    assert "RECONNECT_MAX" in r.text  # capped backoff
    assert "showDreamOverlay" in r.text and "hideDreamOverlay" in r.text
    # The old per-retry disconnect chat line is gone (calm single state).
    assert "disconnected; reconnecting" not in r.text


def test_main_js_reloads_once_on_build_mismatch():
    """The id-garbage root cause: an open tab kept running stale main.js after a
    redeploy. The SPA records the server build on the first snapshot and reloads
    once when a later snapshot's build (or world MAJOR) changes."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "loadedBuild" in r.text
    assert "triggerUpdateReload" in r.text
    assert "the dream updated" in r.text
    assert "location.reload" in r.text


def test_style_css_has_dream_overlay():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert ".dream-overlay" in r.text


def test_index_html_has_slot_picker_elements():
    """SPA exposes the slot-picker affordance per toon-slot-management
    spec: a 'switch toon' toggle in the footer, a slots panel with the
    slots list ul, and a close button."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="slots-toggle"' in r.text
    assert 'id="slots-panel"' in r.text
    assert 'id="slots-list"' in r.text
    assert 'id="slots-close"' in r.text


def test_main_js_wires_slot_picker_endpoints():
    """SPA's slot picker JS calls the four endpoints
    (/api/slots, create, claim, kick)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "/api/slots" in r.text
    assert "create" in r.text
    assert "claim" in r.text
    assert "kick" in r.text


def test_style_css_has_slot_panel():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert ".slots-panel" in r.text
    assert ".slot-row" in r.text


def test_leave_the_dream_control_is_not_a_get_link():
    """Regression: the 'leave the dream' control must not be a GET link (a
    plain <a href> would navigate / 405). It is a JS button that POSTs to
    /api/session/leave and returns to the character picker (web/assets/main.js)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="leave-dream"' in r.text
    assert ">leave the dream<" in r.text
    # Not a GET-navigation anchor to a leave/logout endpoint.
    assert '<a href="/api/logout"' not in r.text
    assert '<a href="/api/session/leave"' not in r.text


# ---- clickable objects + verb bar (objects + local LLMs, 2026-06-30) ----


def test_index_html_has_verb_bar_and_scene_elements():
    """The SPA shell exposes the verb bar and the scene/inventory containers
    the clickable-object rendering targets."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="verb-bar"' in r.text
    assert 'id="things"' in r.text
    assert 'id="inventory"' in r.text


def test_main_js_renders_clickable_objects_with_data_attributes():
    """Scene objects render as clickable chips carrying object id + kind."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "objectChip" in r.text
    assert "dataset.objectId" in r.text
    assert "dataset.kind" in r.text
    assert "onObjectClick" in r.text


def test_main_js_verb_bar_targeting_and_default_examine():
    """Verb-then-object targeting with object-click-defaults-to-Examine, sent
    as a structured command frame (the click path, no parser)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "stagedVerb" in r.text
    assert "sendCommand" in r.text
    assert '"command"' in r.text or "kind: \"command\"" in r.text
    # A bare object click defaults to Examine.
    assert 'stagedVerb || "examine"' in r.text


def test_main_js_no_generic_go_control_only_data_affordances():
    """No generic "go" button: the per-direction exit buttons are the only nav
    affordance, and the affordance bar renders DATA skills only (so core verbs,
    including go, are never buttons)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    # The affordance bar filters to data skills, excluding the core `go` skill.
    assert 's.kind !== "data"' in r.text
    # Navigation is still per-direction exits (go <direction>), not a generic go.
    assert '"go " + dir' in r.text


def test_main_js_attributes_say_by_name_never_raw_id():
    """C2 (SPEC 2026-06-30): the say renderer attributes by the server-provided
    display name (then the room actor map, then 'someone'), and never renders
    the raw actor id; state-sync events are not dumped as JSON (which would
    leak object ids) into the chat."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "e.payload.name" in r.text  # name-first attribution
    assert "e.actor_id || " not in r.text  # the bare raw-id fallback is gone
    assert "JSON.stringify(e.payload)" not in r.text  # no raw payload dump


def test_main_js_links_object_mentions_in_narration():
    """In-scope object names in narration become clickable spans."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "linkifyEntities" in r.text
    assert "entity-link" in r.text


def test_main_js_linkify_is_single_pass():
    """Playtest fix (forge-rook id-leak): linkifyEntities wraps mentions in ONE
    combined-regex pass, not the per-alias iterative replace that nested spans
    on overlapping aliases ('the forge-keeper' + 'keeper')."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "function linkifyEntities(text, ents)" in r.text
    assert "byAlias" in r.text
    assert "for (const ent of entities)" not in r.text  # the old iterative pass is gone


def test_main_js_debounces_duplicate_commands():
    """Playtest fix (double-examine): a browser double-firing a click must not
    echo the line twice; sendCommand drops an identical command repeated within
    a short window."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "lastCmd" in r.text
    assert "400" in r.text  # the debounce window (ms)


def test_main_js_entity_link_click_not_gated_without_verbs():
    """Playtest fix (clicking an underlined mention did nothing): the staged-verb
    gate applies only when the object's verbs are known, so an entity-link click
    (no verbs list) still acts instead of being silently dropped."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "stagedVerb && objectVerbs && !objectVerbs.includes(stagedVerb)" in r.text


def test_index_html_has_labelled_scene_regions():
    """C3 (SPEC 2026-06-30): the scene distinctly labels and separates WHO YOU
    ARE / HERE WITH YOU / AROUND YOU / YOU'RE CARRYING. The room-objects region
    is labelled "around you" (not "on the ground": an object could be on a table)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    for rid in ("self", "toons", "things", "inventory"):
        assert f'id="{rid}"' in r.text
    assert "scene-region" in r.text
    for label in ("you are", "here with you", "around you", "you're carrying"):
        assert label in r.text
    assert "on the ground" not in r.text  # relabelled


def test_main_js_clears_scene_and_log_on_picker_entry():
    """Playtest fix: entering the character picker clears the prior session's
    scene + chat (stale text used to sit visible under the picker until claim)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "clearSceneAndLog" in r.text
    assert "clearSceneAndLog()" in r.text  # enterPicker calls it before showing


def test_main_js_synthesizes_first_entry_arrival_line():
    """Playtest fix: on first entry (empty event log) the SPA writes a look-style
    arrival line into the chat so the log isn't blank until you type 'look'."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "You are in " in r.text
    assert "You see: " in r.text
    assert "lastArrivalRoomId" in r.text  # guards same-room re-snapshots
    assert "!chat.children.length" in r.text  # only when the log would be empty


def test_main_js_shows_thinking_indicator_for_slow_actions():
    """Playtest fix: talk + free-text show a transient 'thinking' line cleared
    when the response event arrives (no protocol change)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "showPending" in r.text
    assert "clearPending" in r.text
    assert "the dream stirs" in r.text


def test_index_html_has_backpack_control():
    """C4 (SPEC 2026-06-30): a backpack-style control surfaces the inventory."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="backpack-toggle"' in r.text


def test_main_js_renders_self_and_filters_others_with_empty_states():
    """C3: the SPA renders WHO YOU ARE from snap.self, filters it out of the
    co-located toons, and shows per-region empty-state lines."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "snap.self" in r.text
    assert "t.id !== selfId" in r.text  # co-located toons exclude self
    assert "your hands are empty" in r.text  # carrying empty state
    assert "emptyLine" in r.text


def test_main_js_inventory_backpack_and_verb_gating():
    """C4 + C5: the backpack control sends the inventory command, and staging a
    verb gates scene objects to those the verb applies to (so Talk never
    prompts on a non-toon)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert 'sendCommand("inventory")' in r.text
    assert "applyVerbGating" in r.text
    assert "obj-ungated" in r.text
    assert "objectVerbs" in r.text  # click-path applicability guard


def test_style_css_has_scene_region_and_gating_styles():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert ".scene-region" in r.text
    assert ".region-label" in r.text
    assert ".obj-ungated" in r.text


def test_style_css_has_object_and_verb_styles():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert ".obj" in r.text
    assert "#verb-bar" in r.text
    assert ".entity-link" in r.text


# ---- no-cache on /assets/ ----------------------------------------------


def test_assets_served_with_no_store_cache_control():
    """Regression for the hard-refresh-after-web-edit workflow. Browsers
    (Safari especially) aggressively cache /assets/main.js; stamping
    Cache-Control: no-store on every /assets/* response lets Cmd+R pick
    up edits without a hard-reload. See daydream/api/nocache.py for why
    the scope is narrow (only /assets/, not /cache/ or the SPA shell)."""
    with TestClient(app) as client:
        _login(client)
        for path in ("/assets/main.js", "/assets/style.css", "/assets/placeholder-meadow.png"):
            r = client.get(path)
            assert r.status_code == 200, f"{path} returned {r.status_code}"
            assert r.headers.get("cache-control") == "no-store", (
                f"{path} has cache-control={r.headers.get('cache-control')!r}"
            )


def test_non_assets_paths_unaffected_by_nocache_middleware():
    """The middleware must NOT touch /, /login, /api/*, or /cache/. Those
    follow FastAPI's default header behavior (no Cache-Control set by
    us). A bug in the path filter that stamped no-store broadly would
    degrade the SPA shell and, in future, cacheability of content-
    addressed generated images."""
    with TestClient(app) as client:
        r = client.get("/login")
        # The login form is a small HTML blob; no Cache-Control from us.
        assert r.headers.get("cache-control") is None
        _login(client)
        r = client.get("/")
        # The SPA shell should also be un-stamped: it's already cheap to
        # fetch (re-pulls /assets/main.js as a child request), and
        # stamping here would fight the OS-level file cache on the box
        # for no benefit.
        assert r.headers.get("cache-control") is None
