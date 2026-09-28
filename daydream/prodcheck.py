"""`bin/game prod check`: prove the live village still holds every invariant
the bring-up verified by hand (docs/runbooks/verify.md).

Read-only: a handful of GETs, one cross-origin POST the CSRF check refuses
before any handler runs, one anonymous WebSocket upgrade and, while awake,
one WebSocket handshake with the CLI's own account (which has no toon, so the
server answers `needs_toon` and creates nothing). Safe to run any time, awake
or asleep; exit status 1 when anything fails.

Each check is a small pure function over a `Reply` so the unit tests can
feed it canned responses (tests/test_prodcheck.py); `main` wires them to the
real network.
"""

from __future__ import annotations

import http.client
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

REPO = Path(__file__).resolve().parent.parent
UA = "daydream-prod-check"  # Cloudflare refuses urllib's default User-Agent (1010)
TIMERS = ("daydream-backup.service", "daydream-keepsakes.service", "daydream-offsite.service")


@dataclass
class Reply:
    status: int
    headers: list[tuple[str, str]] = field(default_factory=list)
    body: bytes = b""

    def header(self, name: str) -> str:
        return next((v for k, v in self.headers if k.lower() == name.lower()), "")

    def cookies(self) -> list[str]:
        return [v for k, v in self.headers if k.lower() == "set-cookie"]

    def json(self) -> dict:
        try:
            v = json.loads(self.body or b"null")
        except ValueError:
            return {}
        return v if isinstance(v, dict) else {}


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    warn_only: bool = False


@dataclass
class Target:
    """Where to look. `public` is scheme://host (https://www.eidolon.com);
    `base` the path prefix (/daydream/); `origin_host` the tunnel hostname."""
    public: str
    base: str
    origin_host: str

    @property
    def root(self) -> str:
        return self.public + self.base

    @property
    def apex(self) -> str | None:
        host = urlsplit(self.public).hostname or ""
        return host[4:] if host.startswith("www.") else None


def _no_access_cookie(r: Reply) -> bool:
    return not any(c.lstrip().startswith("CF_") for c in r.cookies())


# ---- the checks (pure) ---------------------------------------------------------


def check_edge_status(r: Reply, expect: str | None) -> Check:
    s = r.json()
    state = s.get("state")
    if r.status != 200 or state not in ("awake", "asleep"):
        return Check("edge status", False, f"{r.status}: no state in the edge's answer")
    if expect and state != expect:
        why = (" (the origin is unreachable: tunnel or service down?)"
               if expect == "awake" and s.get("unplanned") else "")
        return Check("edge status", False, f"public says {state}, expected {expect}{why}")
    note = f" ({s['note']})" if s.get("note") else ""
    return Check("edge status", True, f"{state}{note}")


def check_front_door(r: Reply, awake: bool, base: str) -> Check:
    body = r.body.decode("utf-8", "replace")
    if awake:
        ok = r.status == 200 and f'<base href="{base}"' in body
        return Check("front door", ok, f"{r.status}" + ("" if ok else f", expected 200 with <base href=\"{base}\">"))
    ok = r.status == 503 and "asleep" in body
    return Check("front door", ok, f"{r.status} asleep page" if ok else f"{r.status}, expected the 503 asleep page")


def check_api_signed_out(r: Reply, awake: bool) -> Check:
    if awake:
        return Check("api signed out", r.status == 401, f"{r.status} (expected 401)")
    ok = r.status == 503 and r.json().get("asleep") is True
    return Check("api signed out", ok, f"{r.status} (expected 503 asleep JSON)")


def check_cross_origin_refused(r: Reply) -> Check:
    return Check("cross-origin login", r.status == 403, f"{r.status} (expected 403)")


def check_redirect(name: str, r: Reply, want: str) -> Check:
    loc = r.header("location")
    ok = r.status in (301, 302, 307, 308) and loc == want
    return Check(name, ok, f"{r.status} -> {loc or 'nothing'}" + ("" if ok else f" (expected -> {want})"))


def check_origin_locked(r: Reply) -> Check:
    return Check("origin locked", r.status == 403,
                 f"{r.status} without the service token (expected 403 from Access)")


def check_ws_anonymous(r: Reply) -> Check:
    ok = _no_access_cookie(r)
    return Check("anonymous ws upgrade", ok,
                 f"{r.status}, no Access cookie" if ok else
                 f"{r.status} carries Access's CF_Authorization cookie (the Worker must strip it)")


def check_ws_session(status: int, headers: list[tuple[str, str]], frames: list[str],
                     close_code: int | None) -> Check:
    leak = not _no_access_cookie(Reply(status, headers))
    if status != 101 or leak:
        return Check("session ws", False, f"handshake {status}" + (", Access cookie on the 101" if leak else ""))
    if not frames:
        return Check("session ws", False, "connected but no frame arrived")
    if frames[0] == "needs_toon" and close_code != 1000:
        return Check("session ws", False, f"needs_toon then close {close_code} (expected a clean 1000)")
    return Check("session ws", True, f"101, {frames[0]}, close {close_code}")


def check_timer(unit: str, props: dict[str, str]) -> Check:
    """`systemctl show` properties of a timer-run oneshot service."""
    name = unit.removesuffix(".service").removeprefix("daydream-") + " job"
    ran = props.get("ExecMainExitTimestamp", "").strip()
    if ran in ("", "n/a"):
        return Check(name, True, "not run yet")
    if props.get("Result") == "success":
        return Check(name, True, f"ok (last {ran})")
    return Check(name, False, f"{props.get('Result')} (last {ran}; journalctl -u {unit})")


def check_release(release: str | None, head: str, behind: str) -> Check:
    if release is None:
        return Check("release", False, "none deployed")
    if release == head:
        return Check("release", True, f"{release} (HEAD)")
    return Check("release", True, f"{release}, HEAD {head}: {behind}", warn_only=True)


# ---- the network ------------------------------------------------------------------


def http_request(method: str, url: str, headers: dict | None = None, body: bytes | None = None,
                 timeout: float = 15.0) -> Reply:
    """One request over HTTP/1.1, redirects NOT followed (a WebSocket upgrade
    must be HTTP/1.1 to reach the Worker's upgrade branch)."""
    u = urlsplit(url)
    conn_cls = http.client.HTTPSConnection if u.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(u.hostname, u.port, timeout=timeout)
    try:
        path = (u.path or "/") + (f"?{u.query}" if u.query else "")
        conn.request(method, path, body=body, headers={"User-Agent": UA, **(headers or {})})
        resp = conn.getresponse()
        data = resp.read(200_000)
        return Reply(resp.status, list(resp.getheaders()), data)
    finally:
        conn.close()


def ws_session(url: str, cookie: str, origin: str) -> tuple[int, list[tuple[str, str]], list[str], int | None]:
    from websockets.exceptions import ConnectionClosed, InvalidStatus
    from websockets.sync.client import connect

    frames: list[str] = []
    try:
        with connect(url, additional_headers={"Cookie": cookie, "Origin": origin, "User-Agent": UA},
                     open_timeout=20) as ws:
            headers = list(ws.response.headers.raw_items())
            try:
                while len(frames) < 3:
                    frames.append(json.loads(ws.recv(timeout=8)).get("kind", "?"))
            except TimeoutError:
                return 101, headers, frames, None
            except ConnectionClosed as e:
                return 101, headers, frames, e.rcvd.code if e.rcvd else None
            return 101, headers, frames, None
    except InvalidStatus as e:
        return e.response.status_code, list(e.response.headers.raw_items()), [], None


def systemctl_show(unit: str) -> dict[str, str]:
    r = subprocess.run(["systemctl", "show", unit, "-p", "Result", "-p", "ExecMainExitTimestamp",
                        "-p", "ExecMainStatus"], capture_output=True, text=True)
    return dict(line.split("=", 1) for line in r.stdout.splitlines() if "=" in line)


def timer_checks() -> list[Check]:
    return [check_timer(u, systemctl_show(u)) for u in TIMERS]


def target_from_config(env: dict[str, str]) -> Target:
    public = env.get("DAYDREAM_PUBLIC_ORIGIN", "").rstrip("/")
    base = env.get("DAYDREAM_PUBLIC_BASE", "/")
    base = "/" + base.strip("/") + "/" if base.strip("/") else "/"
    toml = (REPO / "edge" / "wrangler.toml").read_text()
    m = re.search(r'^ORIGIN\s*=\s*"([^"]+)"', toml, flags=re.M)
    origin_host = urlsplit(m.group(1)).hostname if m else ""
    return Target(public, base, origin_host or "")


def run(target: Target, *, awake: bool, flag: str | None, cookie: str | None,
        cookie_name: str, request=http_request, session=ws_session) -> list[Check]:
    root = target.root
    out = [check_edge_status(request("GET", root + "edge/status"), flag)]
    out.append(check_front_door(request("GET", root, {"Accept": "text/html"}), awake, target.base))
    out.append(check_api_signed_out(request("GET", root + "api/me", {"Accept": "application/json"}),
                                    awake))
    if awake:
        out.append(check_cross_origin_refused(request(
            "POST", root + "api/login",
            {"Origin": "https://example.invalid", "Content-Type": "application/json"},
            b'{"username": "", "password": ""}')))
    out.append(check_redirect("no-slash redirect", request("GET", root.rstrip("/")), root))
    if target.apex:
        out.append(check_redirect("apex redirect",
                                  request("GET", f"https://{target.apex}{target.base}"), root))
    if target.origin_host:
        out.append(check_origin_locked(request("GET", f"https://{target.origin_host}/healthz")))
    out.append(check_ws_anonymous(request("GET", root + "ws", {
        "Upgrade": "websocket", "Connection": "Upgrade", "Sec-WebSocket-Version": "13",
        "Sec-WebSocket-Key": "dGhlIHNhbXBsZSBub25jZQ=="})))
    if awake and cookie:
        c = cookie if "=" in cookie else f"{cookie_name}={cookie}"
        ws_url = "wss://" + root.split("://", 1)[1] + "ws"
        out.append(check_ws_session(*session(ws_url, c, target.public)))
    return out


def report(checks: list[Check], say=print) -> int:
    failed = 0
    for c in checks:
        tag = "ok  " if c.ok and not c.warn_only else ("note" if c.ok else "FAIL")
        failed += 0 if c.ok else 1
        say(f"{tag} {c.name}: {c.detail}")
    say(f"{len(checks) - failed}/{len(checks)} checks passed" if not failed
        else f"{failed} check(s) FAILED (docs/runbooks/verify.md says what each means)")
    return 1 if failed else 0


def main() -> int:
    from daydream import prodctl

    env = prodctl.prod_env()
    target = target_from_config(env)
    if not target.public:
        print("error: DAYDREAM_PUBLIC_ORIGIN is not set in prod.env", file=sys.stderr)
        return 1
    rel = prodctl.current_release()
    awake = prodctl.unit_active(prodctl.UNIT)
    edge = prodctl._edge()
    flag = None
    if edge is not None:
        try:
            flag = edge.get_state().get("state")
        except (edge.EdgeError, OSError):
            flag = None
    head = prodctl.resolve_ref("HEAD")[:12]
    checks = [check_release(rel.name if rel else None, head,
                            prodctl.behind(rel.name, head) if rel else "")]
    # Awake to the public only when the service runs AND the flag isn't
    # asleep; otherwise the Worker must show the asleep page (planned or not).
    expect = "awake" if (awake and flag != "asleep") else "asleep"
    cookie = prodctl.cli_cookie(rel) if (expect == "awake" and rel is not None) else None
    checks += run(target, awake=expect == "awake", flag=expect, cookie=cookie,
                  cookie_name=f"dd_session_{env.get('DAYDREAM_ENV', 'prod')}")
    checks += timer_checks()
    return report(checks)
