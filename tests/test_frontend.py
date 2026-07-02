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


def test_root_escapes_build_sha_in_asset_url(monkeypatch):
    """Defensive: the build id is URL-quoted before HTML interpolation, so an
    exotic DAYDREAM_BUILD_SHA can't inject markup into the served SPA shell."""
    from daydream import version

    monkeypatch.setenv("DAYDREAM_BUILD_SHA", '"><script>x</script>')
    version.build_sha.cache_clear()
    try:
        with TestClient(app) as client:
            _login(client)
            r = client.get("/")
    finally:
        version.build_sha.cache_clear()
    assert "<script>x</script>" not in r.text  # not injected raw
    assert "/assets/main.js?v=" in r.text       # still stamped (escaped value)


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
    # Backoff is bounded on BOTH sides: a gentle floor and a capped ceiling.
    assert "RECONNECT_MAX" in r.text
    assert "RECONNECT_MIN" in r.text
    # The backoff resets when the socket reopens, so recovery is seamless
    # rather than staying slow after a flap (the "recovers on its own" half).
    assert "reconnectDelay = 0" in r.text
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


def test_main_js_picker_offers_claim_on_taken_slot():
    """Liveness claim (UI half): the picker offers a claim button even for a
    '(taken)' toon, so an abandoned claim (the controller's session is gone) is
    reclaimable -- the server takes over a dead session or refuses with 409."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "(taken)" in r.text
    assert "Offer claim anyway" in r.text  # the taken-branch claim affordance


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


def test_index_html_has_verb_hint_element():
    """C6 (SPEC 2026-07-01): the shell exposes the two-step staging hint slot."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="verb-hint"' in r.text


def test_main_js_two_step_staging_for_two_object_verbs():
    """C6 (SPEC 2026-07-01): two-object verbs (give/use) drive a two-step click:
    stage the verb, click the direct object, then a kind-valid indirect object
    sends BOTH ids. Single-object verbs keep the one-click path."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    # A second staged slot for the direct object, plus the verb-spec map that
    # carries needs_iobj / valid_iobj_kinds from the snapshot's verb_bar.
    assert "stagedDobjId" in r.text
    assert "verbSpecs" in r.text
    assert "needs_iobj" in r.text
    assert "valid_iobj_kinds" in r.text
    # Step 2 sends both ids through sendCommand (dobj, then iobj).
    assert "sendCommand(stagedVerb, stagedDobjId" in r.text
    # The command frame carries iobj_id (the server already accepts it).
    assert "iobj_id" in r.text
    # Step 2 gates candidate targets by kind (give -> a toon; use -> a thing).
    assert "valid_iobj_kinds).includes" in r.text or "validIobjKinds.includes" in r.text


def test_main_js_plant_prompts_for_vision_and_sends_command():
    """SPEC 2026-07-02 criterion 5: staging Plant and clicking the seed prompts
    for the vision (mirroring Talk's prompt) and sends one structured command
    frame with the vision as args; the slow LLM-backed grow shows the calm
    pending beat. No plant-specific parser or LLM code client-side."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert 'verb === "plant"' in r.text
    assert "where does the new way lead?" in r.text
    assert 'sendCommand("plant", objectId, vision)' in r.text
    # The vision prompt path shows the pending beat like talk does.
    plant_branch = r.text.split('verb === "plant"')[1].split("} else {")[0]
    assert "showPending()" in plant_branch


def test_main_js_room_change_veils_stale_art():
    """Playtest 2026-07-02: entering an unrendered room briefly showed the
    PREVIOUS room's painting. On a room change the plate veils immediately
    (bg-loading) and reveals only when the next bitmap has decoded."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "bgShownFor" in r.text
    assert "bg-loading" in r.text
    assert 'addEventListener("load"' in r.text


def test_main_js_repeated_narrate_glows_not_duplicates():
    """A verbatim repeat of the last prose line (an affordance clicked twice)
    glows the existing line instead of stacking a duplicate — the detail-inset
    de-dup's sibling for plain narrate."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "prior.dataset.text === text" in r.text
    assert "glowElement(prior)" in r.text


def test_style_css_has_bg_veil_and_narrate_glow():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert "#room-bg.bg-loading" in r.text
    assert ".evt-narrate.detail-glow" in r.text


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
    """C1/C3: the Reading Room marginalia column distinctly labels and separates
    you / here with you / around you / you carry, each a clickable-object region.
    The room-objects region is "around you" (an object could be on a table, not
    "on the ground"). Retheme (SPEC 2026-07-01): the boxed scene-regions became
    the marginalia mgroups."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    for rid in ("self", "toons", "things", "inventory"):
        assert f'id="{rid}"' in r.text
    # Marginalia groups (the storybook right-margin column).
    assert "mgroup" in r.text
    assert "mlabel" in r.text
    for label in (">you<", ">here with you<", ">around you<", ">you carry<"):
        assert label in r.text
    assert "on the ground" not in r.text  # relabelled


def test_index_html_no_design_comptag():
    """Playtest fix: the internal design-direction name ("The Reading Room") is
    not shown to players as floating corner chrome; it was confusing in-game."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert "comptag" not in r.text
    assert "The Reading Room" not in r.text


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
    """C3 (SPEC 2026-07-01): the backpack control opens the keepsakes foldout (a
    two-page spread over the live inventory) with a close control."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/")
    assert 'id="backpack-toggle"' in r.text
    assert 'id="backpack-panel"' in r.text
    assert 'id="backpack-close"' in r.text
    assert 'id="keepsakes"' in r.text


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
    """C3 + C1: the backpack control opens the keepsakes foldout from the cached
    snap.inventory (no longer prints `inventory` to chat), and staging a verb
    gates scene objects to those the verb applies to (so Talk never prompts on a
    non-toon)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    # The backpack opens the foldout and renders inventory as specimen cards.
    assert "openBackpack" in r.text
    assert "renderKeepsakes" in r.text
    assert "lastInventory" in r.text
    # The old "print inventory to chat" behavior is gone.
    assert 'sendCommand("inventory")' not in r.text
    # Verb gating still applies.
    assert "applyVerbGating" in r.text
    assert "obj-ungated" in r.text
    assert "objectVerbs" in r.text  # click-path applicability guard


def test_style_css_has_marginalia_and_gating_styles():
    """Retheme (SPEC 2026-07-01): the marginalia column styles (.margin/.mgroup/
    .mlabel) and the staged-verb gating dim (.obj-ungated) are present."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert ".margin" in r.text
    assert ".mgroup" in r.text
    assert ".mlabel" in r.text
    assert ".obj-ungated" in r.text


def test_style_css_has_object_and_verb_styles():
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert ".obj" in r.text
    assert "#verb-bar" in r.text
    assert ".entity-link" in r.text


def test_style_css_has_responsive_single_column():
    """C4: a phone-width media query collapses the two-column body to a single
    readable column (marginalia below the prose)."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert "@media (max-width: 640px)" in r.text
    # the two-column body grid collapses to one column at narrow widths
    assert "grid-template-columns: 1fr" in r.text


def test_style_css_desktop_shell_keeps_nav_in_view():
    """Playtest fix (nav below the fold): a desktop app-shell fits the leaf to
    the viewport so the verb ribbon + compass stay visible without scrolling,
    the reading column scrolling inside. Plus the repeat-examine glow style."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert "@media (min-width: 641px)" in r.text
    assert ".detail-glow" in r.text


def test_main_js_repeat_examine_glows_not_duplicates():
    """Playtest fix: examining the same thing again with the same result should
    resurface its detail card with a glow, not stack a duplicate line."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/main.js")
    assert "glowElement" in r.text
    assert "detail-glow" in r.text
    assert "data-object-id" in r.text  # dedup keys on the object id...
    assert "dataset.text" in r.text     # ...and the rendered text


def test_style_css_has_keepsakes_spread():
    """C3: the keepsakes backpack foldout styles (the two-page book spread, the
    specimen cards, the empty collection slots) are present."""
    with TestClient(app) as client:
        _login(client)
        r = client.get("/assets/style.css")
    assert ".backpack-overlay" in r.text
    assert ".specimen" in r.text
    assert ".slot-note" in r.text
    assert ".grid2" in r.text


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
