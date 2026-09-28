"""FastAPI app, lifespan (DB init), middleware, route mounting.

Static SPA serving: when web/dist/ exists (built by Inc 7's Vite step), the
root path serves it; before that, a minimal placeholder HTML lets a browser
verify the auth flow end to end."""

import re
from contextlib import asynccontextmanager
from html import escape as html_escape
from urllib.parse import quote

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import (
    FileResponse,
    HTMLResponse,
    PlainTextResponse,
)
from fastapi.staticfiles import StaticFiles

from daydream import accounts, announce, config, db, drift, version, village
from daydream.api import auth, slots, world, ws
from daydream.api import rooms as rooms_api
from daydream.api.access import AccessMiddleware
from daydream.api.csrf import CsrfOriginMiddleware
from daydream.api.gate import GateMiddleware
from daydream.api.headers import SecurityHeadersMiddleware
from daydream.api.nocache import NoCacheAssetsMiddleware
from daydream.images import cache as image_cache

# Image cache root must exist before the StaticFiles mount below so /cache/
# can serve generated room backgrounds. Idempotent; safe at module import.
image_cache.ensure_cache_root()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Fail closed before touching anything: prod refuses to serve unless it
    # runs in edge mode with a public origin, a public base and a loopback
    # bind (SPEC 2026-09-27 criterion 1; docs/GOING-LIVE.md section 2).
    problems = config.boot_problems()
    if problems:
        raise RuntimeError("daydream refuses to boot: " + "; ".join(problems))
    config.ensure_dirs()
    accounts.init()
    db.init_live()
    # Refuse to boot on an incompatible live world (a MAJOR world_version gap);
    # warn on a minor/legacy gap. This is the server-only boot path: the gate
    # lives here, NOT in db.init_live, which admin tools (incl. `world reset`)
    # and the test suite also call. Freeze the build id for /status/build.
    version.check_world_compat(db.get_conn())
    version.build_sha()
    drift.start_drift_loop()
    # The living day (SPEC 2026-09-26): process wall-clock phase boundaries
    # (catching up any missed while the server was down) and let the
    # director pick small events, even with no one connected.
    village.start_loop()
    # Shell-to-village announcements (daydream/announce.py): no web endpoint.
    announce.start()
    try:
        yield
    finally:
        await announce.stop()
        # No-argument stop targets the module-tracked live task. A world
        # hot-swap replaces that task mid-run, so stopping via a startup-time
        # handle would miss the post-swap task and leak it to loop teardown.
        await village.stop_loop()
        await drift.stop_drift_loop()
        db.close_db()
        accounts.close()


# No interactive API docs anywhere: nothing uses them, and in prod they would
# be a pre-login map of every route.
app = FastAPI(lifespan=lifespan, title="daydream", docs_url=None, redoc_url=None,
              openapi_url=None)
# NoCacheAssetsMiddleware stamps Cache-Control: no-store on /assets/*
# responses so browser hard-refresh stops being required after web/
# edits. See daydream/api/nocache.py for why the scope is narrow.
# Order is not load-bearing (it only rewrites response headers), but
# placing it before AccessMiddleware keeps the Access rejection path
# clean of unnecessary header rewrites on 403s.
app.add_middleware(NoCacheAssetsMiddleware)
# CsrfOriginMiddleware (runs before the gate) rejects cross-origin
# state-changing requests before any session lookup; it only acts on unsafe
# methods whose Origin/Referer mismatches (non-browser clients with no Origin
# pass). Runtime order: Access (network) -> CSRF -> Gate (account) -> app.
# GateMiddleware: every request needs an account session except the public
# allowlist (the front door, static assets, login, invite redemption, health),
# so no handler ever sees an unauthenticated request it did not opt into.
app.add_middleware(GateMiddleware)
app.add_middleware(CsrfOriginMiddleware)
# AccessMiddleware added LAST so it sits at the outer edge of the stack
# (middleware added later runs earlier per request). When DAYDREAM_ACCESS
# is 'tailscale' (default), non-tailnet clients see 403 / WS close 1008
# before any session or auth machinery runs.
app.add_middleware(AccessMiddleware)
# Security headers (CSP, nosniff, no framing, noindex) on every HTTP response,
# the network rule's and the gate's refusals included: added after everything
# else, so it is the outermost layer (daydream/api/headers.py).
app.add_middleware(SecurityHeadersMiddleware)
app.include_router(auth.router)
app.include_router(slots.router)
app.include_router(world.router)
app.include_router(rooms_api.router)
app.include_router(ws.router)


def _require_admin(request: Request) -> None:
    """The /status endpoints are operator observability: admin accounts only
    (SPEC 2026-09-27 criterion 4). `bin/game status` reads them with the
    CLI's own admin session."""
    who = auth.principal(request)
    if who is None or not who.is_admin:
        raise HTTPException(status_code=403, detail="status is for admins")


@app.get("/status/drift")
async def status_drift(request: Request):
    """Internal observability endpoint for `bin/game status`. Returns
    a one-line summary of drift outcome counters when any are non-zero;
    empty body (200 OK with empty payload) when drift hasn't ticked yet.

    Plain-text rather than JSON so `bin/game cmd_status` can interpolate
    the response directly without a JSON parser dependency. Loopback /
    admin-only (an admin account session, SPEC 2026-09-27)."""
    _require_admin(request)
    from fastapi.responses import PlainTextResponse

    from daydream import drift

    counts = drift.tick_counts()
    if not any(counts.values()):
        return PlainTextResponse("", status_code=200)
    return PlainTextResponse(
        f"drift: {counts['llm_emit']} emits"
        f" / {counts['canned_fallback']} fallback"
        f" / {counts['noop']} noop (since boot)\n"
    )


@app.get("/status/arbiter")
async def status_arbiter(request: Request):
    """GPU-gate observability for `bin/game status` and the swarm harness.
    Plain-text one-liner (no JSON parser dependency in bin/game), admin
    accounts only. Always non-empty: an idle gate is
    still worth a line, unlike drift's silent-until-first-tick counters."""
    _require_admin(request)
    from fastapi.responses import PlainTextResponse

    from daydream import events
    from daydream.gpu import arbiter

    s = arbiter.stats()
    return PlainTextResponse(
        f"arbiter: llm {s['active_llm']}/{s['llm_concurrency']} active"
        f" +{s['waiting_llm']} waiting"
        f" / image {'busy' if s['active_exclusive'] else 'idle'}"
        f" +{s['waiting_exclusive']} waiting"
        f" / bg {s['active_background']} active +{s['waiting_background']} waiting"
        f" / max wait llm {s['max_wait_ms_llm']}ms"
        f" image {s['max_wait_ms_exclusive']}ms"
        f" / events dropped {events.dropped_event_total()}\n"
    )


@app.get("/status/who")
async def status_who(request: Request):
    """Who is in the village right now (for `bin/game prod status`): the
    toons being played, their ids (moderation names a toon by id; names are
    not unique) and whether their socket is live. Admins only."""
    _require_admin(request)
    from daydream import toons

    lines = []
    for t in toons.playing():
        live = ws.is_session_live(t.controller_session)
        lines.append(f"{t.name} [{t.id}]{'' if live else ' (away)'}")
    return PlainTextResponse("playing: " + (", ".join(lines) if lines else "no one") + "\n")


@app.get("/status/build")
async def status_build(request: Request):
    """Build + version observability for `bin/game status`. Plain-text, one
    key:value per line (no JSON dependency in bin/game), admin accounts
    only. `build` is the commit the running process started
    from; `world_version` + `migration` are this code's expectations, so
    `bin/game status` can compare the live server against HEAD."""
    _require_admin(request)
    from fastapi.responses import PlainTextResponse

    from daydream import db, version

    return PlainTextResponse(
        f"app: {version.APP_VERSION}\n"
        f"build: {version.build_sha()}\n"
        f"world_version: {version.WORLD_VERSION}\n"
        f"migration: {db.max_known_migration()}\n"
    )


def _page(name: str) -> HTMLResponse:
    """Serve a shell page from web/ with the public base injected and the
    asset URLs stamped with the build (belt-and-suspenders with the no-store
    middleware; the client's build-mismatch reload is the primary stale-tab
    fix). StaticFiles ignores the query string, so the files still resolve.
    The build id is URL-quoted so it is safe in the query string and the
    attribute even if a future change sourced it from untrusted input."""
    page = config.WEB_DIR / name
    if not page.exists():
        # web/ ships in the repo; a missing page means a broken deploy.
        return PlainTextResponse(f"daydream: web/{name} is missing from this deploy",
                                 status_code=503)
    sha = quote(version.build_sha(), safe="")
    base = html_escape(config.public_base(), quote=True)
    html = page.read_text().replace('<base href="/">', f'<base href="{base}">', 1)
    html = re.sub(r'"(assets/[a-z0-9_-]+\.(?:js|css))"', rf'"\1?v={sha}"', html)
    return HTMLResponse(html, headers={"Cache-Control": "no-store"})


@app.get("/healthz")
async def healthz():
    """Liveness for the edge Worker and `bin/game prod status`. Public, so it
    says nothing else (no build id, no counts)."""
    return {"ok": True}


@app.get("/login")
async def login_page():
    return _page("door.html")


@app.get("/invite/{slug}")
async def invite_page(slug: str):
    # The slug is only ever checked by the peek/redeem POSTs (throttled);
    # this GET serves the same static card for any path.
    return _page("door.html")


@app.get("/")
async def root(request: Request):
    """The game for a signed-in person, the front door for anyone else. Each
    game load re-issues the session cookie so its 30-day life slides with
    use."""
    who = auth.principal(request)
    if who is None:
        return _page("door.html")
    resp = _page("index.html")
    token = auth.token_from_cookie_header(request.headers.get("cookie"))
    if token:
        auth.set_session_cookie(resp, token)
    return resp


# Serve frontend static assets if a build exists (Inc 7+).
if config.WEB_DIR.exists():
    app.mount(
        "/assets",
        StaticFiles(directory=str(config.WEB_DIR / "assets")),
        name="assets",
    )

# Serve generated assets from the image cache. A route handler (not a
# StaticFiles mount) resolves the cache root per request, so tests that
# override DAYDREAM_DATA_DIR pick up the right path. Path components are
# validated to block traversal even though friend-scope security is the
# real gate. The four-segment shape mirrors the cache layout
# {world}/{target_kind}/{target_id}/{hash}.png.
@app.get("/cache/{world}/{target_kind}/{target_id}/{filename}")
async def serve_cached_image(
    world: str, target_kind: str, target_id: str, filename: str
):
    for seg in (world, target_kind, target_id):
        if "/" in seg or ".." in seg:
            raise HTTPException(status_code=404)
    if "/" in filename or ".." in filename or not filename.endswith(".png"):
        raise HTTPException(status_code=404)
    p = image_cache.cache_dir() / world / target_kind / target_id / filename
    if not p.is_file():
        raise HTTPException(status_code=404)
    # Session-gated and content-addressed: the browser may keep it, but no
    # shared cache (Cloudflare included) ever should (criterion 7).
    return FileResponse(p, media_type="image/png",
                        headers={"Cache-Control": "private, max-age=86400"})
