"""FastAPI app, lifespan (DB init), middleware, route mounting.

Static SPA serving: when web/dist/ exists (built by Inc 7's Vite step), the
root path serves it; before that, a minimal placeholder HTML lets a browser
verify the auth flow end to end."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from daydream import config, db, drift
from daydream.api import auth, slots, world, ws
from daydream.api.access import AccessMiddleware
from daydream.api.csrf import CsrfOriginMiddleware
from daydream.api.nocache import NoCacheAssetsMiddleware
from daydream.images import cache as image_cache

# Image cache root must exist before the StaticFiles mount below so /cache/
# can serve generated room backgrounds. Idempotent; safe at module import.
image_cache.ensure_cache_root()


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    db.init_live()
    drift.start_drift_loop()
    try:
        yield
    finally:
        # No-argument stop targets the module-tracked live task. A world
        # hot-swap replaces that task mid-run, so stopping via a startup-time
        # handle would miss the post-swap task and leak it to loop teardown.
        await drift.stop_drift_loop()
        db.close_db()


app = FastAPI(lifespan=lifespan, title="daydream")
app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret(),
    session_cookie="daydream_session",
    https_only=False,  # friend-scope; box is on a private LAN/Tailscale only
)
# NoCacheAssetsMiddleware stamps Cache-Control: no-store on /assets/*
# responses so browser hard-refresh stops being required after web/
# edits. See daydream/api/nocache.py for why the scope is narrow.
# Order is not load-bearing (it only rewrites response headers), but
# placing it before AccessMiddleware keeps the Access rejection path
# clean of unnecessary header rewrites on 403s.
app.add_middleware(NoCacheAssetsMiddleware)
# CsrfOriginMiddleware rejects cross-origin state-changing POSTs (the
# confused-deputy vector against the friend-scope slot/session endpoints,
# which in tailscale mode have no cookie check). Added before AccessMiddleware
# so the IP gate stays outermost; this layer only acts on unsafe methods whose
# Origin/Referer mismatches Host (non-browser clients with no Origin pass).
app.add_middleware(CsrfOriginMiddleware)
# AccessMiddleware added LAST so it sits at the outer edge of the stack
# (middleware added later runs earlier per request). When DAYDREAM_ACCESS
# is 'tailscale' (default), non-tailnet clients see 403 / WS close 1008
# before any session or auth machinery runs.
app.add_middleware(AccessMiddleware)
app.include_router(auth.router)
app.include_router(slots.router)
app.include_router(world.router)
app.include_router(ws.router)


@app.get("/status/drift")
async def status_drift():
    """Internal observability endpoint for `bin/game status`. Returns
    a one-line summary of drift outcome counters when any are non-zero;
    empty body (200 OK with empty payload) when drift hasn't ticked yet.

    Plain-text rather than JSON so `bin/game cmd_status` can interpolate
    the response directly without a JSON parser dependency. Loopback /
    tailnet-only via AccessMiddleware (no session auth needed)."""
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


@app.get("/login")
async def login_form():
    # Tailscale-mode clients never need to see this form — tailnet
    # membership is the auth boundary. Redirect a stale bookmark (or
    # an agent-driven GET) home rather than rendering a password
    # prompt that wouldn't meaningfully gate anything.
    if config.access_mode() == "tailscale":
        return RedirectResponse(url="/", status_code=302)
    return HTMLResponse(_LOGIN_HTML)


@app.get("/")
async def root(request: Request):
    if not auth.is_authed(request.session):
        return RedirectResponse(url="/login", status_code=302)
    index = config.WEB_DIR / "index.html"
    if index.exists():
        return HTMLResponse(index.read_text())
    return HTMLResponse(_PRE_FRONTEND_HTML)


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
    return FileResponse(p, media_type="image/png")


_LOGIN_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>daydream</title>
<style>
  body { font-family: Georgia, serif; max-width: 480px; margin: 6em auto;
         text-align: center; color: #3a4a44; background: #f6f3ec; }
  h1 { font-weight: normal; color: #5a7a6a; letter-spacing: 0.05em; }
  input { font-size: 1.1em; padding: 0.5em 0.7em; border: 1px solid #b9b3a5;
          border-radius: 4px; background: #fbf9f3; color: #3a4a44; }
  button { font-size: 1em; padding: 0.55em 1.1em; margin-left: 0.4em;
           border: 1px solid #5a7a6a; background: #5a7a6a; color: #fbf9f3;
           border-radius: 4px; cursor: pointer; }
  button:hover { background: #4a6a5a; }
</style>
</head>
<body>
<h1>daydream</h1>
<form method="post" action="/api/login">
<input type="password" name="password" autofocus autocomplete="current-password">
<button type="submit">enter</button>
</form>
</body>
</html>
"""

_PRE_FRONTEND_HTML = """<!doctype html>
<html><body style="font-family: Georgia, serif; max-width: 600px; margin: 5em auto; color: #3a4a44; background: #f6f3ec;">
<h1 style="color: #5a7a6a; font-weight: normal;">daydream</h1>
<p>You are in the daydream. The frontend lands in Inc 7.</p>
<form action="/api/logout" method="post" style="margin:0;">
  <button type="submit" style="background:none;border:none;padding:0;font:inherit;cursor:pointer;color:#5a7a6a;">leave</button>
</form>
</body></html>
"""
