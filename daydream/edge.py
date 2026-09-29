"""`bin/game edge ...`: the Cloudflare side of daydream prod (SPEC 2026-09-27
criteria 14-16; docs/CLOUDFLARE-SETUP.md).

Runs as the operator with the dev venv, standard library only. Credentials
come from `~/.config/daydream/cloudflare.env` (0600, never in the repo, never
readable by the prod service user):

    CLOUDFLARE_API_TOKEN=...   Workers Scripts:Edit, Workers KV Storage:Edit,
                               Workers Routes:Edit on your zone
    CLOUDFLARE_ACCOUNT_ID=...

The KV namespace id is not secret; it lives in edge/wrangler.toml.

Verbs:

- `status`: the flag and what the public URL says right now
- `sleep [NOTE]` / `wake`: just the edge flag; `bin/game prod sleep|wake`
  also stop and start the box
- `deploy`: `wrangler deploy` of edge/
- `secrets`: set the Access service token on the Worker, typed by you
- `kv-create`: make the KV namespace and print the id for wrangler.toml
- `tail`: live Worker logs
- `test`: the Worker's unit tests
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
EDGE = REPO / "edge"
CREDENTIALS = Path.home() / ".config" / "daydream" / "cloudflare.env"
API = "https://api.cloudflare.com/client/v4"


class EdgeError(RuntimeError):
    pass


def _creds() -> dict[str, str]:
    out: dict[str, str] = {}
    if CREDENTIALS.exists():
        for line in CREDENTIALS.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, _, v = line.partition("=")
                out[k.strip()] = v.strip().strip("'\"")
    for k in ("CLOUDFLARE_API_TOKEN", "CLOUDFLARE_ACCOUNT_ID"):
        if os.environ.get(k):
            out[k] = os.environ[k]
    return out


def kv_namespace_id() -> str | None:
    text = (EDGE / "wrangler.toml").read_text()
    m = re.search(r'\[\[kv_namespaces\]\][^\[]*?\bid\s*=\s*"([^"]+)"', text, flags=re.S)
    if not m or m.group(1).startswith("REPLACE"):
        return None
    return m.group(1)


def configured() -> bool:
    c = _creds()
    return bool(c.get("CLOUDFLARE_API_TOKEN") and c.get("CLOUDFLARE_ACCOUNT_ID")
                and kv_namespace_id())


def _api(method: str, path: str, body: bytes | None = None,
         content_type: str = "application/json") -> bytes:
    c = _creds()
    if not c.get("CLOUDFLARE_API_TOKEN"):
        raise EdgeError(f"no CLOUDFLARE_API_TOKEN in {CREDENTIALS}")
    req = urllib.request.Request(API + path, data=body, method=method, headers={
        "Authorization": f"Bearer {c['CLOUDFLARE_API_TOKEN']}", "Content-Type": content_type})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise EdgeError(f"Cloudflare API {method} {path}: {e.code} "
                        f"{e.read().decode('utf-8', 'replace')[:300]}") from None
    except urllib.error.URLError as e:
        raise EdgeError(f"Cloudflare API unreachable: {e.reason}") from None


def _kv_path(key: str) -> str:
    acct = _creds().get("CLOUDFLARE_ACCOUNT_ID")
    ns = kv_namespace_id()
    if not acct or not ns:
        raise EdgeError("the edge is not configured (docs/CLOUDFLARE-SETUP.md)")
    return f"/accounts/{acct}/storage/kv/namespaces/{ns}/values/{urllib.request.quote(key, safe='')}"


def kv_put(key: str, value: str) -> None:
    _api("PUT", _kv_path(key), value.encode("utf-8"), content_type="text/plain")


def kv_get(key: str) -> str | None:
    try:
        return _api("GET", _kv_path(key)).decode("utf-8")
    except EdgeError as e:
        if ": 404 " in str(e):
            return None
        raise


def kv_delete(key: str) -> None:
    try:
        _api("DELETE", _kv_path(key))
    except EdgeError as e:
        if ": 404 " not in str(e):
            raise


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


WORD_KEYS = ("place", "title", "operator", "cookie")


def set_state(state: str, note: str | None = "", words: dict | None = None) -> dict:
    """Flip the edge's flag. The Worker reads it on every request; KV
    propagates worldwide within about a minute. The flag also carries the
    attached instance's words (docs/INSTANCES.md: the place, its title, the
    operator's title, the session cookie's name); without `words` it keeps
    the ones it has, so a bare `edge sleep` never forgets which instance is
    attached. `note=None` keeps the note it has (a swap must not erase an
    asleep page's "back Sunday")."""
    if state not in ("awake", "asleep"):
        raise EdgeError("state is 'awake' or 'asleep'")
    prev = get_state() if words is None or note is None else {}
    if words is None:
        words = {k: prev[k] for k in WORD_KEYS if isinstance(prev.get(k), str)}
    if note is None:
        note = prev.get("note") if isinstance(prev.get("note"), str) else ""
    body = {"state": state, "note": (note or "")[:280], "since": _now()}
    body.update({k: str(v)[:80] for k, v in words.items() if k in WORD_KEYS and v})
    kv_put("state", json.dumps(body))
    return body


def get_state() -> dict:
    raw = kv_get("state")
    try:
        s = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        s = None
    return s if isinstance(s, dict) else {"state": "awake", "note": "", "since": None}


def get_uptime() -> dict:
    """What the Worker's uptime watch recorded (worker.js `watch`): an open
    unplanned outage's start, and the last ones, newest first."""
    try:
        u = json.loads(kv_get("uptime") or "null")
    except json.JSONDecodeError:
        u = None
    if not isinstance(u, dict):
        return {"down_since": None, "outages": []}
    outages = u.get("outages") if isinstance(u.get("outages"), list) else []
    return {"down_since": u.get("down_since"), "outages": outages}


def describe_uptime(u: dict) -> str:
    if u.get("down_since"):
        return f"DOWN since {u['down_since']} (unplanned)"
    last = next((o for o in u.get("outages", []) if isinstance(o, dict)), None)
    if last:
        return (f"up; last unplanned outage {last.get('from')} to {last.get('to')} "
                f"({len(u['outages'])} recorded)")
    return "up; no unplanned outage recorded"


def describe_state() -> str:
    s = get_state()
    out = s.get("state", "?")
    if s.get("note"):
        out += f" ({s['note']})"
    if s.get("since"):
        out += f" since {s['since']}"
    if s.get("place"):
        out += f"; {s['place']}"
    try:
        out += "; watch: " + describe_uptime(get_uptime())
    except (EdgeError, OSError):
        out += "; watch: unknown"
    return out


def public_status_url() -> str:
    """The Worker's public status route, from edge/wrangler.toml's PUBLIC_HOST
    and BASE vars, so a fork probes its own instance (codereview WARN
    2026-09-28b)."""
    text = (EDGE / "wrangler.toml").read_text()
    host = re.search(r'^PUBLIC_HOST\s*=\s*"([^"]+)"', text, flags=re.M)
    base = re.search(r'^BASE\s*=\s*"([^"]*)"', text, flags=re.M)
    if not host:
        raise EdgeError("edge/wrangler.toml has no PUBLIC_HOST var")
    prefix = (base.group(1) if base else "").strip("/")
    return f"https://{host.group(1)}/" + (f"{prefix}/" if prefix else "") + "edge/status"


def public_status() -> dict | None:
    # Cloudflare's Browser Integrity Check refuses urllib's default
    # User-Agent (error 1010), so the probe names itself.
    req = urllib.request.Request(public_status_url(), headers={"User-Agent": "daydream-edge-cli"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.loads(r.read())
    except (urllib.error.URLError, OSError, ValueError):
        return None


MANIFEST = Path.home() / ".local" / "state" / "daydream" / "keepsakes-manifest.json"
KEEPSAKE_PREFIXES = ("keepsakes:", "portrait:")


def _kv_bulk_put(items: list[dict]) -> None:
    acct = _creds().get("CLOUDFLARE_ACCOUNT_ID")
    ns = kv_namespace_id()
    for i in range(0, len(items), 1000):
        _api("PUT", f"/accounts/{acct}/storage/kv/namespaces/{ns}/bulk",
             json.dumps(items[i:i + 1000]).encode())


def desired_keys(doc: dict) -> dict[str, tuple[str, bool]]:
    """The KV keys a keepsakes document maps to: key -> (value, is_base64)."""
    out: dict[str, tuple[str, bool]] = {
        "passes": (json.dumps(doc["passes"], sort_keys=True), False),
        "chronicle": (json.dumps(doc["chronicle"]), False),
    }
    portraits = doc.get("portraits") or {}
    for acct, entry in doc["accounts"].items():
        out[f"keepsakes:{acct}"] = (json.dumps(entry, sort_keys=True), False)
        if entry.get("portrait") and portraits.get(acct):
            out[f"portrait:{acct}"] = (portraits[acct], True)
    return out


def plan_sync(desired: dict[str, tuple[str, bool]],
              manifest: dict[str, str]) -> tuple[dict[str, str], list[str], list[str]]:
    """(new manifest, keys to write, keys to delete). Only changed values are
    written: KV's free tier allows 1000 writes a day, and an hourly sync of
    unchanged keepsakes should cost none."""
    import hashlib

    new = {k: hashlib.sha256(v.encode()).hexdigest() for k, (v, _) in desired.items()}
    write = sorted(k for k, h in new.items() if manifest.get(k) != h)
    delete = sorted(k for k in manifest if k not in new and k.startswith(KEEPSAKE_PREFIXES))
    return new, write, delete


def sync_keepsakes(release: Path) -> dict:
    """Export keepsakes with the prod release's code and push the changes to
    KV (criterion 16). A revoked or disabled account's keepsakes and passes
    disappear here."""
    from daydream import prodctl

    if not configured():
        raise EdgeError("the edge is not configured (docs/CLOUDFLARE-SETUP.md)")
    # Exported by the service user; the operator only receives the bytes.
    r = prodctl.run_release_python(release, ["-m", "daydream.keepsakes", "export", "--stdout"],
                                   check=False, capture=True)
    if r.returncode != 0:
        raise EdgeError("keepsakes export failed: " + (r.stderr or r.stdout)[-500:])
    desired = desired_keys(json.loads(r.stdout))
    manifest = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else {}
    new, write, delete = plan_sync(desired, manifest)
    if write:
        _kv_bulk_put([{"key": k, "value": desired[k][0], "base64": desired[k][1]} for k in write])
    for k in delete:
        kv_delete(k)
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(new, indent=1))
    summary = {"written": len(write), "deleted": len(delete), "keys": len(new)}
    print(f"keepsakes: {summary['written']} written, {summary['deleted']} removed, "
          f"{summary['keys']} in all")
    return summary


# ---- wrangler ------------------------------------------------------------------------


def _node_env() -> dict[str, str]:
    """The environment with node's bin dir first on PATH: node on PATH, else
    the newest ~/.nvm install. A systemd timer's PATH has no ~/.nvm, so the
    weekly offsite could not find npx (codereview WARN 2026-09-28)."""
    env = dict(os.environ)
    node = shutil.which("node")
    if node is None:
        installs = sorted((Path.home() / ".nvm" / "versions" / "node").glob("*/bin/node"),
                          key=lambda p: [int(n) for n in re.findall(r"\d+", p.parent.parent.name)])
        node = str(installs[-1]) if installs else None
    if node is not None:
        env["PATH"] = str(Path(node).parent) + os.pathsep + env.get("PATH", "")
    return env


def _wrangler_env() -> dict[str, str]:
    c = _creds()
    if not c.get("CLOUDFLARE_API_TOKEN"):
        raise EdgeError(f"no CLOUDFLARE_API_TOKEN in {CREDENTIALS}")
    env = _node_env()
    env["CLOUDFLARE_API_TOKEN"] = c["CLOUDFLARE_API_TOKEN"]
    if c.get("CLOUDFLARE_ACCOUNT_ID"):
        env["CLOUDFLARE_ACCOUNT_ID"] = c["CLOUDFLARE_ACCOUNT_ID"]
    env["WRANGLER_SEND_METRICS"] = "false"
    return env


def _ensure_node_modules() -> None:
    if not (EDGE / "node_modules" / ".bin" / "wrangler").exists():
        subprocess.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=EDGE, check=True,
                       env=_node_env())


def deploy() -> int:
    if not kv_namespace_id():
        raise EdgeError("edge/wrangler.toml has no KV namespace id yet: run `bin/game edge kv-create`")
    test()
    _ensure_node_modules()
    return subprocess.run(["npx", "--no-install", "wrangler", "deploy"], cwd=EDGE,
                          env=_wrangler_env()).returncode


def secrets() -> int:
    _ensure_node_modules()
    print("Paste each value when wrangler asks (Zero Trust > Access > Service Auth > "
          "the daydream-edge token). They go straight to Cloudflare.")
    for name in ("ACCESS_CLIENT_ID", "ACCESS_CLIENT_SECRET"):
        r = subprocess.run(["npx", "--no-install", "wrangler", "secret", "put", name], cwd=EDGE,
                           env=_wrangler_env())
        if r.returncode != 0:
            return r.returncode
    return 0


def kv_create() -> int:
    acct = _creds().get("CLOUDFLARE_ACCOUNT_ID")
    if not acct:
        raise EdgeError(f"no CLOUDFLARE_ACCOUNT_ID in {CREDENTIALS}")
    data = json.loads(_api("POST", f"/accounts/{acct}/storage/kv/namespaces",
                           json.dumps({"title": "daydream-edge-state"}).encode()))
    ns = data["result"]["id"]
    print(f"KV namespace id: {ns}")
    print('put it in edge/wrangler.toml ([[kv_namespaces]] id = "...") and commit')
    return 0


def tail() -> int:
    _ensure_node_modules()
    # Errors only, in the short form: the JSON form (wrangler's default off a
    # terminal, which is how an agent runs it) prints whole request URLs and
    # headers, invite links among them, into whatever reads the output
    # (security review 2026-09-29).
    return subprocess.run(["npx", "--no-install", "wrangler", "tail", "daydream-edge",
                           "--format", "pretty", "--status", "error"], cwd=EDGE,
                          env=_wrangler_env()).returncode


def test() -> int:
    files = sorted(str(p) for p in (EDGE / "test").glob("*.test.js"))
    r = subprocess.run(["node", "--test", *files], cwd=EDGE, env=_node_env())
    if r.returncode != 0:
        raise EdgeError("the edge Worker's tests failed")
    return 0


def status() -> int:
    if configured():
        print("edge flag: " + describe_state())
    else:
        print(f"edge flag: not configured ({CREDENTIALS} and the KV id in edge/wrangler.toml)")
    pub = public_status()
    print("public:    " + (json.dumps(pub) if pub else f"no answer from {public_status_url()}"))
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bin/game edge", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("status", "wake", "deploy", "secrets", "kv-create", "tail", "test"):
        sub.add_parser(name)
    s = sub.add_parser("sleep")
    s.add_argument("note", nargs="?", default="")
    args = p.parse_args(argv)
    try:
        if args.cmd == "status":
            return status()
        if args.cmd == "sleep":
            print("edge: asleep " + json.dumps(set_state("asleep", args.note)))
            return 0
        if args.cmd == "wake":
            print("edge: awake " + json.dumps(set_state("awake")))
            return 0
        return {"deploy": deploy, "secrets": secrets, "kv-create": kv_create,
                "tail": tail, "test": test}[args.cmd]()
    except (EdgeError, subprocess.CalledProcessError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
