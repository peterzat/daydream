"""`bin/game playthrough`: a blind new player in a real browser (the
/playthrough skill).

A playthrough hands the village to a frontier model that knows nothing about
this codebase and lets it play the way a friend does: a browser window,
screenshots, clicks and typing. Everything around that player lives here.

    bin/game playthrough setup [--name "Full Name"] [--persona TEXT] [--moves N]
    bin/game playthrough player [--model M]
    bin/game playthrough status
    bin/game playthrough teardown [--purge]

`setup` builds a fresh village in the session's own data dir (the canonical
envelope, art copied from dev's graded cache, nothing of dev's world or
accounts), makes up an account, starts the game server on a free loopback
port and a headless Chromium on its front door, and writes the player's
folder: BRIEF.md (docs/playtests/BROWSER-BRIEF.md, filled in) and ./browser.
`player` runs the player: `claude -p` in that folder, restricted to ./browser
and its own files (no CLAUDE.md, no settings, no MCP, no other command),
streaming its transcript to player.jsonl. It blocks; run it in the
background. `teardown` stops the server and the browser and copies the
report, the notes and the screenshots into playthroughs/ (committed, with
its spoiler notice), with a session record appended; its copy of the action
log masks the made-up password and names screenshots by their place there.

The player's verbs, through ./browser. Each prints the path of a new
screenshot and little else: the screen is the player's only way to see the
game. Numbered tags drawn on the screenshot mark what can be clicked (orange
on a thing the player has not seen before):

    look | click N | click X,Y | type "words" [--enter] | key KEY
    scroll [N|X,Y] up|down [--px N] | wait SECONDS | reload | open PATH

A tag counts only what a person could see: inside the window, not clipped by
a scrolling panel, not hidden or transparent, not covered by something on
top. The browser plays at a person's pace: a move that comes before the last
screenshot could have been looked at is refused, the notes must keep up with
the acting moves, and the move budget ends the session. Page errors and
failed requests go to the session's log for the report, never to the player.
"""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import io
import json
import os
import random
import re
import shlex
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
from datetime import date, datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from daydream import config

ROOT = Path(__file__).resolve().parent.parent
BRIEF_TEMPLATE = ROOT / "docs" / "playtests" / "BROWSER-BRIEF.md"
ENVELOPE = ROOT / "worlds" / "lost-hours.json"
VIEWPORT = {"width": 1280, "height": 800}
DEFAULT_MOVES = 150
DEFAULT_MODEL = "opus"
MAX_WAIT_S = 300
IDLE_EXIT_S = 4 * 3600  # a browser nobody drives closes itself
# The page's own "thinking..." lines: a person waits those out, and so does
# the settle after an action.
BUSY_SELECTOR = ".evt-pending, .evt-thinking"
PLAYER_VERBS = ("look", "click", "type", "key", "scroll", "wait", "reload", "open")
ACTING_VERBS = ("click", "type", "key", "reload", "open")  # the notes keep up with these
MIN_GAP_S = 2.0      # sooner than a screenshot can be looked at: a chained move
NOTE_EVERY = 3       # acting moves allowed before notes.md must change again
BUDGET_GRACE = 20    # moves past the budget before the browser stops
DEFAULT_PERSONA = (
    "Someone who enjoys cozy games and good writing, plays on a laptop in the "
    "evening, and has never played a text adventure. Curious and patient: reads "
    "what the screen says, tries the obvious thing first, and is mildly annoyed "
    "when a game does not explain itself.")

_FIRST = ("Hollis", "Marguerite", "Teodor", "Ines", "Callum", "Priya", "Odette", "Rafael",
          "Junie", "Anselm", "Maeve", "Tobias", "Noor", "Silas", "Wilhelmina", "Dario")
_LAST = ("Marr", "Okafor", "Lindqvist", "Brennan", "Castellanos", "Achterberg", "Whitlow",
         "Sato", "Ferreira", "Pell", "Abernathy", "Kowalczyk")
_WORDS = ("copper", "meadow", "lantern", "quiet", "harbor", "thistle", "pebble", "orchard",
          "willow", "ember", "saffron", "juniper", "kettle", "marble", "hollow", "fern")


class Refusal(Exception):
    """A verb the browser cannot do as asked; the message is for the player."""


# ---- where things live --------------------------------------------------------------


def reports_dir() -> Path:
    """The gitignored folder the reports land in."""
    return Path(os.environ.get("DAYDREAM_PLAYTHROUGHS_DIR") or ROOT / "playthroughs")


def sessions_root() -> Path:
    return config.data_root() / "playthroughs"


def paths(sdir: Path) -> dict[str, Path]:
    player = sdir / "player"
    return {
        "session": sdir / "session.json",
        "data": sdir / "data",              # the server's DAYDREAM_DATA_DIR
        "player": player,                   # the player's cwd: all it can see
        "shots": player / "shots",
        "notes": player / "notes.md",
        "report": player / "report.md",
        "brief": player / "BRIEF.md",
        "wrapper": player / "browser",
        "server_log": sdir / "server.log",
        "browser_log": sdir / "browser.log",
        "actions": sdir / "actions.log",
        "page_errors": sdir / "page-errors.log",
        "transcript": sdir / "player.jsonl",
        "player_err": sdir / "player.err",
    }


def sock_path(sdir: Path) -> Path:
    """Short, so a long session dir cannot overflow a Unix socket's path."""
    base = os.environ.get("XDG_RUNTIME_DIR") or tempfile.gettempdir()
    tag = hashlib.sha256(str(sdir.resolve()).encode()).hexdigest()[:12]
    return Path(base) / f"dd-playthrough-{tag}.sock"


def load_session(sdir: Path) -> dict:
    p = paths(sdir)["session"]
    if not p.exists():
        raise SystemExit(f"no playthrough session at {sdir}")
    return json.loads(p.read_text())


def save_session(sdir: Path, sess: dict) -> None:
    p = paths(sdir)["session"]
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(sess, indent=2) + "\n")
    os.chmod(tmp, 0o600)  # it holds the made-up account's password
    tmp.replace(p)


def current_session_dir() -> Path:
    ptr = sessions_root() / "current"
    if not ptr.exists():
        raise SystemExit("no current playthrough; run: bin/game playthrough setup")
    return sessions_root() / ptr.read_text().strip()


def new_session_id(root: Path, day: str, username: str) -> str:
    sid, n = f"{day}-{username}", 2
    while (root / sid).exists() or (reports_dir() / f"{sid}.md").exists():
        sid, n = f"{day}-{username}-{n}", n + 1
    return sid


# ---- the made-up friend --------------------------------------------------------------


def make_friend(rng: random.Random, name: str | None = None) -> dict:
    """A plausible person: a full name, a username from it, a password."""
    name = (name or f"{rng.choice(_FIRST)} {rng.choice(_LAST)}").strip()
    first = re.sub(r"[^a-z0-9]", "", name.split()[0].lower()) if name.split() else ""
    username = first if len(first) >= 3 else f"friend{rng.randint(100, 999)}"
    password = "-".join(rng.sample(_WORDS, 3)) + f"-{rng.randint(10, 99)}"
    return {"name": name, "username": username[:24], "password": password}


def invite_message(friend: dict, url: str) -> str:
    """What the friend reads: the village's own invitation words, with the
    sign-in already made for them (the playthrough skips the invite flow)."""
    from daydream import instance

    first = friend["name"].split()[0]
    blurb = instance.DEFAULTS["invite_blurb"]
    return (f"Hi {first}! You're invited to daydream, {blurb}. I set up your sign-in "
            f"already: open {url} and sign in as {friend['username']} with the password "
            f"{friend['password']}.")


def render_brief(*, invite: str, persona: str, moves: int, day: str,
                 template: Path = BRIEF_TEMPLATE) -> str:
    text = template.read_text()
    for key, value in {"invite": invite, "persona": persona, "moves": str(moves),
                       "date": day}.items():
        text = text.replace("{" + key + "}", value)
    return text


def wrapper_script(sdir: Path) -> str:
    """./browser: the player's only command. It reaches the player verbs and
    nothing else (`--as-player`). Its Python runs isolated (`-I`): its cwd is
    the player's folder, which the player writes, so nothing there is
    importable."""
    py = shlex.quote(sys.executable)
    return ("#!/bin/sh\n"
            "# The playthrough browser (daydream/playthrough.py). Player verbs only.\n"
            f"exec {py} -I -m daydream.playthrough --session-dir {shlex.quote(str(sdir))} "
            "--as-player \"$@\"\n")


# ---- setup -----------------------------------------------------------------------------


@contextlib.contextmanager
def _data_dir_env(data: Path):
    """Point this process's config, world DB and accounts DB at `data`, and
    put everything back after."""
    from daydream import accounts, db

    saved = {k: os.environ.get(k) for k in ("DAYDREAM_DATA_DIR", "DAYDREAM_INSTANCE")}
    os.environ["DAYDREAM_DATA_DIR"] = str(data)
    os.environ.pop("DAYDREAM_INSTANCE", None)
    config.forget_data_dir()
    try:
        yield
    finally:
        db.close_db()
        accounts.close()
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        config.forget_data_dir()


def build_village(data: Path, art_from: Path | None) -> dict:
    """A fresh canonical village in `data`, its art copied (never rendered)
    from a graded cache. Returns art counts by status."""
    import asyncio

    from daydream import db, prebake
    from daydream.llm import bootstrap

    envelope = json.loads(ENVELOPE.read_text())
    with _data_dir_env(data):
        live = config.live_db_path()
        live.parent.mkdir(parents=True, exist_ok=True)
        bootstrap.load_world(envelope["world"]["name"], envelope, live)
        db.close_db()
        counts: dict[str, int] = {}
        if art_from is not None and art_from.is_dir():
            with contextlib.redirect_stdout(io.StringIO()):
                results = asyncio.run(prebake.prebake(live, from_cache=art_from))
            for r in results:
                counts[r["status"]] = counts.get(r["status"], 0) + 1
    return counts


def create_friend_account(data: Path, friend: dict) -> None:
    from daydream import accounts

    with _data_dir_env(data):
        accounts.init()
        accounts.create_account(friend["username"], friend["password"],
                                display_name=friend["name"])


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def server_env(data: Path, port: int) -> dict[str, str]:
    env = dict(os.environ)
    for k in ("DAYDREAM_INSTANCE", "DAYDREAM_PUBLIC_BASE", "DAYDREAM_PUBLIC_ORIGIN",
              "DAYDREAM_FAKE_NOW"):
        env.pop(k, None)
    env.update({"DAYDREAM_DATA_DIR": str(data), "DAYDREAM_PORT": str(port),
                "DAYDREAM_BIND_HOST": "127.0.0.1", "DAYDREAM_ACCESS": "tailscale",
                "DAYDREAM_ENV": "dev"})
    return env


def _spawn(argv: list[str], log: Path, env: dict | None = None) -> int:
    with open(log, "ab") as out:
        p = subprocess.Popen(argv, cwd=ROOT, env=env, stdout=out, stderr=subprocess.STDOUT,
                             stdin=subprocess.DEVNULL, start_new_session=True)
    return p.pid


def _alive(pid: int | None) -> bool:
    if not pid:
        return False
    try:
        os.kill(pid, 0)
    except (ProcessLookupError, PermissionError):
        return False
    try:  # a zombie child of this process is not alive
        done, _ = os.waitpid(pid, os.WNOHANG)
        return done == 0
    except ChildProcessError:
        return True


def start_server(sdir: Path, port: int, timeout: float = 60.0) -> int:
    import httpx

    p = paths(sdir)
    pid = _spawn([sys.executable, "-m", "uvicorn", "daydream.server:app",
                  "--host", "127.0.0.1", "--port", str(port)],
                 p["server_log"], server_env(p["data"], port))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            raise SystemExit(f"the playthrough server exited at startup; see {p['server_log']}")
        try:
            if httpx.get(f"http://127.0.0.1:{port}/healthz", timeout=1.0).status_code == 200:
                return pid
        except httpx.HTTPError:
            pass
        time.sleep(0.25)
    _stop(pid)
    raise SystemExit(f"the playthrough server did not come up in {timeout:.0f} s; "
                     f"see {p['server_log']}")


def start_browser(sdir: Path, timeout: float = 30.0) -> int:
    p = paths(sdir)
    pid = _spawn([sys.executable, "-m", "daydream.playthrough", "_browser", str(sdir)],
                 p["browser_log"])
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _alive(pid):
            raise SystemExit(f"the browser exited at startup; see {p['browser_log']}")
        try:
            send(sdir, {"cmd": "ping"}, timeout=2)
            return pid
        except OSError:
            time.sleep(0.2)
    _stop(pid)
    raise SystemExit(f"the browser did not start in {timeout:.0f} s; see {p['browser_log']}")


def engines_note() -> list[str]:
    """Warnings for an engine the village will miss (nothing is started)."""
    import httpx

    notes = []
    for name, url in (("vLLM", config.llm_base_url().rstrip("/") + "/models"),
                      ("ComfyUI", config.comfyui_base_url().rstrip("/") + "/system_stats")):
        try:
            httpx.get(url, timeout=2.0).raise_for_status()
        except Exception:
            notes.append(f"warning: {name} is not answering at {url}; the village will be "
                         "foggy or unpainted where it needs it")
    return notes


def setup(name: str | None = None, persona: str | None = None,
          moves: int = DEFAULT_MOVES, seed: int | None = None,
          min_gap_s: float = MIN_GAP_S, note_every: int = NOTE_EVERY) -> dict:
    from daydream.images import cache

    friend = make_friend(random.Random(seed), name)
    day = date.today().isoformat()
    root = sessions_root()
    root.mkdir(parents=True, exist_ok=True)
    sid = new_session_id(root, day, friend["username"])
    sdir = root / sid
    p = paths(sdir)
    p["shots"].mkdir(parents=True)
    art_from = cache.cache_dir()  # dev's graded art, read before the env moves
    art = build_village(p["data"], art_from)
    create_friend_account(p["data"], friend)
    port = free_port()
    base = f"http://127.0.0.1:{port}"
    sess = {"id": sid, "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "base_url": base, "port": port, "friend": friend,
            "persona": persona or DEFAULT_PERSONA, "moves": moves, "art": art,
            "envelope": str(ENVELOPE.relative_to(ROOT)), "build": _head_sha(),
            "sock": str(sock_path(sdir)), "min_gap_s": min_gap_s, "note_every": note_every}
    save_session(sdir, sess)
    sess["server_pid"] = start_server(sdir, port)
    save_session(sdir, sess)
    try:
        sess["browser_pid"] = start_browser(sdir)
    except BaseException:
        _stop(sess["server_pid"])
        raise
    save_session(sdir, sess)
    send(sdir, {"cmd": "open", "path": "/", "internal": True})
    invite = invite_message(friend, base + "/")
    p["brief"].write_text(render_brief(invite=invite, persona=sess["persona"], moves=moves,
                                       day=day))
    p["wrapper"].write_text(wrapper_script(sdir))
    p["wrapper"].chmod(0o755)
    p["notes"].write_text(f"# Notes, {day}\n\n")
    p["report"].write_text("")  # the player only edits; it never needs to create a file
    (root / "current").write_text(sid + "\n")
    return {"id": sid, "dir": str(sdir), "base_url": base, "friend": friend, "art": art,
            "notes": engines_note()}


def _head_sha() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=ROOT,
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return "unknown"


# ---- the player ------------------------------------------------------------------------


def player_argv(model: str = DEFAULT_MODEL, claude: str = "claude") -> list[str]:
    """The player's sandbox: restricted mode (no settings files, file tools
    confined to its folder), no MCP, and in dontAsk mode nothing runs but
    ./browser and edits to its own notes and report. Run with the player's
    folder as cwd, outside the repo, so no CLAUDE.md is discovered."""
    return [claude, "-p", "--restricted", "--tools", "Bash,Read,Write,Edit",
            "--strict-mcp-config", "--permission-mode", "dontAsk",
            "--allowedTools", "Bash(./browser *),Edit(./notes.md),Edit(./report.md)",
            "--append-system-prompt-file", "BRIEF.md",
            "--model", model, "--output-format", "stream-json", "--verbose"]


# All the player gets of the operator's environment (plus LC_*). bin/game
# exports the project .env and the per-host secrets file, and the operator's
# own Claude Code session sets CLAUDE_CODE_*: none of that may follow.
PLAYER_ENV_KEYS = frozenset((
    "PATH", "HOME", "USER", "LOGNAME", "SHELL", "LANG", "TERM",
    "XDG_RUNTIME_DIR", "TMPDIR", "TEMP", "TMP",  # where ./browser finds its socket
    "HTTP_PROXY", "HTTPS_PROXY", "NO_PROXY", "ALL_PROXY",
    "http_proxy", "https_proxy", "no_proxy", "all_proxy",
    "SSL_CERT_FILE", "SSL_CERT_DIR", "NODE_EXTRA_CA_CERTS"))


def player_env() -> dict[str, str]:
    """An allowlist: a shell, a home, a locale, the socket's directory, and a
    proxy if one is set. ./browser carries absolute paths."""
    return {k: v for k, v in os.environ.items() if k in PLAYER_ENV_KEYS or k.startswith("LC_")}


PLAYER_PROMPT = ("Begin your playthrough now. Your brief is in your instructions and in "
                 "BRIEF.md in this folder. Start with: ./browser look")


def run_player(sdir: Path, model: str = DEFAULT_MODEL) -> dict:
    claude = shutil.which("claude")
    if not claude:
        raise SystemExit("the claude CLI is not on PATH")
    p, sess = paths(sdir), load_session(sdir)
    started = time.monotonic()
    with open(p["transcript"], "ab") as out, open(p["player_err"], "ab") as err:
        proc = subprocess.Popen(player_argv(model, claude), cwd=p["player"], env=player_env(),
                                stdin=subprocess.PIPE, stdout=out, stderr=err)
        sess["player"] = {"pid": proc.pid, "model": model, "started":
                          datetime.now(timezone.utc).isoformat(timespec="seconds")}
        save_session(sdir, sess)
        proc.communicate(PLAYER_PROMPT.encode())
    result = transcript_result(p["transcript"])
    sess = load_session(sdir)
    sess["player"].update(exit=proc.returncode, minutes=round((time.monotonic() - started) / 60, 1),
                          result=result)
    save_session(sdir, sess)
    return sess["player"]


def transcript_result(path: Path) -> dict:
    """What a session record reports from a stream-json transcript: its final
    result line, and how many distinct screenshots the player opened (the
    honest measure of playing by sight)."""
    found: dict = {}
    if not path.exists():
        return found
    looked: set[str] = set()
    for line in path.read_text(errors="replace").splitlines():
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if msg.get("type") == "system" and msg.get("subtype") == "init":
            found["session_id"] = msg.get("session_id")
        elif msg.get("type") == "result":
            found.update({k: msg.get(k) for k in ("subtype", "is_error", "num_turns",
                                                   "duration_ms", "total_cost_usd")})
        elif msg.get("type") == "assistant":
            for c in (msg.get("message") or {}).get("content") or []:
                if isinstance(c, dict) and c.get("type") == "tool_use" and c.get("name") == "Read":
                    fp = str((c.get("input") or {}).get("file_path") or "")
                    if "/shots/" in fp:
                        looked.add(fp.rsplit("/", 1)[-1])
    found["shots_read"] = len(looked)
    return found


# ---- teardown and the session record -------------------------------------------------


def _ours(pid: int) -> bool:
    """The pid still runs one of this harness's processes (a pid can be
    reused after a long-dead server)."""
    try:
        cmd = Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ")
    except OSError:
        return True  # no /proc to ask: trust the session's record
    return b"daydream.server:app" in cmd or b"daydream.playthrough" in cmd


def _stop(pid: int | None, grace: float = 10.0) -> None:
    if not _alive(pid) or not _ours(pid):
        return
    try:
        os.killpg(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError):
        return
    deadline = time.monotonic() + grace
    while time.monotonic() < deadline and _alive(pid):
        time.sleep(0.2)
    if _alive(pid):
        with contextlib.suppress(ProcessLookupError, PermissionError):
            os.killpg(pid, signal.SIGKILL)


def session_record(sdir: Path) -> str:
    """The mechanical facts of a session, appended to its report."""
    p, sess = paths(sdir), load_session(sdir)
    actions = []
    if p["actions"].exists():
        for line in p["actions"].read_text().splitlines():
            with contextlib.suppress(ValueError):
                actions.append(json.loads(line))
    by_cmd: dict[str, int] = {}
    refused: dict[str, int] = {}
    shots = 0
    for a in actions:
        if "refused" in a:
            refused[a.get("gate") or "other"] = refused.get(a.get("gate") or "other", 0) + 1
            continue
        by_cmd[a["cmd"]] = by_cmd.get(a["cmd"], 0) + 1
        shots += 1 if a.get("shot") else 0
    errors = p["page_errors"].read_text().splitlines() if p["page_errors"].exists() else []
    server = p["server_log"].read_text(errors="replace") if p["server_log"].exists() else ""
    server_errors = sum(1 for ln in server.splitlines() if " ERROR " in ln or ln.startswith("Traceback"))
    lines = ["## Session record", "",
             "Written by `bin/game playthrough teardown`, not by the player.", "",
             f"- Session `{sess['id']}`: a fresh village from `{sess['envelope']}` at build "
             f"`{sess.get('build', 'unknown')}`; art copied from dev: "
             + (", ".join(f"{n} {k}" for k, n in sorted(sess.get("art", {}).items())) or "none")]
    player = sess.get("player") or {}
    res = player.get("result") or {}
    if actions:
        span = (_parse_t(actions[-1]["t"]) - _parse_t(actions[0]["t"])).total_seconds() / 60
        lines.append(f"- Moves: {sum(by_cmd.values())} ("
                     + ", ".join(f"{k} {n}" for k, n in sorted(by_cmd.items(), key=lambda kv: -kv[1]))
                     + f") over {span:.0f} minutes")
        if "shots_read" in res:
            lines.append(f"- Screenshots the player opened: {res['shots_read']} of {shots}")
        lines.append("- Moves the browser refused: "
                     + (", ".join(f"{k} {n}" for k, n in sorted(refused.items())) or "none")
                     + " (pace: sooner than a look; notes: notes behind; budget: moves spent)")
    else:
        lines.append("- Moves: none")
    if player:
        cost = res.get("total_cost_usd")
        lines.append(f"- Player: `claude -p --model {player.get('model')}`, "
                     f"{res.get('num_turns', '?')} turns, {player.get('minutes', '?')} minutes, "
                     f"ended {res.get('subtype', 'unknown')}"
                     + (f", ${cost:.2f} equivalent" if isinstance(cost, (int, float)) else ""))
    lines.append(f"- Page errors and failed requests: {len(errors)}")
    lines.extend(f"  - `{e[:200]}`" for e in errors[:8])
    if len(errors) > 8:
        lines.append(f"  - and {len(errors) - 8} more in page-errors.log")
    lines.append(f"- Server log errors: {server_errors}")
    return "\n".join(lines) + "\n"


def _parse_t(s: str) -> datetime:
    return datetime.fromisoformat(s)


def shareable_actions(src: Path, password: str) -> str:
    """The action log as the reports folder keeps it, which is committed: each
    screenshot named by its place in the copy's shots/, and the made-up
    account's password masked where the player typed it."""
    out = []
    for line in src.read_text().splitlines():
        try:
            a = json.loads(line)
        except ValueError:
            continue
        if a.get("shot"):
            a["shot"] = f"shots/{Path(a['shot']).name}"
        args = a.get("args") or {}
        if password and password in str(args.get("text", "")):
            a["args"] = {**args, "text": args["text"].replace(password, "•" * len(password))}
        out.append(json.dumps(a))
    return "".join(f"{ln}\n" for ln in out)


def teardown(sdir: Path, purge: bool = False) -> dict:
    p, sess = paths(sdir), load_session(sdir)
    with contextlib.suppress(OSError, ValueError):
        send(sdir, {"cmd": "quit"}, timeout=10)
    _stop(sess.get("browser_pid"))
    _stop(sess.get("server_pid"))
    with contextlib.suppress(FileNotFoundError):
        sock_path(sdir).unlink()
    out = reports_dir()
    extra = out / sess["id"]
    extra.mkdir(parents=True, exist_ok=True)
    for key in ("notes", "page_errors"):
        if p[key].exists():
            shutil.copy2(p[key], extra / p[key].name)
    if p["actions"].exists():
        (extra / p["actions"].name).write_text(
            shareable_actions(p["actions"], sess.get("friend", {}).get("password", "")))
    if p["shots"].is_dir():
        shutil.copytree(p["shots"], extra / "shots", dirs_exist_ok=True)
    wrote_report = p["report"].exists() and p["report"].read_text().strip() != ""
    body = (p["report"].read_text().rstrip() if wrote_report else
            f"# Playthrough {sess['id']}\n\nThe player wrote no report.md; its notes are in "
            f"`{sess['id']}/notes.md`.")
    report = out / f"{sess['id']}.md"
    report.write_text(body + "\n\n" + session_record(sdir))
    ptr = sessions_root() / "current"
    if ptr.exists() and ptr.read_text().strip() == sess["id"]:
        ptr.unlink()
    if purge:
        shutil.rmtree(sdir)
    return {"report": str(report), "extra": str(extra), "player_report": wrote_report}


def status(sdir: Path) -> list[str]:
    p, sess = paths(sdir), load_session(sdir)
    try:
        send(sdir, {"cmd": "ping"}, timeout=2)
        browser = "up"
    except OSError:
        browser = "down"
    moves = len(p["actions"].read_text().splitlines()) if p["actions"].exists() else 0
    player = sess.get("player") or {}
    running = "running" if _alive(player.get("pid")) else (
        f"finished ({(player.get('result') or {}).get('subtype', 'no result')})" if player
        else "not started")
    out = [f"session: {sess['id']}  ({sdir})",
           f"village: {sess['base_url']}  server {'up' if _alive(sess.get('server_pid')) else 'down'}"
           f", browser {browser}",
           f"friend:  {sess['friend']['name']} ({sess['friend']['username']})",
           f"player:  {running}; {moves} browser commands so far"]
    if p["notes"].exists():
        tail = p["notes"].read_text().rstrip().splitlines()[-12:]
        out += ["latest notes:"] + [f"  {ln}" for ln in tail]
    return out


# ---- talking to the browser ------------------------------------------------------------


def send(sdir: Path, req: dict, timeout: float = 90.0) -> dict:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(str(sock_path(sdir)))
        s.sendall(json.dumps(req).encode() + b"\n")
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
    return json.loads(buf or b"{}")


# The page-side helpers every query shares: the part of an element a person
# can see (inside the window and every clipping ancestor, more than a
# sliver), a point on it a click would reach (nothing covering it), its
# visible words, and how a form field reads to someone looking at it.
_JS_HELPERS = r"""
const vw = window.innerWidth, vh = window.innerHeight;
const clipRect = (el) => {
  let l = 0, t = 0, rr = vw, b = vh;
  for (let p = el.parentElement; p && p !== document.documentElement; p = p.parentElement) {
    const cs = getComputedStyle(p);
    if (cs.overflowX !== "visible" || cs.overflowY !== "visible") {
      const pr = p.getBoundingClientRect();
      l = Math.max(l, pr.left); t = Math.max(t, pr.top);
      rr = Math.min(rr, pr.right); b = Math.min(b, pr.bottom);
    }
  }
  return {l, t, r: rr, b};
};
// a rect's visible part inside a clip, or null when that is a sliver:
// 8 px each way, or the whole rect when it is smaller
const within = (r, c) => {
  const l = Math.max(r.left, c.l), t = Math.max(r.top, c.t);
  const rr = Math.min(r.right, c.r), b = Math.min(r.bottom, c.b);
  const minW = Math.max(Math.min(8, r.width), 2), minH = Math.max(Math.min(8, r.height), 2);
  return (rr - l >= minW && b - t >= minH) ? {l, t, r: rr, b} : null;
};
const clipBox = (el) => within(el.getBoundingClientRect(), clipRect(el));
const reaches = (el, x, y) => {
  const h = document.elementFromPoint(x, y);
  return !!h && (h === el || el.contains(h));
};
const hitPoint = (el, box) => {
  const cx = (box.l + box.r) / 2, cy = (box.t + box.b) / 2;
  const pts = [[cx, cy], [box.l + 3, cy], [box.r - 3, cy], [cx, box.t + 3], [cx, box.b - 3],
               [box.l + 3, box.t + 3], [box.r - 3, box.b - 3]];
  for (const [x, y] of pts) if (reaches(el, x, y)) return [Math.round(x), Math.round(y)];
  return null;
};
const seen = (el) => el.checkVisibility({opacityProperty: true, visibilityProperty: true});
const cased = (el, v) => {
  const tt = getComputedStyle(el).textTransform;
  return tt === "uppercase" ? v.toUpperCase() : tt === "lowercase" ? v.toLowerCase() : v;
};
// visible text nodes joined with spaces (innerText runs flex children together)
const textOf = (el) => {
  const parts = [];
  const w = document.createTreeWalker(el, NodeFilter.SHOW_TEXT);
  for (let n = w.nextNode(); n; n = w.nextNode()) {
    const v = n.nodeValue.trim();
    if (v && n.parentElement && seen(n.parentElement)) parts.push(cased(n.parentElement, v));
  }
  return parts.join(" ").replace(/\s+/g, " ").trim();
};
const TEXTLIKE = (el) => el.tagName === "TEXTAREA" || (el.tagName === "INPUT" &&
  !["button", "submit", "reset", "checkbox", "radio", "hidden", "file", "range", "color"].includes(el.type));
// a field as it reads: its kind, the label shown with it, what it holds or hints
const fieldName = (el) => {
  const lab = el.labels && [...el.labels].find(seen);
  return (lab && textOf(lab)) || el.getAttribute("aria-label") || "";
};
const fieldDesc = (el) => {
  const kind = el.type === "password" ? "password field" : "text field";
  const name = fieldName(el);
  const v = el.type === "password" ? "•".repeat(el.value.length) : el.value;
  return kind + (name ? ` "${name}"` : "") +
    (v ? ` containing "${v}"` : el.placeholder ? ` showing "${el.placeholder}"` : "");
};
"""

# Everything a person could click: native controls, and the outermost
# element showing a pointer cursor (the cursor inherits, so its children are
# the same target). Stored on the page so a click by number finds the same
# element even if it has moved. A mark's key is what makes it "the same
# thing" again (a field stays itself whatever is typed in it).
_MARKS_JS = "() => {" + _JS_HELPERS + r"""
const NATIVE = new Set(["A", "BUTTON", "INPUT", "TEXTAREA", "SELECT", "SUMMARY"]);
const label = (el) => {
  const tag = el.tagName;
  let t = "";
  if (tag === "INPUT" && ["button", "submit", "reset"].includes(el.type)) t = el.value;
  else if (tag === "INPUT" && ["checkbox", "radio"].includes(el.type))
    t = `${el.type}${fieldName(el) ? ` "${fieldName(el)}"` : ""}${el.checked ? " (checked)" : ""}`;
  else if (TEXTLIKE(el)) t = fieldDesc(el);
  else if (tag === "SELECT") t = `menu: ${el.selectedOptions[0]?.text || ""}`;
  else t = textOf(el);
  if (!t) {
    const img = el.querySelector("img[alt]");
    const named = (img && img.alt) || el.getAttribute("aria-label") || el.title || "";
    const r = el.getBoundingClientRect();
    t = named ? `icon: ${named}` : `(no label, ${Math.round(r.width)}x${Math.round(r.height)} px)`;
  }
  if (el.disabled || el.getAttribute("aria-disabled") === "true") t += " (greyed out)";
  return t.length > 72 ? t.slice(0, 69) + "..." : t;
};
const keyOf = (el, l) => TEXTLIKE(el)
  ? `${el.type === "password" ? "password" : "text"} field|${fieldName(el)}|${el.placeholder || ""}` : l;
const found = [];
for (const el of document.body.querySelectorAll("*")) {
  if (el.closest("#__pt_overlay")) continue;
  const native = NATIVE.has(el.tagName) || el.isContentEditable;
  let pointer = false;
  if (!native) {
    const cur = getComputedStyle(el).cursor;
    pointer = cur === "pointer" && !(el.parentElement &&
      getComputedStyle(el.parentElement).cursor === "pointer");
  }
  if (!native && !pointer) continue;
  if (el.tagName === "INPUT" && el.type === "hidden") continue;
  if (!seen(el)) continue;
  const box = clipBox(el);
  if (!box || !hitPoint(el, box)) continue;
  const l = label(el);
  found.push({el, box, label: l, key: keyOf(el, l)});
}
found.sort((a, b) => (Math.round(a.box.t / 6) - Math.round(b.box.t / 6)) || (a.box.l - b.box.l));
window.__ptMarks = found.map(f => f.el);
return found.map((f, i) => ({n: i + 1, label: f.label, key: f.key,
  box: {l: Math.round(f.box.l), t: Math.round(f.box.t), r: Math.round(f.box.r), b: Math.round(f.box.b)}}));
}"""

_POINT_JS = "(i) => {" + _JS_HELPERS + r"""
if (!window.__ptMarks) return "unlooked";
const el = window.__ptMarks[i];
if (!el || !el.isConnected || !seen(el)) return null;
const box = clipBox(el);
return box ? hitPoint(el, box) : null;
}"""

_OVERLAY_JS = r"""(marks) => {
const root = document.createElement("div");
root.id = "__pt_overlay";
root.style.cssText = "position:fixed;inset:0;pointer-events:none;z-index:2147483647;";
for (const m of marks) {
  const tag = document.createElement("div");
  tag.textContent = String(m.n);
  // just outside the top-left corner, so a short label stays readable
  const w = 7 * String(m.n).length + 7;
  tag.style.cssText = `position:fixed;left:${Math.max(m.box.l - w + 3, 0)}px;` +
    `top:${Math.max(m.box.t - 11, 0)}px;background:${m.new ? "#ff9a3c" : "#ffe14d"};color:#111;` +
    "font:bold 11px/13px Arial,sans-serif;padding:0 3px;border:1px solid #111;" +
    "border-radius:3px;opacity:0.92;";
  root.appendChild(tag);
}
document.documentElement.appendChild(root);
}"""

_UNOVERLAY_JS = "() => { const o = document.getElementById('__pt_overlay'); if (o) o.remove(); }"

_FOCUS_JS = "() => {" + _JS_HELPERS + r"""
const el = document.activeElement;
if (!el || el === document.body || el === document.documentElement) return {editable: false, label: ""};
const editable = el.isContentEditable || TEXTLIKE(el);
const label = TEXTLIKE(el) ? fieldDesc(el)
  : (textOf(el) || el.getAttribute("aria-label") || el.tagName.toLowerCase()).slice(0, 60);
return {editable, label};
}"""

# Resolves when the page has been still for `quiet` ms since it last changed
# (or for `idle` ms when nothing changed at all: the page shows its own
# thinking line at once for anything slow) and is not showing a thinking
# line, or after `max` ms.
_SETTLE_JS = r"""(o) => new Promise((resolve) => {
const start = performance.now();
let last = start, changed = false;
const obs = new MutationObserver(() => { last = performance.now(); changed = true; });
obs.observe(document.documentElement, {subtree: true, childList: true, characterData: true, attributes: true});
const busy = () => !!document.querySelector(o.busy);
const tick = () => {
  const now = performance.now();
  if (now - start >= o.max) { obs.disconnect(); resolve(busy() ? "busy" : "timeout"); return; }
  const still = changed ? now - last >= o.quiet : now - start >= o.idle;
  if (now - start >= o.min && still && !busy()) { obs.disconnect(); resolve("quiet"); return; }
  setTimeout(tick, 100);
};
tick();
})"""

_SETTLE_LONG = {"quiet": 1200, "idle": 1000, "min": 600, "max": 20000, "busy": BUSY_SELECTOR}
_SETTLE_SHORT = {"quiet": 350, "idle": 350, "min": 300, "max": 4000, "busy": BUSY_SELECTOR}


class Browser:
    """The headless Chromium behind a session's socket. One page, one
    thread: every request runs to completion before the next is read."""

    def __init__(self, sdir: Path):
        self.sdir = sdir
        self.p = paths(sdir)
        self.sess = load_session(sdir)
        self.origin = _origin(self.sess["base_url"])
        self.shot_n = len(list(self.p["shots"].glob("*.jpg")))
        self.seen_labels: set[str] = set()
        self.min_gap = float(self.sess.get("min_gap_s", MIN_GAP_S))
        self.note_every = int(self.sess.get("note_every", NOTE_EVERY))
        self.budget = int(self.sess.get("moves", DEFAULT_MOVES))
        self.last_reply: float | None = None  # when the player's last answer went out
        self.moves = 0                         # the player's moves the browser made
        self.unnoted = 0                       # acting moves since notes.md last changed
        self.notes_seen = self._notes_sig()

    def start(self) -> None:
        from playwright.sync_api import sync_playwright

        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch()
        self.context = self.browser.new_context(viewport=VIEWPORT, device_scale_factor=1)
        self.page = self.context.new_page()
        self.page.set_default_timeout(15000)
        self.page.on("pageerror", lambda e: self._log_error("pageerror", str(e)))
        self.page.on("console", lambda m: m.type == "error" and self._log_error("console", m.text))
        self.page.on("requestfailed", self._on_failed)
        self.page.on("response", lambda r: r.status >= 500 and self._log_error(
            "http", f"{r.status} {r.request.method} {r.url}"))

    def close(self) -> None:
        with contextlib.suppress(Exception):
            self.browser.close()
        with contextlib.suppress(Exception):
            self.pw.stop()

    def _on_failed(self, req) -> None:
        failure = req.failure or ""
        if "ERR_ABORTED" not in failure:  # a navigation cancelling its own loads
            self._log_error("requestfailed", f"{req.method} {req.url} {failure}")

    def _log_error(self, kind: str, text: str) -> None:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with open(self.p["page_errors"], "a") as f:
            f.write(f"{stamp} {kind}: {' '.join(text.split())[:500]}\n")

    # ---- the page ----

    def _eval(self, js: str, arg=None):
        """Evaluate, riding out a navigation that replaces the page under us."""
        from playwright.sync_api import Error as PlaywrightError

        for attempt in range(3):
            try:
                return self.page.evaluate(js, arg)
            except PlaywrightError as e:
                if attempt == 2 or not re.search(r"context was destroyed|navigat", str(e)):
                    raise
                with contextlib.suppress(PlaywrightError):
                    self.page.wait_for_load_state("load", timeout=15000)
        return None

    def settle(self, long: bool = True) -> str:
        return self._eval(_SETTLE_JS, _SETTLE_LONG if long else _SETTLE_SHORT) or "navigated"

    def observe(self, verb: str, settle: str) -> dict:
        marks = self._eval(_MARKS_JS) or []
        for m in marks:  # a first sighting is drawn orange, for the knowledge check
            key = m.pop("key", None) or m["label"]
            m["new"] = key not in self.seen_labels
            self.seen_labels.add(key)
        self.shot_n += 1
        shot = self.p["shots"] / f"{self.shot_n:03d}-{verb}.jpg"
        self._eval(_OVERLAY_JS, marks)
        try:
            self.page.screenshot(path=str(shot), type="jpeg", quality=80)
        finally:
            self._eval(_UNOVERLAY_JS)
        for m in marks:
            del m["box"]
        return {"shot": str(shot), "n": self.shot_n, "url": self.page.url, "settle": settle,
                "focus": self._eval(_FOCUS_JS), "marks": marks}

    def point(self, target) -> tuple[int, int]:
        if isinstance(target, int):
            pt = self._eval(_POINT_JS, target - 1)
            if pt == "unlooked":
                raise Refusal("there are no numbered tags on this page yet: look first")
            if not pt:
                raise Refusal(f"nothing marked {target} is on the screen now (the page has "
                              "changed); look again")
            return pt[0], pt[1]
        x, y = target
        if not (0 <= x < VIEWPORT["width"] and 0 <= y < VIEWPORT["height"]):
            raise Refusal(f"{x},{y} is outside the window "
                          f"({VIEWPORT['width']}x{VIEWPORT['height']})")
        return x, y

    # ---- the verbs ----

    def handle(self, req: dict) -> dict:
        cmd = req.get("cmd")
        if cmd == "ping":
            return {"ok": True}
        if cmd == "look":
            return self.observe("look", "quiet")
        if cmd == "click":
            x, y = self.point(_target(req["target"]))
            self.page.mouse.click(x, y)
            return self.observe("click", self.settle())
        if cmd == "type":
            focus = self._eval(_FOCUS_JS)
            if not focus["editable"]:
                raise Refusal("nothing that takes typing has focus: click a text field first")
            self.page.keyboard.type(req["text"], delay=8)
            if req.get("enter"):
                self.page.keyboard.press("Enter")
            return self.observe("type", self.settle(long=bool(req.get("enter"))))
        if cmd == "key":
            key = req["key"]
            if not re.fullmatch(r"[A-Za-z0-9+]{1,24}", key):
                raise Refusal(f"not a key name: {key!r} (try Enter, Escape, Tab, ArrowDown)")
            self.page.keyboard.press(key)
            return self.observe("key", self.settle(long=key == "Enter"))
        if cmd == "scroll":
            target = req.get("target")
            x, y = (self.point(_target(target)) if target is not None
                    else (VIEWPORT["width"] // 2, VIEWPORT["height"] // 2))
            px = max(50, min(int(req.get("px") or 400), 3000))
            self.page.mouse.move(x, y)
            self.page.mouse.wheel(0, px if req.get("direction", "down") == "down" else -px)
            self.page.wait_for_timeout(250)
            return self.observe("scroll", self.settle(long=False))
        if cmd == "wait":
            secs = max(1, min(int(req.get("seconds") or 10), MAX_WAIT_S))
            self.page.wait_for_timeout(secs * 1000)
            return self.observe("wait", self.settle(long=False))
        if cmd == "reload":
            self.page.reload(wait_until="load")
            return self.observe("reload", self.settle())
        if cmd == "open":
            url = urljoin(self.sess["base_url"] + "/", req.get("path") or "/")
            if _origin(url) != self.origin:
                raise Refusal(f"this browser only opens the game's own pages ({self.origin})")
            self.page.goto(url, wait_until="load")
            if req.get("internal"):  # setup's page load is not the player's first look
                self.settle(long=False)
                return {"ok": True}
            return self.observe("open", self.settle())
        raise Refusal(f"unknown command {cmd!r}")

    def serve(self) -> None:
        """Answer requests on the socket; between them, keep Playwright's
        event loop turning so page errors are logged as they happen."""
        sp = sock_path(self.sdir)
        with contextlib.suppress(FileNotFoundError):
            sp.unlink()
        srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        srv.bind(str(sp))
        os.chmod(sp, 0o600)
        srv.listen(4)
        srv.settimeout(0.1)
        last = time.monotonic()
        try:
            while time.monotonic() - last < IDLE_EXIT_S:
                try:
                    conn, _ = srv.accept()
                except TimeoutError:
                    with contextlib.suppress(Exception):
                        self.page.wait_for_timeout(50)
                    continue
                last = time.monotonic()
                with conn:
                    if not self._answer(conn):
                        return
        finally:
            srv.close()
            with contextlib.suppress(FileNotFoundError):
                sp.unlink()

    def _answer(self, conn: socket.socket) -> bool:
        conn.settimeout(10)
        buf = b""
        while not buf.endswith(b"\n"):
            chunk = conn.recv(65536)
            if not chunk:
                break
            buf += chunk
        try:
            req = json.loads(buf or b"{}")
        except ValueError:
            req = {}
        if req.get("cmd") == "quit":
            conn.sendall(b'{"ok": true}\n')
            return False
        player = req.get("cmd") in PLAYER_VERBS and not req.get("internal")
        t0 = time.monotonic()
        gate = self.gate(req) if player else None
        if gate:
            resp = {"refused": gate[1], "gate": gate[0]}
        else:
            try:
                resp = self.handle(req)
            except Refusal as e:
                resp = {"refused": str(e)}
            except Exception as e:  # the page broke: say so, keep serving
                resp = {"error": f"{type(e).__name__}: {str(e)[:300]}"}
            if player and "shot" in resp:
                self.moves += 1
                if req["cmd"] in ACTING_VERBS:
                    self.unnoted += 1
                note = self.budget_note()
                if note:
                    resp["note"] = note
        if player:
            entry = {"t": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                     "cmd": req.get("cmd"), "args": {k: v for k, v in req.items() if k != "cmd"},
                     "ms": round((time.monotonic() - t0) * 1000)}
            for k in ("shot", "settle", "refused", "gate", "error"):
                if k in resp:
                    entry[k] = resp[k]
            if "marks" in resp:  # what the screen offered, for the record (never printed)
                entry["marks"] = [m["label"] for m in resp["marks"]]
            with open(self.p["actions"], "a") as f:
                f.write(json.dumps(entry) + "\n")
        conn.sendall(json.dumps(resp).encode() + b"\n")
        if player:
            self.last_reply = time.monotonic()
        return True

    # ---- a person's pace ----

    def _notes_sig(self):
        try:
            st = self.p["notes"].stat()
            return (st.st_size, st.st_mtime_ns)
        except OSError:
            return None

    def gate(self, req: dict) -> tuple[str, str] | None:
        """Why the browser will not make this move yet, if it will not: it
        came sooner than the last screenshot could have been looked at, the
        notes have fallen behind, or the moves are spent."""
        cmd = req["cmd"]
        if self.last_reply is not None and time.monotonic() - self.last_reply < self.min_gap:
            return ("pace", "one move at a time: look at the screenshot from your last move, "
                            "then decide what to do")
        if self.moves >= self.budget + BUDGET_GRACE and cmd != "look":
            return ("budget", "your moves are spent: write your report now")
        if cmd in ACTING_VERBS:
            sig = self._notes_sig()
            if sig != self.notes_seen:
                self.notes_seen, self.unnoted = sig, 0
            if self.unnoted >= self.note_every:
                return ("notes", "your notes have fallen behind: add to notes.md what you did, "
                                 "what the screen showed, how it felt, and your knowledge "
                                 "check, then make this move")
        return None

    def budget_note(self) -> str | None:
        if self.moves >= self.budget:
            return ("your move budget is spent: finish what you are doing, leave the game if "
                    "it offers a way, and write your report")
        if self.moves == int(self.budget * 0.8):
            return ("about a fifth of your moves are left: if you have not yet tried making "
                    "your mark on the game, now is the time")
        return None


def _origin(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.netloc}"


def _target(raw):
    """A mark number (7) or a point ("640,410" or [640, 410])."""
    if isinstance(raw, int):
        return raw
    if isinstance(raw, (list, tuple)) and len(raw) == 2:
        return int(raw[0]), int(raw[1])
    s = str(raw).strip()
    if s.isdigit():
        return int(s)
    m = re.fullmatch(r"(\d+)\s*,\s*(\d+)", s)
    if not m:
        raise Refusal(f"click what? give a mark number (7) or a point (640,410), not {s!r}")
    return int(m.group(1)), int(m.group(2))


def browser_main(sdir: Path) -> int:
    b = Browser(sdir)
    b.start()
    try:
        b.serve()
    finally:
        b.close()
    return 0


# ---- what the player reads ----------------------------------------------------------


def format_response(resp: dict) -> str:
    """What the player reads after a move: where the new screenshot is, and
    the little a browser's own chrome would say. Never what the page holds:
    the labels stay in the log, so the screenshot is the only way to see."""
    if "refused" in resp:
        return f"refused: {resp['refused']}"
    if "error" in resp:
        return f"the browser had a problem: {resp['error']}"
    if "shot" not in resp:
        return "the browser gave no answer (it may have closed)"
    out = [f"shot {resp['n']}: {resp['shot']}",
           "  (Read that image: it is the only way you can see the screen.)",
           f"address bar: {resp['url']}"]
    if resp.get("settle") == "busy":
        out.append("the page still looks busy (something is loading or thinking); "
                   "wait a little and look again")
    focus = resp.get("focus") or {}
    out.append(f"typing goes to: {focus['label']}" if focus.get("editable")
               else "typing goes nowhere (nothing that takes typing has focus)")
    marks = resp.get("marks") or []
    new = sum(1 for m in marks if m.get("new"))
    out.append(f"{len(marks)} numbered tags on the screen"
               + (f", {new} of them orange (things you have not seen before)" if new else ""))
    if resp.get("note"):
        out.append(f"browser: {resp['note']}")
    return "\n".join(out)


def player_request(argv: list[str]) -> dict:
    """Parse a player verb into a browser request."""
    ap = argparse.ArgumentParser(prog="./browser", add_help=True)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("look", help="take a screenshot")
    c = sub.add_parser("click", help="click mark N, or the point X,Y")
    c.add_argument("target")
    t = sub.add_parser("type", help="type into the focused field")
    t.add_argument("text")
    t.add_argument("--enter", action="store_true", help="then press Enter")
    k = sub.add_parser("key", help="press a key: Enter, Escape, Tab, ArrowDown, ...")
    k.add_argument("key")
    s = sub.add_parser("scroll", help="scroll [over mark N or X,Y] up|down")
    s.add_argument("where", nargs="+", help="[N|X,Y] up|down")
    s.add_argument("--px", type=int, default=400)
    w = sub.add_parser("wait", help="let SECONDS pass, then look")
    w.add_argument("seconds", type=int)
    sub.add_parser("reload", help="reload the page")
    o = sub.add_parser("open", help="open a page of the game by its path")
    o.add_argument("path")
    a = ap.parse_args(argv)
    req: dict = {"cmd": a.cmd}
    if a.cmd == "click":
        req["target"] = a.target
    elif a.cmd == "type":
        req.update(text=a.text, enter=a.enter)
    elif a.cmd == "key":
        req["key"] = a.key
    elif a.cmd == "scroll":
        *where, direction = a.where
        if direction not in ("up", "down") or len(where) > 1:
            ap.error("scroll takes [N|X,Y] then up or down")
        req.update(direction=direction, px=a.px)
        if where:
            req["target"] = where[0]
    elif a.cmd == "wait":
        req["seconds"] = a.seconds
    elif a.cmd == "open":
        req["path"] = a.path
    return req


# ---- the command line ----------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["_browser"]:
        return browser_main(Path(argv[1]))
    sdir_arg, as_player = None, False
    while argv and argv[0] in ("--session-dir", "--as-player"):
        if argv[0] == "--as-player":
            as_player = True
            argv = argv[1:]
            break  # everything after it is the player's verb and its arguments
        sdir_arg, argv = Path(argv[1]), argv[2:]
    if as_player or (argv and argv[0] in PLAYER_VERBS):
        if as_player and argv and argv[0] not in PLAYER_VERBS and argv[0] not in ("-h", "--help"):
            print(f"./browser: unknown command {argv[0]!r}; try: {', '.join(PLAYER_VERBS)}",
                  file=sys.stderr)
            return 2
        req = player_request(argv)
        sdir = sdir_arg or current_session_dir()
        timeout = 90 + (req.get("seconds") or 0)
        try:
            resp = send(sdir, req, timeout=timeout)
        except OSError as e:
            print(f"the browser is not answering ({type(e).__name__}); it may have closed",
                  file=sys.stderr)
            return 1
        print(format_response(resp))
        return 1 if ("refused" in resp or "error" in resp) else 0

    ap = argparse.ArgumentParser(prog="bin/game playthrough", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("setup", help="a fresh village, an account, a server and a browser")
    s.add_argument("--name", help='the made-up friend\'s full name (default: invented)')
    s.add_argument("--persona", help="who the player is (default: a cozy-game reader)")
    s.add_argument("--moves", type=int, default=DEFAULT_MOVES, help="browser-command budget")
    s.add_argument("--seed", type=int, help="seed for the invented name and password")
    pl = sub.add_parser("player", help="run the blind player (blocks; run it in the background)")
    pl.add_argument("--model", default=DEFAULT_MODEL)
    sub.add_parser("status", help="the session and the player's latest notes")
    td = sub.add_parser("teardown", help="stop it all; copy the report into playthroughs/")
    td.add_argument("--purge", action="store_true", help="also delete the session's data dir")
    a = ap.parse_args(argv)

    if a.cmd == "setup":
        r = setup(a.name, a.persona, a.moves, a.seed)
        f = r["friend"]
        print(f"session:  {r['id']}  ({r['dir']})")
        print(f"village:  {r['base_url']}  (fresh; art: "
              + (", ".join(f"{n} {k}" for k, n in sorted(r["art"].items())) or "none") + ")")
        print(f"friend:   {f['name']}, signs in as {f['username']} / {f['password']}")
        print(f"player:   {paths(Path(r['dir']))['player']}  (BRIEF.md, ./browser)")
        for note in r["notes"]:
            print(note)
        print("next:     bin/game playthrough player   (in the background)")
        return 0
    sdir = sdir_arg or current_session_dir()
    if a.cmd == "player":
        res = run_player(sdir, a.model)
        r = res.get("result") or {}
        print(f"player finished: exit {res.get('exit')}, {r.get('num_turns', '?')} turns, "
              f"{res.get('minutes')} minutes, {r.get('subtype', 'no result line')}")
        rp = paths(sdir)["report"]  # setup leaves it empty
        print(f"report written: {'yes' if rp.exists() and rp.read_text().strip() else 'NO'}")
        return 0 if res.get("exit") == 0 else 1
    if a.cmd == "status":
        print("\n".join(status(sdir)))
        return 0
    if a.cmd == "teardown":
        r = teardown(sdir, a.purge)
        print(f"report:   {r['report']}"
              + ("" if r["player_report"] else "  (the player wrote none: a stub)"))
        print(f"evidence: {r['extra']}  (notes, shots, actions, page errors)")
        return 0
    return 2


if __name__ == "__main__":
    sys.exit(main())
