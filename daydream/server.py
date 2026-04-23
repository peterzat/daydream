"""FastAPI app, lifespan (DB init), middleware, route mounting.

Static SPA serving: when web/dist/ exists (built by Inc 7's Vite step), the
root path serves it; before that, a minimal placeholder HTML lets a browser
verify the auth flow end to end."""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from daydream import config, db
from daydream.api import auth, ws


@asynccontextmanager
async def lifespan(app: FastAPI):
    config.ensure_dirs()
    db.init_live()
    yield
    db.close_db()


app = FastAPI(lifespan=lifespan, title="daydream")
app.add_middleware(
    SessionMiddleware,
    secret_key=config.session_secret(),
    session_cookie="daydream_session",
    https_only=False,  # friend-scope; box is on a private LAN/Tailscale only
)
app.include_router(auth.router)
app.include_router(ws.router)


@app.get("/login")
async def login_form() -> HTMLResponse:
    return HTMLResponse(_LOGIN_HTML)


@app.get("/")
async def root(request: Request):
    if not request.session.get("authed"):
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
<p><a href="/api/logout">leave</a></p>
</body></html>
"""
