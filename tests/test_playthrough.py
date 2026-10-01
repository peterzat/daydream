"""The /playthrough harness (daydream/playthrough.py): a blind player in a
headless browser.

The short tier pins what the player is given and kept from: the sandbox its
`claude -p` runs in, a brief that names nothing of the world, a wrapper that
reaches only the browser verbs, a made-up account the gate accepts, and a
teardown that lands the report in the gitignored folder with its session
record.

The medium tier drives the real browser daemon: against a fixture page, a
mark or a readable word counts only when a person could see it (in the
window, not clipped by a scrolling panel, not hidden or transparent, not
covered); clicks, typing and scrolling act on what was marked; and a full
setup builds a fresh village, signs the made-up friend in through the front
door, and tears down. Skipped cleanly where Chromium is absent."""

from __future__ import annotations

import functools
import http.server
import json
import re
import threading
from pathlib import Path

import pytest

from daydream import accounts, playthrough

ROOT = Path(__file__).resolve().parent.parent
SECTIONS = ("## 1. Overall impression", "## 2. Did I solve it?", "## 3. Surprises (good and bad)",
            "## 4. Dead ends and blockers", "## 5. Suggestions for improvement (clarity, gameplay)",
            "## 6. The puzzles: difficulty, and were they interesting?", "## 7. Making my mark",
            "## 8. Knowledge discrepancies")


@pytest.fixture
def reports(tmp_path, monkeypatch):
    """This test's own reports folder and sessions root."""
    out = tmp_path / "reports"
    monkeypatch.setenv("DAYDREAM_PLAYTHROUGHS_DIR", str(out))
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path / "data"))
    return out


# ---- what the player is given, and kept from (short) --------------------------------


@pytest.mark.tier_short
def test_the_player_runs_sandboxed_to_its_browser_and_its_own_files():
    argv = playthrough.player_argv("opus", "/bin/claude")
    assert argv[:2] == ["/bin/claude", "-p"]
    assert "--restricted" in argv  # no settings files; file tools confined to its folder
    assert "--strict-mcp-config" in argv
    assert argv[argv.index("--permission-mode") + 1] == "dontAsk"
    assert argv[argv.index("--tools") + 1] == "Bash,Read,Write,Edit"
    # writes reach only the two files the brief names (an Edit rule covers Write too)
    assert argv[argv.index("--allowedTools") + 1] == (
        "Bash(./browser *),Edit(./notes.md),Edit(./report.md)")
    for loose in ("--dangerously-skip-permissions", "bypassPermissions", "--add-dir", "--bare"):
        assert loose not in argv


@pytest.mark.tier_short
def test_the_player_inherits_no_keys_and_none_of_daydreams_settings(monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", "/somewhere")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-nope")
    # bin/game exports the project .env and the per-host secrets file: anything there
    monkeypatch.setenv("TYPESAFE_API_KEY", "ts-nope")
    monkeypatch.setenv("MAIL_RELAY_TOKEN", "tok-nope")
    monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")  # the operator's own session
    monkeypatch.setenv("PATH", "/usr/bin")
    monkeypatch.setenv("XDG_RUNTIME_DIR", "/run/user/1000")
    monkeypatch.setenv("LC_ALL", "C.UTF-8")
    env = playthrough.player_env()
    assert env["PATH"] == "/usr/bin" and env["LC_ALL"] == "C.UTF-8"
    assert env["XDG_RUNTIME_DIR"] == "/run/user/1000", "./browser finds its socket there"
    assert not [k for k in env if k.startswith(("DAYDREAM_", "CLAUDE")) or k.endswith("_API_KEY")]
    assert "MAIL_RELAY_TOKEN" not in env


@pytest.mark.tier_short
def test_the_made_up_friend_is_one_the_front_door_accepts():
    import random

    for seed in range(60):
        f = playthrough.make_friend(random.Random(seed))
        assert len(f["name"].split()) == 2
        assert accounts.username_problem(f["username"]) is None
        assert not accounts.reserved_username(f["username"])
        assert accounts.password_problem(f["password"]) is None
    named = playthrough.make_friend(random.Random(1), "Robin Ash")
    assert (named["name"], named["username"]) == ("Robin Ash", "robin")
    assert playthrough.make_friend(random.Random(1), "Al")["username"].startswith("friend")


def _world_names() -> set[str]:
    env = json.loads(playthrough.ENVELOPE.read_text())
    names = {env["world"]["name"]}
    names |= {t["name"] for t in env["toons"]}
    names |= {r.get("title") or r.get("name") or "" for r in env["rooms"]}
    names |= {t.get("name", "") for t in env["things"]}
    return {n for n in names if n}


@pytest.mark.tier_short
def test_the_brief_fills_in_and_names_nothing_of_the_world():
    invite = playthrough.invite_message({"name": "Robin Ash", "username": "robin",
                                         "password": "pw-pw-pw-12"}, "http://127.0.0.1:1/")
    text = playthrough.render_brief(invite=invite, persona="a careful reader", moves=40,
                                    day="2026-10-01")
    assert not re.findall(r"\{[a-z]+\}", text), "an unfilled placeholder"
    for needle in ("http://127.0.0.1:1/", "robin", "pw-pw-pw-12", "a careful reader",
                   "about 40 moves", "Playthrough, 2026-10-01", "notes.md",
                   "report.md", "DISCREPANCY:", "./browser look", "make your mark",
                   "only way you can see", "one move at a time", "orange"):
        assert needle.lower() in text.lower(), needle
    assert "./browser text" not in text, "the screen is the only way to see"
    positions = [text.index(h) for h in SECTIONS]
    assert positions == sorted(positions), "the report's sections, in order"
    low = text.lower()
    leaks = sorted(n for n in _world_names() if re.search(rf"\b{re.escape(n.lower())}\b", low))
    assert not leaks, f"the brief names the world's {leaks}: the player must meet them in play"


@pytest.mark.tier_short
def test_the_wrapper_reaches_the_player_verbs_and_nothing_else(tmp_path, capsys):
    sdir = tmp_path / "a session dir"
    script = playthrough.wrapper_script(sdir)
    assert script.startswith("#!/bin/sh\n")
    assert f"--session-dir '{sdir}' --as-player" in script
    for verb in ("setup", "player", "teardown", "status", "_browser", "text"):
        assert playthrough.main(["--session-dir", str(sdir), "--as-player", verb]) == 2
    assert "unknown command" in capsys.readouterr().err
    # the options end at --as-player: the player's arguments cannot retarget the session
    assert playthrough.main(["--session-dir", str(sdir), "--as-player",
                             "--session-dir", str(tmp_path / "another"), "look"]) == 2
    assert "unknown command '--session-dir'" in capsys.readouterr().err
    assert not sdir.exists()


@pytest.mark.tier_short
def test_player_verbs_parse_to_browser_requests():
    req = playthrough.player_request
    assert req(["look"]) == {"cmd": "look"}
    assert req(["click", "7"]) == {"cmd": "click", "target": "7"}
    assert req(["type", "hello there", "--enter"]) == {"cmd": "type", "text": "hello there",
                                                       "enter": True}
    assert req(["scroll", "down"]) == {"cmd": "scroll", "direction": "down", "px": 400}
    assert req(["scroll", "7", "up", "--px", "800"]) == {"cmd": "scroll", "direction": "up",
                                                         "px": 800, "target": "7"}
    assert req(["wait", "30"]) == {"cmd": "wait", "seconds": 30}
    with pytest.raises(SystemExit):
        req(["scroll", "sideways"])
    assert playthrough._target("7") == 7
    assert playthrough._target("640, 410") == (640, 410)
    with pytest.raises(playthrough.Refusal):
        playthrough._target("the door")


@pytest.mark.tier_short
def test_what_the_player_reads_after_a_move_is_where_the_screen_is():
    """The labels stay in the log: printing them let a player act without
    looking (playthrough 2026-10-01 read 9 of 146 screenshots)."""
    out = playthrough.format_response({
        "shot": "/s/012-click.jpg", "n": 12, "url": "http://127.0.0.1:5/", "settle": "busy",
        "focus": {"editable": True, "label": 'text field showing "speak"'},
        "marks": [{"n": 1, "label": "Talk", "new": True}, {"n": 2, "label": "up", "new": False}],
        "note": "your move budget is spent"})
    assert out.splitlines()[0] == "shot 12: /s/012-click.jpg"
    assert "only way you can see the screen" in out
    assert "still looks busy" in out
    assert 'typing goes to: text field showing "speak"' in out
    assert "2 numbered tags on the screen, 1 of them orange" in out
    assert "browser: your move budget is spent" in out
    assert "Talk" not in out and " up" not in out
    assert playthrough.format_response({"refused": "look first"}) == "refused: look first"
    assert "gave no answer" in playthrough.format_response({})


@pytest.mark.tier_short
def test_a_new_session_id_never_reuses_a_day_and_name(tmp_path, reports):
    root = tmp_path / "sessions"
    (root / "2026-10-01-robin").mkdir(parents=True)
    reports.mkdir()
    (reports / "2026-10-01-robin-2.md").write_text("x")
    assert playthrough.new_session_id(root, "2026-10-01", "robin") == "2026-10-01-robin-3"
    assert playthrough.new_session_id(root, "2026-10-02", "robin") == "2026-10-02-robin"


@pytest.mark.tier_short
def test_the_transcript_result_is_read_from_stream_json(tmp_path):
    t = tmp_path / "player.jsonl"
    t.write_text("\n".join([
        json.dumps({"type": "system", "subtype": "init", "session_id": "abc"}),
        "not json",
        json.dumps({"type": "assistant", "message": {}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/p/shots/001-look.jpg"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/p/shots/001-look.jpg"}},
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/p/notes.md"}},
            {"type": "tool_use", "name": "Bash", "input": {"command": "./browser look"}}]}}),
        json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Read", "input": {"file_path": "/p/shots/002-click.jpg"}}]}}),
        json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 88,
                    "duration_ms": 1000, "total_cost_usd": 4.5})]))
    assert playthrough.transcript_result(t) == {
        "session_id": "abc", "subtype": "success", "is_error": False, "num_turns": 88,
        "duration_ms": 1000, "total_cost_usd": 4.5, "shots_read": 2}
    assert playthrough.transcript_result(tmp_path / "missing") == {}


def _gated(tmp_path, **sess) -> playthrough.Browser:
    sdir = tmp_path / "gated"
    playthrough.paths(sdir)["shots"].mkdir(parents=True)
    playthrough.paths(sdir)["notes"].write_text("# Notes\n")
    playthrough.save_session(sdir, {"id": "gated", "base_url": "http://127.0.0.1:1", **sess})
    return playthrough.Browser(sdir)  # no Chromium: the gates are bookkeeping


@pytest.mark.tier_short
def test_the_browser_keeps_a_persons_pace(tmp_path):
    """A move sooner than the last screenshot could be looked at is refused
    (playthrough 2026-10-01 chained up to eight moves blind per turn)."""
    import time

    b = _gated(tmp_path, min_gap_s=2.0)
    assert b.gate({"cmd": "look"}) is None  # the first move waits on nothing
    b.last_reply = time.monotonic()
    assert b.gate({"cmd": "look"})[0] == "pace"
    assert b.gate({"cmd": "click"})[0] == "pace"
    b.last_reply = time.monotonic() - 2.5
    assert b.gate({"cmd": "click"}) is None


@pytest.mark.tier_short
def test_the_notes_keep_up_with_the_acting_moves(tmp_path):
    b = _gated(tmp_path, min_gap_s=0, note_every=3)
    for _ in range(3):
        assert b.gate({"cmd": "click"}) is None
        b.unnoted += 1  # what a made move adds
    assert b.gate({"cmd": "scroll"}) is None, "looking around needs no note"
    assert b.gate({"cmd": "wait"}) is None
    refused = b.gate({"cmd": "type"})
    assert refused[0] == "notes" and "notes.md" in refused[1]
    with open(b.p["notes"], "a") as f:
        f.write("- shot 4: tried the door. Felt: curious. Knowledge: fine.\n")
    assert b.gate({"cmd": "type"}) is None and b.unnoted == 0


@pytest.mark.tier_short
def test_the_budget_nudges_then_ends_the_session(tmp_path):
    b = _gated(tmp_path, min_gap_s=0, note_every=99, moves=10)
    b.moves = 7
    assert b.budget_note() is None
    b.moves = 8
    assert "your mark" in b.budget_note()
    b.moves = 10
    assert "spent" in b.budget_note()
    assert b.gate({"cmd": "click"}) is None, "a little grace to wrap up"
    b.moves = 10 + playthrough.BUDGET_GRACE
    assert b.gate({"cmd": "click"})[0] == "budget"
    assert b.gate({"cmd": "look"}) is None, "a last look is always allowed"


def _fake_session(sid: str, report: str | None) -> Path:
    sdir = playthrough.sessions_root() / sid
    p = playthrough.paths(sdir)
    p["shots"].mkdir(parents=True)
    playthrough.save_session(sdir, {
        "id": sid, "base_url": "http://127.0.0.1:1", "envelope": "worlds/lost-hours.json",
        "build": "abc123", "art": {"copied": 30, "missing": 2},
        "friend": {"name": "Robin Ash", "username": "robin", "password": "x"},
        "player": {"model": "opus", "minutes": 41.5,
                   "result": {"subtype": "success", "num_turns": 210, "total_cost_usd": 12.3,
                              "shots_read": 2}}})
    p["actions"].write_text(
        json.dumps({"t": "2026-10-01T00:00:00+00:00", "cmd": "look", "shot": "1"}) + "\n"
        + json.dumps({"t": "2026-10-01T00:00:01+00:00", "cmd": "click", "refused": "x",
                      "gate": "pace"}) + "\n"
        + json.dumps({"t": "2026-10-01T00:40:00+00:00", "cmd": "click", "shot": "2"}) + "\n"
        + json.dumps({"t": "2026-10-01T00:41:00+00:00", "cmd": "click", "shot": "3"}) + "\n")
    p["page_errors"].write_text("2026-10-01T00:05:00+00:00 pageerror: boom\n")
    p["server_log"].write_text("INFO fine\n2026 x ERROR daydream.ws: oops\nTraceback (most recent)\n")
    p["notes"].write_text("# Notes\n\nmove 1\n")
    (p["shots"] / "001-look.jpg").write_bytes(b"\xff\xd8")
    if report is not None:
        p["report"].write_text(report)
    (playthrough.sessions_root() / "current").write_text(sid + "\n")
    return sdir


@pytest.mark.tier_short
def test_teardown_lands_the_report_with_its_session_record(reports):
    sdir = _fake_session("2026-10-01-robin", "# Playthrough, 2026-10-01: Wren\n\n## 1. Overall impression\n\nlovely\n")
    r = playthrough.teardown(sdir)
    assert r["player_report"] is True
    text = (reports / "2026-10-01-robin.md").read_text()
    assert text.startswith("# Playthrough, 2026-10-01: Wren")
    record = text[text.index("## Session record"):]
    assert "Moves: 3 (click 2, look 1) over 41 minutes" in record
    assert "Screenshots the player opened: 2 of 3" in record
    assert "Moves the browser refused: pace 1" in record
    assert "210 turns, 41.5 minutes, ended success, $12.30 equivalent" in record
    assert "Page errors and failed requests: 1" in record and "pageerror: boom" in record
    assert "Server log errors: 2" in record
    assert "art copied from dev: 30 copied, 2 missing" in record
    evidence = reports / "2026-10-01-robin"
    assert (evidence / "notes.md").exists() and (evidence / "shots" / "001-look.jpg").exists()
    assert (evidence / "actions.log").exists() and (evidence / "page-errors.log").exists()
    assert not (playthrough.sessions_root() / "current").exists()
    assert sdir.exists()  # kept unless purged


@pytest.mark.tier_short
def test_teardown_without_a_report_says_so_and_purge_removes_the_village(reports):
    sdir = _fake_session("2026-10-01-ines", None)
    r = playthrough.teardown(sdir, purge=True)
    assert r["player_report"] is False
    assert "wrote no report.md" in (reports / "2026-10-01-ines.md").read_text()
    assert not sdir.exists()


@pytest.mark.tier_short
def test_the_reports_stay_local_and_the_skill_names_real_verbs():
    assert "/playthroughs/" in (ROOT / ".gitignore").read_text().splitlines()
    skill = (ROOT / ".claude" / "skills" / "playthrough" / "SKILL.md").read_text()
    assert skill.startswith("---\nname: playthrough\n")
    named = set(re.findall(r"bin/game playthrough ([a-z_]+)", skill))
    assert {"setup", "player", "status", "teardown"} <= named
    for verb in named:
        with pytest.raises(SystemExit) as e:
            playthrough.main([verb, "--help"])
        assert e.value.code == 0, verb


# ---- the browser (medium) -----------------------------------------------------------


@pytest.mark.tier_medium
def test_the_wrapper_never_runs_a_file_planted_beside_it(tmp_path):
    """./browser runs from the player's folder, where the player writes: its
    Python imports nothing from there (python -I), whatever is planted."""
    import subprocess

    folder = tmp_path / "player"
    (folder / "daydream").mkdir(parents=True)
    ran = tmp_path / "planted-ran"
    plant = f"open({str(ran)!r}, 'a').write(__name__ + '\\n')\n"
    for planted in (folder / "json.py", folder / "daydream" / "__init__.py"):
        planted.write_text(plant)
    wrapper = folder / "browser"
    wrapper.write_text(playthrough.wrapper_script(tmp_path / "no session"))
    wrapper.chmod(0o755)
    r = subprocess.run(["./browser", "look"], cwd=folder, env=playthrough.player_env(),
                       capture_output=True, text=True, timeout=60)
    assert not ran.exists(), f"a planted module ran: {ran.read_text().split()}"
    assert r.returncode == 1 and "the browser is not answering" in r.stderr, r.stderr


FIXTURE ="""<!doctype html><html><head><meta charset="utf-8"><style>
body { margin: 0; font: 16px sans-serif; }
.ptr { cursor: pointer; }
#cover { position: absolute; left: 400px; top: 100px; width: 320px; height: 140px;
         background: #fff; z-index: 5; }
#under { position: absolute; left: 420px; top: 120px; }
#scroller { position: absolute; left: 20px; top: 320px; width: 300px; height: 110px;
            overflow: auto; border: 1px solid #000; }
#far { position: absolute; top: 1400px; }
#pressme { position: absolute; left: 820px; top: 40px; width: 160px; height: 30px; }
</style></head><body>
<p>Visible paragraph words</p>
<button id="pressme" onclick="this.textContent = 'Pressed itself'">Visible button</button>
<div class="ptr" onclick="document.getElementById('pressme').textContent = 'Pressed by the chip'"><span>Pointer</span><span>chip</span></div>
<label for="name">Name</label> <input id="name">
<p id="out"></p>
<button style="display: none">Hidden by display</button>
<button style="visibility: hidden">Hidden by visibility</button>
<button style="opacity: 0">Hidden by opacity</button>
<div id="under"><button>Covered button</button><p>Covered words</p></div>
<div id="cover">a plain card on top</div>
<div id="scroller"><p>Top of the scroller</p><div style="height: 300px"></div>
  <p>Deep in the scroller</p><button>Deep button</button></div>
<div id="far"><p>Below the fold words</p><button>Below button</button></div>
</body></html>"""


@pytest.fixture(scope="module")
def chromium_here():
    sync_api = pytest.importorskip("playwright.sync_api")
    try:
        pw = sync_api.sync_playwright().start()
    except Exception as e:
        pytest.skip(f"playwright driver unavailable: {e}")
    try:
        pw.chromium.launch().close()
    except Exception as e:
        pytest.skip(f"headless Chromium unavailable: {e}")
    finally:
        pw.stop()


@pytest.fixture
def fixture_site(tmp_path):
    site = tmp_path / "site"
    site.mkdir()
    (site / "index.html").write_text(FIXTURE)
    handler = functools.partial(_QuietHandler, directory=str(site))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@pytest.fixture
def browser_session(chromium_here, fixture_site, tmp_path):
    sdir = tmp_path / "s"
    playthrough.paths(sdir)["shots"].mkdir(parents=True)
    playthrough.save_session(sdir, {"id": "fixture", "base_url": fixture_site,
                                    "min_gap_s": 0, "note_every": 99})
    pid = playthrough.start_browser(sdir)
    try:
        yield sdir
    finally:
        try:
            playthrough.send(sdir, {"cmd": "quit"}, timeout=10)
        except OSError:
            pass
        playthrough._stop(pid)


def _labels(resp: dict) -> list[str]:
    return [m["label"] for m in resp["marks"]]


def _mark(resp: dict, label: str) -> int:
    return next(m["n"] for m in resp["marks"] if m["label"] == label)


@pytest.mark.tier_medium
def test_only_what_a_person_could_see_is_marked_or_read(browser_session):
    send = functools.partial(playthrough.send, browser_session)
    first = send({"cmd": "open", "path": "/"})
    labels = _labels(first)
    assert {"Visible button", "Pointer chip", 'text field "Name"'} <= set(labels)
    for hidden in ("Hidden by display", "Hidden by visibility", "Hidden by opacity",
                   "Covered button", "Deep button", "Below button"):
        assert hidden not in labels, hidden
    assert all(m["new"] for m in first["marks"]), "everything is new on a first look (orange)"
    assert Path(first["shot"]).exists() and first["shot"].endswith("001-open.jpg")
    again = send({"cmd": "look"})
    assert _labels(again) == labels, "the tags never stay on the page to be marked themselves"
    assert not any(m["new"] for m in again["marks"])


@pytest.mark.tier_medium
def test_clicks_typing_and_scrolling_act_on_what_was_marked(browser_session):
    send = functools.partial(playthrough.send, browser_session)
    assert "look first" in send({"cmd": "click", "target": "1"})["refused"]
    page = send({"cmd": "open", "path": "/"})
    chipped = send({"cmd": "click", "target": str(_mark(page, "Pointer chip"))})
    assert "Pressed by the chip" in _labels(chipped)
    assert next(m for m in chipped["marks"] if m["label"] == "Pressed by the chip")["new"]
    assert "click a text field first" in send({"cmd": "type", "text": "Ada"})["refused"]
    send({"cmd": "click", "target": str(_mark(page, 'text field "Name"'))})
    typed = send({"cmd": "type", "text": "Ada"})
    assert typed["focus"] == {"editable": True, "label": 'text field "Name" containing "Ada"'}
    field = next(m for m in typed["marks"] if m["label"].startswith('text field "Name"'))
    assert field["new"] is False, "a field is the same thing whatever is typed in it"
    pressed = send({"cmd": "click", "target": "900,55"})  # the button, by its point
    assert "Pressed itself" in _labels(pressed)
    assert pressed["n"] == 5
    scrolled = send({"cmd": "scroll", "target": "170,370", "direction": "down", "px": 400})
    assert "Deep button" in _labels(scrolled)
    assert "only opens the game's own pages" in send({"cmd": "open",
                                                      "path": "http://example.com/"})["refused"]
    assert "outside the window" in send({"cmd": "click", "target": "5000,5"})["refused"]
    log = [json.loads(ln) for ln in playthrough.paths(browser_session)["actions"]
           .read_text().splitlines()]
    assert [e["cmd"] for e in log][:3] == ["click", "open", "click"]
    assert all("ms" in e for e in log)
    entry = next(e for e in log if e.get("shot") == pressed["shot"])
    assert "Pressed itself" in entry["marks"], "the log keeps what the screen offered"


@pytest.mark.tier_medium
def test_setup_builds_a_fresh_village_the_friend_can_sign_into(chromium_here, reports,
                                                               monkeypatch):
    # The engines point nowhere: nothing in this test may reach the box's GPU.
    monkeypatch.setenv("DAYDREAM_LLM_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("DAYDREAM_COMFYUI_BASE_URL", "http://127.0.0.1:9")
    r = playthrough.setup(name="Robin Ash", moves=20, seed=3, min_gap_s=0, note_every=99)
    sdir = Path(r["dir"])
    try:
        p = playthrough.paths(sdir)
        assert re.fullmatch(r"\d{4}-\d\d-\d\d-robin", r["id"])
        assert r["friend"]["username"] == "robin"
        assert any("vLLM is not answering" in n for n in r["notes"])
        brief = p["brief"].read_text()
        assert r["base_url"] in brief and r["friend"]["password"] in brief
        assert (p["wrapper"].stat().st_mode & 0o111) and "--as-player" in p["wrapper"].read_text()
        assert p["notes"].exists() and p["report"].read_text() == "", "the player only edits"
        send = functools.partial(playthrough.send, sdir)
        door = send({"cmd": "look"})
        assert door["n"] == 1, "setup's own page load is not the player's first look"
        send({"cmd": "click", "target": str(_mark(door, 'text field "username"'))})
        send({"cmd": "type", "text": "robin"})
        tabbed = send({"cmd": "key", "key": "Tab"})
        assert tabbed["focus"]["label"] == 'password field "password"'
        inside = send({"cmd": "type", "text": r["friend"]["password"], "enter": True})
        assert 'password field "password"' not in _labels(inside), "still at the door"
        assert playthrough.status(sdir)[0].startswith(f"session: {r['id']}")
    finally:
        out = playthrough.teardown(sdir, purge=True)
    assert Path(out["report"]).exists()
    assert not sdir.exists()
