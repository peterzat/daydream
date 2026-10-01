"""Instances (docs/INSTANCES.md): several games behind one door, each a
complete data dir, one attached at a time, swapped with everything kept.

The operator's ask (2026-09-28): swap prod between the village and a Zork
playthrough (invite a friend, let them play, go back), preserving every
instance's accounts, world and art, from the same URL; the beginning of
multi-tenancy."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from daydream import accounts, config, db, events, instance

pytestmark = pytest.mark.tier_medium

ROOT = Path(__file__).resolve().parent.parent
PW = "a-long-enough-password"
ZORK_WORDS = {"title": "The Old Empire", "place": "the old empire", "operator": "the Keeper",
              "lede": "An old underground empire, kept for friends.",
              "invite_blurb": "an old text adventure I keep for friends"}


@pytest.fixture(autouse=True)
def box(tmp_path: Path, monkeypatch):
    """A scratch data root, fresh resolution caches, nothing open."""
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    monkeypatch.delenv("DAYDREAM_INSTANCE", raising=False)
    config.forget_data_dir()
    instance.forget()
    db.close_db()
    accounts.close()
    events.reset_subscribers()
    yield tmp_path
    db.close_db()
    accounts.close()
    events.reset_subscribers()
    config.forget_data_dir()
    instance.forget()


def _fresh() -> None:
    config.forget_data_dir()
    instance.forget()


# ---- which data dir ----------------------------------------------------------


def test_a_box_without_instances_is_its_own_data_dir(box):
    assert config.data_dir() == box
    assert instance.load() == instance.DEFAULTS
    assert config.cookie_name() == "dd_session_dev"


def test_the_active_link_and_the_instance_setting_pick_the_dir(box, monkeypatch):
    instance.create("village", {})
    instance.create("zork", ZORK_WORDS)
    instance.attach("village")
    _fresh()
    assert config.data_dir() == box / "instances" / "village"
    assert config.cookie_name() == "dd_session_dev_village"
    monkeypatch.setenv("DAYDREAM_INSTANCE", "zork")
    _fresh()
    assert config.data_dir() == box / "instances" / "zork"
    assert config.cookie_name() == "dd_session_dev_zork"
    assert config.operator_name() == "the Keeper"
    monkeypatch.setenv("DAYDREAM_INSTANCE", "../etc")
    _fresh()
    with pytest.raises(ValueError):
        config.data_dir()


def test_a_process_keeps_the_instance_it_resolved(box):
    """A swap under a running server would split it; the resolution is once
    per process, so a flip takes effect only on the next start."""
    instance.create("village", {})
    instance.create("zork", ZORK_WORDS)
    instance.attach("village")
    _fresh()
    first = config.data_dir()
    instance.attach("zork")
    assert config.data_dir() == first
    config.forget_data_dir()
    assert config.data_dir() == box / "instances" / "zork"


# ---- the words -----------------------------------------------------------------


def test_the_words_default_to_the_village_and_refuse_what_could_point_anywhere():
    assert instance.validate({})["place"] == "the village"
    assert instance.validate({"place": "the old empire"})["place"] == "the old empire"
    for bad in ({"door_image": "../../etc/passwd"}, {"door_image": "https://x/y.png"},
                {"envelope": "/etc/hosts"}, {"envelope": "worlds/../x.json"},
                {"place": 3}, {"colour": "red"}, {"name": "Not A Name"},
                {"place": "line\nbreak"}, {"card_image": "https://x/y.png"},
                {"card_image": "assets/card.webp"}):
        with pytest.raises(instance.InstanceError):
            instance.validate(bad)


def test_a_link_preview_card_follows_the_instances_own_door():
    """An instance that paints its own door and makes no card previews with
    its door, never the village's card."""
    assert instance.validate({})["card_image"] == "assets/card-village.jpg"
    zork = instance.validate({"door_image": "assets/door-zork.png"})
    assert zork["card_image"] == "assets/door-zork.png"
    both = instance.validate({"door_image": "assets/door-zork.png",
                              "card_image": "assets/card-zork.jpg"})
    assert both["card_image"] == "assets/card-zork.jpg"


def test_the_envelope_is_the_instances_own(box, capsys):
    instance.create("zork", {**ZORK_WORDS, "envelope": "worlds/zork1.json"})
    instance.attach("zork")
    _fresh()
    assert instance.main(["envelope"]) == 0
    assert capsys.readouterr().out.strip() == "worlds/zork1.json"
    script = (ROOT / "bin" / "game").read_text()
    reset = script[script.index("cmd_world_reset() {"):]
    assert '"$VENV_PY" -m daydream.instance envelope' in reset[:reset.index("\n}\n")]
    refresh = (ROOT / "daydream" / "refresh.py").read_text()
    assert 'instance.load()["envelope"]' in refresh


def test_the_invite_message_speaks_for_the_instance(box):
    from daydream import accounts_cli

    instance.create("zork", ZORK_WORDS)
    instance.attach("zork")
    _fresh()
    msg = accounts_cli.invite_message("Juno Vale", "https://x/invite/a-b", "2026-10-12T00:00:00Z")
    assert "an old text adventure I keep for friends" in msg and "(I'm the Keeper)" in msg
    assert "village" not in msg


# ---- the pages -------------------------------------------------------------------


def _load_world(d: Path) -> None:
    from daydream.llm import bootstrap

    env = json.loads((ROOT / "worlds" / "lost-hours.json").read_text())
    live = d / "worlds-dev" / "live.db"
    live.parent.mkdir(parents=True, exist_ok=True)
    bootstrap.load_world("lost hours", env, live)
    db.close_db()


def test_the_door_and_the_game_speak_the_instances_words_escaped(box):
    instance.create("zork", {**ZORK_WORDS, "place": "the <old> empire"})
    instance.attach("zork")
    _fresh()
    _load_world(instance.instances_root() / "zork")
    with TestClient(app()) as client:
        door = client.get("/login").text
        assert "An old underground empire, kept for friends." in door
        assert 'data-place="the &lt;old&gt; empire"' in door
        assert "{{" not in door
        accounts.create_account("admin-one", PW, role="admin")
        assert client.post("/api/login", json={"username": "admin-one", "password": PW}).status_code == 200
        game = client.get("/").text
        assert "Who will you be in the &lt;old&gt; empire?" in game and "{{" not in game
        assert "instance: zork" in client.get("/status/build").text


def test_without_instance_json_the_pages_read_exactly_as_before(box):
    _load_world(box)
    with TestClient(app()) as client:
        door = client.get("/login").text
    assert "A small storybook village, kept for friends." in door
    assert 'src="assets/door-village.png"' in door


def app():
    from daydream.server import app as the_app

    return the_app


# ---- create, attach, migrate --------------------------------------------------------


def test_migrate_moves_a_flat_data_dir_into_one_instance(box):
    (box / "worlds-dev").mkdir()
    (box / "worlds-dev" / "live.db").write_text("a world")
    (box / "accounts-dev.db").write_text("accounts")
    (box / "keep").mkdir()
    (box / "gpu.lock").write_text("")
    (box / ".local").mkdir()
    moved = instance.migrate("village")
    assert sorted(moved) == ["accounts-dev.db", "keep", "worlds-dev"]
    assert (box / "gpu.lock").exists() and (box / ".local").is_dir()
    assert (box / "instances" / "village" / "worlds-dev" / "live.db").read_text() == "a world"
    assert instance.attached() == "village"
    assert json.loads((box / "instances" / "village" / "instance.json").read_text()) == {
        "name": "village"}
    with pytest.raises(instance.InstanceError):
        instance.migrate("again")


def test_attach_refuses_an_unknown_instance_and_create_an_existing_one(box):
    instance.create("village", {})
    with pytest.raises(instance.InstanceError):
        instance.attach("nowhere")
    with pytest.raises(FileExistsError):
        instance.create("village", {})
    instance.attach("village")
    assert [r["name"] for r in instance.listing()] == ["village"]
    assert instance.listing()[0]["attached"] is True


# ---- a swap, rehearsed for real (in-process servers, one instance at a time) ----


def test_a_swap_keeps_each_instances_accounts_world_and_sessions(box):
    for name, words in (("village", {}), ("zork", ZORK_WORDS)):
        instance.create(name, words)
        _load_world(instance.instances_root() / name)

    def serve():
        _fresh()
        db.close_db()
        accounts.close()
        events.reset_subscribers()
        return TestClient(app())

    instance.attach("village")
    with serve() as client:
        accounts.create_account("robin", PW)
        assert client.post("/api/login", json={"username": "robin", "password": PW}).status_code == 200
        village_cookie = client.cookies.get("dd_session_dev_village")
        assert village_cookie
        assert client.post("/api/dreamer/create", json={
            "name": "Robin", "appearance_seed": "a small wren"}).status_code == 200

    instance.attach("zork")
    with serve() as client:
        assert client.post("/api/login", json={"username": "robin", "password": PW}).status_code == 401
        accounts.create_account("juno", PW)
        assert client.post("/api/login", json={"username": "juno", "password": PW}).status_code == 200
        assert client.get("/api/dreamer").json()["toons"] == []

    instance.attach("village")
    with serve() as client:
        client.cookies.set("dd_session_dev_village", village_cookie)
        me = client.get("/api/me")
        assert me.status_code == 200 and me.json()["username"] == "robin"  # still signed in
        assert [t["name"] for t in client.get("/api/dreamer").json()["toons"]] == ["Robin"]
        assert accounts.get_account("juno") is None  # Juno lives only in the other one


# ---- the prod swap's order and its rollback (systemd and the edge faked) ----


@pytest.fixture
def prodbox(tmp_path, monkeypatch):
    from daydream import prodctl

    srv = tmp_path / "srv"
    data = srv / "data"
    (srv / "etc").mkdir(parents=True)
    (srv / "etc" / "prod.env").write_text(f"DAYDREAM_ENV=prod\nDAYDREAM_DATA_DIR={data}\n")
    rel = srv / "releases" / "aaaaaaaaaaaa"
    rel.mkdir(parents=True)
    monkeypatch.setattr(prodctl, "SRV", srv)
    prodctl.point("current", rel)
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(data))
    data.mkdir()
    for name in ("village", "zork"):
        instance.create(name, {})
    instance.attach("village")
    calls: list = []

    def fake_python(rel, args, check=True, capture=False, data=None, **k):
        calls.append(("python", tuple(args), data.name if data else None))
        if args[:2] == ["-m", "daydream.instance"] and args[2] == "attach":
            instance.attach(args[3])
        if args[:3] == ["-m", "daydream.instance", "flag-words"]:
            return subprocess.CompletedProcess(args, 0, stdout=json.dumps(
                {"place": "the village", "title": "t", "operator": "o", "cookie": "dd_session_x"}))
        if args[:3] == ["-m", "daydream.admin", "preflight"]:
            return subprocess.CompletedProcess(args, 0, stdout=(
                "code_world_version: 1.5\nworld_migrations_pending: 0\n"
                "live_world: w-lost-hours 1.5\naccounts_migrations_pending: 0\n"), stderr="")
        return subprocess.CompletedProcess(args, 0, stdout="ok", stderr="")

    monkeypatch.setattr(prodctl, "run_release_python", fake_python)
    monkeypatch.setattr(prodctl, "unit_active", lambda unit: True)
    monkeypatch.setattr(prodctl, "systemctl", lambda a, u: calls.append((a, u)))
    monkeypatch.setattr(prodctl, "wait_healthy", lambda seconds=45.0: True)
    monkeypatch.setattr(prodctl, "_edge", lambda: None)
    monkeypatch.setattr(prodctl.time, "sleep", lambda s: None)
    return prodctl, data, calls


def test_the_swap_backs_up_both_stops_attaches_and_checks_what_answers(prodbox, monkeypatch):
    prodctl, data, calls = prodbox
    monkeypatch.setattr(prodctl, "served_instance", lambda rel: "zork")
    assert prodctl.instance_use("zork", grace=0, note="") == 0
    assert (data / "active").resolve().name == "zork"
    steps = [c[1][2] if c[0] == "python" else c[0] for c in calls]
    assert steps.index("preflight") < steps.index("stop") < steps.index("attach") < steps.index("start")
    backups = [c[2] for c in calls if c[0] == "python" and c[1][2] == "backup"]
    assert sorted(backups) == ["village", "zork"]


def test_a_swap_whose_target_does_not_answer_goes_back(prodbox, monkeypatch):
    prodctl, data, calls = prodbox
    monkeypatch.setattr(prodctl, "served_instance", lambda rel: "village")
    with pytest.raises(prodctl.ProdError):
        prodctl.instance_use("zork", grace=0, note="")
    assert (data / "active").resolve().name == "village"
    assert ("restart", prodctl.UNIT) in calls


def test_a_swap_to_an_instance_with_no_world_is_refused_before_anything_stops(prodbox,
                                                                             monkeypatch):
    """Codereview WARN 2026-09-28e: a world-less target boots on an empty data
    dir and answers as itself, so the served check alone would pass."""
    prodctl, data, calls = prodbox
    fake = prodctl.run_release_python

    def no_world(rel, args, **k):
        if args[:3] == ["-m", "daydream.admin", "preflight"]:
            calls.append(("python", tuple(args), k["data"].name))
            return subprocess.CompletedProcess(args, 0, stdout=(
                "code_world_version: 1.5\nlive_world: missing\naccounts: missing\n"), stderr="")
        return fake(rel, args, **k)

    monkeypatch.setattr(prodctl, "run_release_python", no_world)
    monkeypatch.setattr(prodctl, "served_instance", lambda rel: "zork")
    with pytest.raises(prodctl.ProdError, match="no world to serve"):
        prodctl.instance_use("zork", grace=0, note="")
    assert (data / "active").resolve().name == "village"
    assert [c for c in calls if c[0] != "python"] == []  # nothing stopped or started
    assert not [c for c in calls if c[0] == "python" and c[1][2] == "backup"]


def test_a_create_whose_world_does_not_load_leaves_nothing_behind(prodbox, monkeypatch):
    """Codereview WARN 2026-09-28e: the new dir is discarded, so a retry with
    a good envelope does not fail on "File exists"."""
    prodctl, data, calls = prodbox
    loads = []

    def real_instance_cli(rel, args, check=True, capture=False, data=None, **k):
        if args[:2] == ["-m", "daydream.instance"]:
            return subprocess.CompletedProcess(args, instance.main(list(args[2:])), "", "")
        if args[:3] == ["-m", "daydream.admin", "load"]:
            loads.append(args[3])
            if args[3].endswith("nope.json"):
                return subprocess.CompletedProcess(args, 2, "", "error: envelope not found")
            out = Path(args[args.index("--output") + 1])
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text("a world")
        return subprocess.CompletedProcess(args, 0, "loaded", "")

    monkeypatch.setattr(prodctl, "run_release_python", real_instance_cli)
    with pytest.raises(prodctl.ProdError, match="removed, so a retry starts clean"):
        prodctl.instance_create("empire", {"envelope": "worlds/nope.json"})
    assert not (data / "instances" / "empire").exists()
    assert prodctl.instance_create("empire", {"envelope": "worlds/zork1.json"}) == 0
    assert (data / "instances" / "empire" / "worlds-prod" / "live.db").exists()
    assert len(loads) == 2


def test_discard_removes_only_an_empty_detached_instance(box):
    instance.create("village", {})
    instance.create("zork", ZORK_WORDS)
    instance.create("empty", {})
    instance.attach("village")
    (box / "instances" / "zork" / "worlds-dev").mkdir()
    (box / "instances" / "zork" / "worlds-dev" / "live.db").write_text("a world")
    for name in ("village", "zork", "nowhere", "../x"):
        with pytest.raises(instance.InstanceError):
            instance.discard(name)
    instance.discard("empty")
    assert sorted(p.name for p in (box / "instances").iterdir()) == ["village", "zork"]


def test_a_stop_for_verb_on_a_detached_instance_leaves_the_service_up(prodbox, monkeypatch):
    """Codereview WARN 2026-09-28e: `world refresh --instance zork` stopped
    the village's service for nothing."""
    prodctl, data, calls = prodbox
    ran = []
    monkeypatch.setattr(prodctl.subprocess, "run",
                        lambda cmd, **k: ran.append(cmd) or subprocess.CompletedProcess(cmd, 0))
    monkeypatch.setattr(prodctl, "INSTANCE", "zork")
    assert prodctl.passthrough(["world", "refresh"]) == 0
    assert [c for c in calls if c[0] in ("stop", "start")] == [] and len(ran) == 1
    monkeypatch.setattr(prodctl, "INSTANCE", "village")  # the attached one: stopped around it
    assert prodctl.passthrough(["world", "refresh"]) == 0
    assert [c for c in calls if c[0] in ("stop", "start")] == [("stop", prodctl.UNIT),
                                                               ("start", prodctl.UNIT)]


def test_an_instances_name_is_its_directorys(box, monkeypatch):
    """Codereview WARN 2026-09-28e: a nameless instance.json under
    instances/zork shared the plain cookie, said "-" on /status/build, and
    failed every swap's served check. A file may omit the name, never
    contradict it."""
    d = box / "instances" / "zork"
    d.mkdir(parents=True)
    (d / "instance.json").write_text(json.dumps({"title": "Zork I"}))
    assert instance.name(d) == "zork"
    monkeypatch.setenv("DAYDREAM_INSTANCE", "zork")
    _fresh()
    assert config.cookie_name() == "dd_session_dev_zork"
    (d / "instance.json").write_text(json.dumps({"name": "village"}))
    _fresh()
    with pytest.raises(instance.InstanceError, match="not its directory's"):
        instance.load(d)
    empty = box / "instances" / "empty"
    empty.mkdir()
    assert instance.name(empty) == "empty"  # no file at all: still its directory's


def test_migrate_names_an_existing_instance_json_and_refuses_a_bad_one_first(box, monkeypatch):
    (box / "instance.json").write_text(json.dumps({"title": "Zork I"}))
    (box / "accounts-dev.db").write_text("accounts")
    instance.migrate("zork")
    assert json.loads((box / "instances" / "zork" / "instance.json").read_text()) == {
        "title": "Zork I", "name": "zork"}
    other = box / "other"  # a second flat data dir, with a bad instance.json
    other.mkdir()
    (other / "instance.json").write_text(json.dumps({"colour": "red"}))
    (other / "accounts-dev.db").write_text("accounts")
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(other))
    _fresh()
    with pytest.raises(instance.InstanceError):
        instance.migrate("village")
    assert (other / "accounts-dev.db").exists() and not (other / "instances").exists()


class _FlagEdge:
    """The edge module's surface prodctl uses, with the flag asleep on a note."""
    EdgeError = RuntimeError

    def __init__(self):
        self.flags = []

    def get_state(self):
        return {"state": "asleep", "note": "back Sunday"}

    def set_state(self, state, note="", words=None):
        self.flags.append((state, note))

    def sync_keepsakes(self, rel):
        pass


def test_a_swap_keeps_the_flags_note_unless_given_one(prodbox, monkeypatch):
    """Codereview WARN 2026-09-28e: `instance use` wrote note "" and erased
    an asleep note."""
    prodctl, data, calls = prodbox
    edge = _FlagEdge()
    monkeypatch.setattr(prodctl, "_edge", lambda: edge)
    monkeypatch.setattr(prodctl, "served_instance", lambda rel: "zork")
    assert prodctl.main(["instance", "use", "zork"]) == 0
    monkeypatch.setattr(prodctl, "served_instance", lambda rel: "village")
    assert prodctl.main(["instance", "use", "village", "--note", "a game night"]) == 0
    assert edge.flags == [("asleep", None), ("asleep", "a game night")]


def test_migrate_keeps_the_flags_note(tmp_path, monkeypatch):
    from daydream import prodctl

    srv, data = tmp_path / "srv", tmp_path / "srv" / "data"
    (srv / "etc").mkdir(parents=True)
    (srv / "etc" / "prod.env").write_text(f"DAYDREAM_ENV=prod\nDAYDREAM_DATA_DIR={data}\n")
    rel = srv / "releases" / "aaaaaaaaaaaa"
    rel.mkdir(parents=True)
    monkeypatch.setattr(prodctl, "SRV", srv)
    prodctl.point("current", rel)
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(data))
    data.mkdir()
    (data / "accounts-prod.db").write_text("accounts")

    def fake_python(rel, args, check=True, capture=False, data=None, **k):
        if args[:3] == ["-m", "daydream.instance", "migrate"]:
            return subprocess.CompletedProcess(args, instance.main(list(args[2:])), "", "")
        return subprocess.CompletedProcess(args, 0, stdout="{}", stderr="")

    edge = _FlagEdge()
    monkeypatch.setattr(prodctl, "run_release_python", fake_python)
    monkeypatch.setattr(prodctl, "unit_active", lambda unit: False)
    monkeypatch.setattr(prodctl, "_edge", lambda: edge)
    assert prodctl.instance_migrate("village") == 0
    assert (data / "active").resolve().name == "village"
    assert edge.flags == [("asleep", None)]
