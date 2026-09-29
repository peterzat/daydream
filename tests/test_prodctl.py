"""`bin/game prod` orchestration (SPEC 2026-09-27 criteria 10-12): the clean
prod environment, immutable releases, the atomic switch, automatic rollback,
and pruning. Systemd, health and the test run are faked; releases are built
for real from this repo into a temporary /srv/daydream."""

import hashlib
import os
import sys
from pathlib import Path

import pytest

from daydream import prodctl

pytestmark = pytest.mark.tier_medium

REPO = Path(__file__).resolve().parent.parent


def _git(repo, *args):
    import subprocess

    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True,
                   env={**os.environ, "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@t",
                        "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@t"})


@pytest.fixture
def fake_repo(tmp_path, monkeypatch):
    """A tiny committed project to build releases from, so these tests never
    depend on what this repo's HEAD happens to contain."""
    repo = tmp_path / "repo"
    (repo / "daydream").mkdir(parents=True)
    (repo / "daydream" / "__init__.py").write_text("")
    (repo / "daydream" / "server.py").write_text("app = None\n")
    (repo / "ops").mkdir()
    (repo / "ops" / "requirements-prod.lock").write_text("# lock\nfastapi==0.1\n")
    (repo / "bin").mkdir()
    (repo / "bin" / "game").write_text("#!/bin/sh\n")
    _git(repo, "init", "-q")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", "fixture")
    monkeypatch.setattr(prodctl, "REPO", repo)
    return repo


@pytest.fixture
def srv(tmp_path, monkeypatch, fake_repo):
    root = tmp_path / "srv"
    for d in ("releases", "venvs", "data", "etc"):
        (root / d).mkdir(parents=True)
    (root / "etc" / "prod.env").write_text(
        "# prod\nDAYDREAM_ENV=prod\nDAYDREAM_ACCESS=edge\n"
        "DAYDREAM_PUBLIC_ORIGIN='https://www.example.com'\nDAYDREAM_PORT=54322\n"
        f"DAYDREAM_DATA_DIR={root / 'data'}\n")
    monkeypatch.setattr(prodctl, "SRV", root)
    monkeypatch.setattr(prodctl, "AS_USER", "")  # no daydream user in the suite
    # Pre-seed the venv the lock hashes to, so building a release never pips.
    lock = (fake_repo / "ops" / "requirements-prod.lock").read_bytes()
    venv = root / "venvs" / hashlib.sha256(lock).hexdigest()[:16] / "bin"
    venv.mkdir(parents=True)
    (venv / "python").symlink_to(sys.executable)
    yield root
    for rel in (root / "releases").iterdir():
        os.system(f"chmod -R u+w '{rel}'")


def test_env_file_parsing(tmp_path):
    f = tmp_path / "x.env"
    f.write_text("# c\nA=1\n\nB = 'two words'\nC=\"q\"\nnot a pair\nD=a=b\n")
    assert prodctl.parse_env_file(f) == {"A": "1", "B": "two words", "C": "q", "D": "a=b"}
    assert prodctl.parse_env_file(tmp_path / "missing.env") == {}


def test_release_env_is_a_clean_slate(srv, monkeypatch, tmp_path):
    """Nothing from the caller's (dev) environment leaks into a prod command."""
    monkeypatch.setenv("DAYDREAM_ACCESS", "tailscale")
    monkeypatch.setenv("DAYDREAM_PASSWORD", "dev-secret")
    rel = tmp_path / "rel"
    rel.mkdir()
    (rel / ".release.env").write_text("DAYDREAM_BUILD_SHA=abc123def456\n")
    env = prodctl.release_env(rel)
    assert env["DAYDREAM_ACCESS"] == "edge" and env["DAYDREAM_ENV"] == "prod"
    assert env["DAYDREAM_PUBLIC_ORIGIN"] == "https://www.example.com"
    assert env["DAYDREAM_BUILD_SHA"] == "abc123def456"
    assert env["DAYDREAM_LIFECYCLE"] == "external"
    assert env["DAYDREAM_ENGINES_ROOT"] == str(prodctl.REPO)  # the checkout that ran us
    assert env["HOME"] == str(srv / "data")   # the service user's home, not the operator's
    assert "DAYDREAM_PASSWORD" not in env
    assert set(env) - {k for k in env if k.startswith("DAYDREAM_")} <= {
        "PATH", "HOME", "LANG", "PYTHONDONTWRITEBYTECODE"}


def test_missing_prod_env_is_an_error(srv):
    (srv / "etc" / "prod.env").unlink()
    with pytest.raises(prodctl.ProdError, match="install-prod"):
        prodctl.prod_env()


def test_build_release_is_immutable_and_linked_to_its_venv(srv):
    sha = prodctl.resolve_ref("HEAD")
    rel = prodctl.build_release(sha)
    assert rel == srv / "releases" / sha[:12]
    assert (rel / ".release.env").read_text() == f"DAYDREAM_BUILD_SHA={sha[:12]}\n"
    assert (rel / "daydream" / "server.py").exists()
    assert not (rel / ".git").exists() and not (rel / ".env").exists()
    assert os.readlink(rel / ".venv").startswith("../../venvs/")
    assert (rel / ".venv" / "bin" / "python").exists()
    assert not os.access(rel / "daydream" / "server.py", os.W_OK)  # read-only
    assert list((rel / "daydream").glob("__pycache__/*.pyc"))     # precompiled
    assert prodctl.build_release(sha) == rel                       # reused


def test_point_is_an_atomic_relative_symlink(srv, tmp_path):
    a = srv / "releases" / "aaaaaaaaaaaa"
    b = srv / "releases" / "bbbbbbbbbbbb"
    a.mkdir()
    b.mkdir()
    prodctl.point("current", a)
    assert prodctl.current_release() == a
    prodctl.point("current", b)
    assert os.readlink(srv / "current") == "releases/bbbbbbbbbbbb"
    assert prodctl.current_release() == b


def _fake(monkeypatch, *, active=True, healthy=True):
    calls = []
    monkeypatch.setattr(prodctl, "run_tests_at", lambda sha: calls.append(("tests", sha[:12])))
    monkeypatch.setattr(prodctl, "_preflight", lambda rel: {"world_migrations_pending": "0"})
    monkeypatch.setattr(prodctl, "_backup", lambda rel: None)
    monkeypatch.setattr(prodctl, "unit_active", lambda unit: active)
    monkeypatch.setattr(prodctl, "systemctl", lambda action, unit: calls.append((action, unit)))
    monkeypatch.setattr(prodctl, "wait_healthy", lambda seconds=45.0: healthy)
    monkeypatch.setattr(prodctl, "served_build", lambda rel: rel.name if healthy else None)
    monkeypatch.setattr(prodctl, "git", _git_clean_tree)
    return calls


_real_git = prodctl.git


def _git_clean_tree(*args, **kw):
    if args[:2] == ("status", "--porcelain"):
        return ""
    return _real_git(*args, **kw)


def test_deploy_switches_and_restarts_when_awake(srv, monkeypatch):
    calls = _fake(monkeypatch)
    old = srv / "releases" / "000000000000"
    old.mkdir()
    prodctl.point("current", old)
    assert prodctl.deploy("HEAD", skip_tests=False) == 0
    sha = prodctl.resolve_ref("HEAD")[:12]
    assert prodctl.current_release().name == sha
    assert (srv / "previous").resolve() == old
    assert ("tests", sha) in calls and ("restart", prodctl.UNIT) in calls


def test_deploy_while_asleep_does_not_start_the_village(srv, monkeypatch):
    calls = _fake(monkeypatch, active=False)
    assert prodctl.deploy("HEAD", skip_tests=True) == 0
    assert not [c for c in calls if c[0] in ("start", "restart")]
    assert prodctl.current_release().name == prodctl.resolve_ref("HEAD")[:12]


def test_an_unhealthy_release_rolls_back_by_itself(srv, monkeypatch):
    calls = _fake(monkeypatch, healthy=False)
    old = srv / "releases" / "000000000000"
    old.mkdir()
    prodctl.point("current", old)
    with pytest.raises(prodctl.ProdError, match="rolled back to 000000000000"):
        prodctl.deploy("HEAD", skip_tests=True)
    assert prodctl.current_release() == old
    assert calls.count(("restart", prodctl.UNIT)) == 2


def test_deploy_refuses_a_dirty_tree(srv, monkeypatch):
    _fake(monkeypatch)
    monkeypatch.setattr(prodctl, "git", lambda *a, **k: " M daydream/x.py"
                        if a[:2] == ("status", "--porcelain") else _real_git(*a, **k))
    with pytest.raises(prodctl.ProdError, match="uncommitted"):
        prodctl.deploy("HEAD", skip_tests=True)


def test_prune_keeps_current_previous_and_the_newest(srv, monkeypatch):
    monkeypatch.setattr(prodctl, "KEEP_RELEASES", 2)
    names = [f"{i:012d}" for i in range(6)]
    for i, n in enumerate(names):
        d = srv / "releases" / n
        d.mkdir()
        os.utime(d, (1000 + i, 1000 + i))
    prodctl.point("current", srv / "releases" / names[0])   # oldest, but current
    prodctl.point("previous", srv / "releases" / names[1])
    prodctl.prune_releases()
    left = sorted(d.name for d in (srv / "releases").iterdir())
    assert left == sorted([names[0], names[1], names[4], names[5]])


def test_passthrough_names():
    assert set(prodctl.PASSTHROUGH) == {"world", "dream", "account", "invite", "prebake", "play",
                                        "text-scan"}


def test_the_lock_pins_what_the_dev_venv_tests_against():
    """Prod runs what the suite ran: every package in the lock that the dev
    venv also has must be the same version (regenerate with
    tools/lock_prod_requirements.sh after an upgrade)."""
    from importlib import metadata

    drift = []
    for line in (REPO / "ops" / "requirements-prod.lock").read_text().splitlines():
        if not line or line.startswith("#") or "==" not in line:
            continue
        name, _, pinned = line.partition("==")
        try:
            have = metadata.version(name)
        except metadata.PackageNotFoundError:
            continue
        if have != pinned:
            drift.append(f"{name}: lock {pinned}, dev venv {have}")
    assert not drift, drift


def test_age_recipients_take_bare_keys_from_authorized_keys(tmp_path, monkeypatch):
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "authorized_keys").write_text(
        'from="100.64.0.0/10",no-agent-forwarding ssh-ed25519 AAAAC3laptop peter@laptop\n'
        "# a comment\n"
        "ssh-rsa AAAAB3phone peter@phone\n")
    (ssh / "id_ed25519.pub").write_text("ssh-ed25519 AAAAC3box peter@dev\n")
    monkeypatch.setattr(prodctl, "SSH_DIR", ssh)
    out = prodctl.age_recipients(tmp_path / "r")
    assert out.read_text().splitlines() == [
        "ssh-ed25519 AAAAC3box", "ssh-ed25519 AAAAC3laptop", "ssh-rsa AAAAB3phone"]


def test_age_recipients_refuse_when_there_are_no_keys(tmp_path, monkeypatch):
    monkeypatch.setattr(prodctl, "SSH_DIR", tmp_path)
    with pytest.raises(prodctl.ProdError, match="no SSH public keys"):
        prodctl.age_recipients(tmp_path / "r")


def test_offsite_encrypts_before_anything_leaves(srv, monkeypatch, tmp_path):
    """The upload only ever sees the age output; the plaintext tarball never
    reaches wrangler."""
    backup = srv / "data" / "backups" / "20261004-043000"
    backup.mkdir(parents=True)
    (backup / "live.db").write_bytes(b"sqlite")
    rel = srv / "releases" / "aaaaaaaaaaaa"
    rel.mkdir()
    prodctl.point("current", rel)
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    (ssh / "authorized_keys").write_text("ssh-ed25519 AAAAC3laptop x\n")
    monkeypatch.setattr(prodctl, "SSH_DIR", ssh)
    monkeypatch.setattr(prodctl, "_backup", lambda r, data=None: backup)
    monkeypatch.setattr(prodctl.shutil, "which", lambda name: "/usr/bin/" + name)
    calls = []

    def fake_run(cmd, **kw):
        tool = "tar" if "tar" in cmd else cmd[0]
        calls.append(tool)
        if tool == "age":
            Path(cmd[cmd.index("-o") + 1]).write_bytes(b"age-encryption.org/v1 ciphertext")
        out = b"tarball-bytes" if tool == "tar" else b""
        return __import__("subprocess").CompletedProcess(cmd, 0, stdout=out, stderr=b"")

    monkeypatch.setattr(prodctl.subprocess, "run", fake_run)
    uploaded = []
    monkeypatch.setattr(prodctl, "_wrangler", lambda args: uploaded.append(args))
    assert prodctl.offsite() == 0
    assert calls == ["tar", "age"]
    (put,) = uploaded
    assert put[:3] == ["r2", "object", "put"]
    assert put[3] == "daydream-backups/prod-20261004-043000.tar.gz.age"
    assert put[put.index("--file") + 1].endswith(".tar.gz.age")



def test_prod_commands_run_as_the_service_user(srv, monkeypatch):
    """SECURITY WARN 2026-09-27: anything touching the data dir runs as
    daydream, so the operator's tools never follow a path planted there."""
    monkeypatch.setattr(prodctl, "AS_USER", "daydream")
    cmd = prodctl.as_prod(["python", "-m", "x"], {"A": "1", "HOME": "/srv/daydream/data"})
    assert cmd[:4] == ["sudo", "-n", "-u", "daydream"]
    assert cmd[4:6] == ["/usr/bin/env", "-i"] and "A=1" in cmd and cmd[-3:] == ["python", "-m", "x"]
    monkeypatch.setattr(prodctl, "AS_USER", "")
    assert prodctl.as_prod(["x"], {})[:2] == ["/usr/bin/env", "-i"]


def test_server_stopping_verbs_cycle_the_unit(srv, monkeypatch):
    rel = srv / "releases" / "aaaaaaaaaaaa"
    (rel / "bin").mkdir(parents=True)
    prodctl.point("current", rel)
    calls = []
    monkeypatch.setattr(prodctl, "unit_active", lambda unit: True)
    monkeypatch.setattr(prodctl, "systemctl", lambda a, u: calls.append(a))
    monkeypatch.setattr(prodctl, "wait_healthy", lambda seconds=45.0: True)
    monkeypatch.setattr(prodctl.subprocess, "run",
                        lambda cmd, **kw: calls.append("run") or
                        __import__("subprocess").CompletedProcess(cmd, 0))
    prodctl.passthrough(["world", "reset", "--yes"])
    assert calls == ["stop", "run", "start"]
    calls.clear()
    prodctl.passthrough(["invite", "list"])
    assert calls == ["run"]


def test_prebake_from_cache_is_staged_read_only_for_the_service(srv, monkeypatch, tmp_path):
    rel = srv / "releases" / "aaaaaaaaaaaa"
    (rel / "bin").mkdir(parents=True)
    prodctl.point("current", rel)
    (srv / "incoming-art").mkdir()
    graded = tmp_path / "graded"
    (graded / "w" / "room" / "r").mkdir(parents=True)
    (graded / "w" / "room" / "r" / "h.png").write_bytes(b"png")
    seen = []

    def fake_run(cmd, **kw):
        i = cmd.index("--from-cache")
        staged = Path(cmd[i + 1])
        seen.append((staged, (staged / "w" / "room" / "r" / "h.png").read_bytes()))
        return __import__("subprocess").CompletedProcess(cmd, 0)

    monkeypatch.setattr(prodctl, "unit_active", lambda unit: False)
    monkeypatch.setattr(prodctl.subprocess, "run", fake_run)
    prodctl.passthrough(["prebake", "--from-cache", str(graded)])
    (staged, data), = seen
    assert staged.parent == srv / "incoming-art" and data == b"png"
    assert not staged.exists()  # cleaned up after


def test_deploy_tests_run_with_the_dev_venv_in_the_worktree(tmp_path, monkeypatch):
    """bin/game (which the smoke test shells out to) needs the checkout's own
    .venv; the throwaway worktree has none unless it borrows the dev venv."""
    import subprocess
    import tempfile

    monkeypatch.setattr(tempfile, "mkdtemp", lambda prefix="": str(tmp_path))
    monkeypatch.setattr(prodctl, "git", lambda *a, **k: (tmp_path / "tree").mkdir())
    seen = {}

    def fake_run(cmd, cwd=None, **kw):
        if "pytest" in cmd:
            venv = Path(cwd) / ".venv"
            seen["venv"] = venv.is_symlink() and venv.resolve() == (prodctl.REPO / ".venv").resolve()
        return subprocess.CompletedProcess(cmd, 0, stdout="1 passed\n", stderr="")

    monkeypatch.setattr(prodctl.subprocess, "run", fake_run)
    prodctl.run_tests_at("a" * 40)
    assert seen["venv"]


def _sleep_fakes(srv, monkeypatch, *, active, edge=None):
    import subprocess

    rel = srv / "releases" / "aaaaaaaaaaaa"
    rel.mkdir(parents=True, exist_ok=True)
    prodctl.point("current", rel)
    calls = []
    monkeypatch.setattr(prodctl, "unit_active", lambda unit: active)
    monkeypatch.setattr(prodctl, "systemctl", lambda a, u: calls.append((a, u)))
    monkeypatch.setattr(prodctl, "run_release_python",
                        lambda rel, args, check=True, capture=False, **k:
                        subprocess.CompletedProcess(args, 0, stdout="", stderr=""))
    monkeypatch.setattr(prodctl, "_edge", lambda: edge)
    return calls


def test_sleep_stops_a_unit_that_is_not_exactly_active(srv, monkeypatch):
    """Codereview WARN 2026-09-28: a failed or auto-restarting unit (not
    "active") was left looping with the tunnel up."""
    calls = _sleep_fakes(srv, monkeypatch, active=False)
    assert prodctl.sleep_("", 0, keep_engines=True) == 0
    assert ("stop", prodctl.TUNNEL) in calls and ("stop", prodctl.UNIT) in calls


def test_a_cloudflare_error_does_not_abort_sleep_or_wake(srv, monkeypatch):
    """Codereview WARN 2026-09-28: the edge flag is best effort; the village
    still stops (or starts) when the Cloudflare API fails."""
    from daydream import edge as edge_mod

    def fail(*a, **k):
        raise edge_mod.EdgeError("Cloudflare API unreachable")

    fake_edge = type("E", (), {"EdgeError": edge_mod.EdgeError, "set_state": staticmethod(fail),
                               "describe_state": staticmethod(fail),
                               "sync_keepsakes": staticmethod(lambda rel: None)})
    calls = _sleep_fakes(srv, monkeypatch, active=True, edge=fake_edge)
    assert prodctl.sleep_("", 0, keep_engines=True) == 0
    assert ("stop", prodctl.UNIT) in calls
    monkeypatch.setattr(prodctl, "engines_reachable", lambda: {"vllm": True, "comfyui": True})
    monkeypatch.setattr(prodctl, "wait_healthy", lambda seconds=45.0: True)
    assert prodctl.wake() == 0
    assert ("start", prodctl.UNIT) in calls


def test_pull_leaves_the_friends_toons_adoptable_in_dev(srv, monkeypatch, tmp_path):
    """Codereview WARN 2026-09-28: pulled toons belonged to prod account ids
    that do not exist in dev, so nobody could enter one to reproduce a bug."""
    import sqlite3
    import subprocess

    src = tmp_path / "prod-live.db"
    c = sqlite3.connect(str(src))
    c.execute("CREATE TABLE objects (id TEXT, kind TEXT, owner_account TEXT)")
    c.execute("INSERT INTO objects VALUES ('t-mira', 'toon', 'a-prod1'), ('i-key', 'thing', NULL)")
    c.commit()
    c.close()
    backup = tmp_path / "backup"
    backup.mkdir()
    (backup / "live.db").write_bytes(src.read_bytes())
    rel = srv / "releases" / "aaaaaaaaaaaa"
    rel.mkdir(parents=True)
    prodctl.point("current", rel)
    monkeypatch.setattr(prodctl, "_backup", lambda rel: backup)
    monkeypatch.setattr(prodctl, "run_as_prod_bytes", lambda rel, cmd: src.read_bytes())
    monkeypatch.setattr(prodctl.subprocess, "run", lambda cmd, **kw: subprocess.CompletedProcess(cmd, 7))
    dev = tmp_path / "dev"
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(dev))
    assert prodctl.pull() == 0
    got = sqlite3.connect(str(dev / "worlds-dev" / "live.db"))
    assert got.execute("SELECT owner_account FROM objects WHERE kind = 'toon'").fetchall() == [(None,)]


def test_an_auto_rollback_keeps_the_release_before_for_prod_rollback(srv, monkeypatch):
    """codereview NOTE 2026-09-28: the failed deploy moved `previous` to the
    release it rolled back to, so `prod rollback` became a no-op."""
    _fake(monkeypatch, healthy=False)
    older, old = srv / "releases" / "000000000001", srv / "releases" / "000000000002"
    older.mkdir()
    old.mkdir()
    prodctl.point("previous", older)
    prodctl.point("current", old)
    with pytest.raises(prodctl.ProdError, match="rolled back"):
        prodctl.deploy("HEAD", skip_tests=True)
    assert prodctl.current_release() == old
    assert (srv / "previous").resolve() == older


def test_the_service_is_bounced_only_for_verbs_that_change_prod_data():
    """codereview NOTE 2026-09-28: `--check` and refused (no --yes) runs
    stopped the service and dropped every session."""
    assert not prodctl.needs_stop(["world", "refresh", "--check"])
    assert prodctl.needs_stop(["world", "refresh"])
    assert not prodctl.needs_stop(["world", "reset"])
    assert prodctl.needs_stop(["world", "reset", "--yes"])
    assert not prodctl.needs_stop(["world", "delete", "w-x"])
    assert prodctl.needs_stop(["dream", "install", "p.json"])
    assert prodctl.needs_stop(["prebake", "--from-cache", "x"])
    assert not prodctl.needs_stop(["invite", "list"])
    assert not prodctl.needs_stop(["dream", "digest"])
    assert prodctl.needs_stop(["world", "restore-backup", "/srv/daydream/data/backups/x"])


def test_a_path_the_service_user_cannot_read_is_refused_plainly(monkeypatch, tmp_path):
    monkeypatch.setattr(prodctl.Path, "home", classmethod(lambda cls: tmp_path))
    with pytest.raises(prodctl.ProdError, match="Commit it"):
        prodctl._refuse_unreadable_paths(["dream", "check", str(tmp_path / "patch.json")])
    prodctl._refuse_unreadable_paths(["dream", "check", "worlds/lost-hours/dreams/x/patch.json"])
    prodctl._refuse_unreadable_paths(["prebake", "--from-cache", str(tmp_path / "cache")])


def test_behind_survives_a_release_off_heads_history(fake_repo):
    """codereview NOTE 2026-09-28: after a history rewrite `rev-list` raised
    and aborted the whole status report."""
    head = prodctl.resolve_ref("HEAD")
    assert prodctl.behind(head[:12], head) == "up to date"
    assert "not in HEAD's history" in prodctl.behind("0123456789ab", head)
    (fake_repo / "x.txt").write_text("x")
    _git(fake_repo, "add", "-A")
    _git(fake_repo, "commit", "-q", "-m", "more")
    assert prodctl.behind(head[:12], prodctl.resolve_ref("HEAD")) == "1 commit(s) behind"


def test_instance_goes_after_the_verb_so_the_permission_rules_see_it(monkeypatch, capsys):
    """A leading `--instance` would walk around the prefix-matched ask rules
    (`bin/game prod world reset *`), so prodctl refuses it; after the verb it
    names the instance and is removed before the verb runs."""
    assert prodctl.main(["--instance", "zork", "world", "reset", "--yes"]) == 2
    assert "after the verb" in capsys.readouterr().err
    seen = {}
    monkeypatch.setattr(prodctl, "passthrough", lambda argv: seen.update(argv=argv, inst=prodctl.INSTANCE) or 0)
    monkeypatch.setattr(prodctl, "INSTANCE", None)
    assert prodctl.main(["invite", "create", "--for", "A Friend", "--instance", "zork"]) == 0
    assert seen == {"argv": ["invite", "create", "--for", "A Friend"], "inst": "zork"}
    assert prodctl.main(["backup", "--instance", "../x"]) == 2
    # Anywhere but the end it could split a two-word verb past its ask rule.
    assert prodctl.main(["world", "--instance", "zork", "reset", "--yes"]) == 2
    assert prodctl.main(["invite", "create", "--instance", "zork", "--for", "A"]) == 2
    assert prodctl.main(["backup", "--instance", "a", "--instance", "b"]) == 2


def test_instance_is_refused_on_verbs_that_act_on_the_attached_one(monkeypatch, capsys):
    """`sleep --instance zork` announced, rested and journaled zork while the
    village went down; `deploy --instance zork` backed up zork and migrated
    the village (codereview WARN 2026-09-28e). Only the pass-throughs and
    backup act on one instance's data."""
    monkeypatch.setattr(prodctl, "INSTANCE", None)
    for verb in (["sleep"], ["deploy"], ["keepsakes"], ["wake"], ["status"], ["pull"],
                 ["offsite"], ["rollback"], ["instance", "use", "village"]):
        assert prodctl.main([*verb, "--instance", "zork"]) == 2, verb
        assert "--instance applies only to" in capsys.readouterr().err
        assert prodctl.INSTANCE is None
    seen = []
    monkeypatch.setattr(prodctl, "_require_current", lambda: Path("/nowhere"))
    monkeypatch.setattr(prodctl, "_backup", lambda rel, data=None: seen.append(prodctl.INSTANCE))
    assert prodctl.main(["backup", "--instance", "zork"]) == 0
    assert seen == ["zork"]


# ---- prod root: the validated helper (docs/ADMIN-ROOT.md) ----------------------------------


def _fake_helper(tmp_path, monkeypatch, *, installed_sha=None, rc=0):
    """A stand-in for /usr/local/sbin/daydream-root; every sudo call recorded."""
    import subprocess

    helper = tmp_path / "daydream-root"
    helper.write_text("#!/usr/bin/python3 -I\n")
    monkeypatch.setattr(prodctl, "ROOT_HELPER", helper)
    calls = []

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        if cmd[-1] == "version":
            if installed_sha is None:
                return subprocess.CompletedProcess(cmd, 1, stdout="", stderr="a password is required")
            return subprocess.CompletedProcess(cmd, 0, stdout=f"daydream-root 1\nsha256 {installed_sha}\n",
                                               stderr="")
        return subprocess.CompletedProcess(cmd, rc)

    monkeypatch.setattr(prodctl.subprocess, "run", fake_run)
    return helper, calls


def test_prod_root_hands_its_arguments_to_the_helper_through_sudo(tmp_path, monkeypatch):
    helper, calls = _fake_helper(tmp_path, monkeypatch, rc=3)
    for argv in (["units", "--apply"], ["env", "set", "DAYDREAM_OPERATOR_NAME", "the Night Warden"],
                 ["status", "daydream-backup.timer"], []):
        calls.clear()
        assert prodctl.main(["root", *argv]) == 3  # the helper's exit code, as is
        assert calls == [["sudo", "-n", str(helper), *argv]]


def test_prod_root_doctor_says_when_the_repo_helper_is_newer(tmp_path, monkeypatch, capsys):
    repo_sha = hashlib.sha256((prodctl.REPO / "ops" / "root" / "daydream-root").read_bytes()).hexdigest()
    helper, calls = _fake_helper(tmp_path, monkeypatch, installed_sha="0" * 64)
    assert prodctl.main(["root", "doctor"]) == 1
    assert calls == [["sudo", "-n", str(helper), "doctor"], ["sudo", "-n", str(helper), "version"]]
    assert ("the repo's helper is newer: the operator runs sudo ops/install-prod.sh"
            in capsys.readouterr().out)
    _fake_helper(tmp_path, monkeypatch, installed_sha=repo_sha)
    assert prodctl.main(["root", "doctor"]) == 0
    out = capsys.readouterr().out
    assert "newer" not in out and f"the installed helper is the repo's ({repo_sha[:12]})" in out


def test_prod_root_doctor_without_the_sudoers_line_says_so(tmp_path, monkeypatch, capsys):
    _fake_helper(tmp_path, monkeypatch, installed_sha=None)
    assert prodctl.main(["root", "doctor"]) == 1
    assert "sudo ops/install-prod.sh" in capsys.readouterr().out


def test_prod_root_before_the_helper_is_installed_names_the_installer(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(prodctl, "ROOT_HELPER", tmp_path / "missing")
    monkeypatch.setattr(prodctl.subprocess, "run", lambda *a, **k: pytest.fail("ran something"))
    assert prodctl.main(["root", "units"]) == 1
    assert "sudo ops/install-prod.sh" in capsys.readouterr().err


def test_prod_root_arguments_reach_the_helper_before_instance_is_read(tmp_path, monkeypatch):
    """An --instance moved into the middle must not turn `root units
    --instance x --apply` into `units --apply` past the ask rule on
    `prod root units --apply`: the helper gets it as typed and refuses it."""
    helper, calls = _fake_helper(tmp_path, monkeypatch, rc=2)
    monkeypatch.setattr(prodctl, "INSTANCE", None)
    assert prodctl.main(["root", "units", "--instance", "zork", "--apply"]) == 2
    assert calls == [["sudo", "-n", str(helper), "units", "--instance", "zork", "--apply"]]
    assert prodctl.INSTANCE is None


# ---- what a publish ships (docs/runbooks/publish.md) --------------------------------


@pytest.mark.tier_short
def test_followups_name_what_a_deploy_alone_does_not_do():
    assert prodctl.followups(["daydream/verbs.py", "web/assets/main.js"], "1.5", "1.5") == []
    content = prodctl.followups(["worlds/lost-hours/cast/tace.json", "worlds/lost-hours.json"],
                                "1.5", "1.5")
    assert len(content) == 1 and "world refresh --check" in content[0] and "lost-hours" in content[0]
    # A walkthrough is a test's replay; a dream is installed, not refreshed.
    assert prodctl.followups(["worlds/lost-hours/walkthroughs/prologue.json"], "1.5", "1.5") == []
    (dream,) = prodctl.followups(["worlds/lost-hours/dreams/d-1/patch.json"], "1.5", "1.5")
    assert "dream" in dream and "refresh" not in dream
    # A MINOR bump alone still wants a refresh (it re-stamps the world).
    assert any("world refresh" in s for s in prodctl.followups(["daydream/version.py"], "1.5", "1.6"))
    major = prodctl.followups(["daydream/version.py"], "1.5", "2.0")
    assert "MAJOR" in major[0] and "reset" in major[0]
    joined = " | ".join(prodctl.followups(
        ["edge/src/worker.js", "ops/systemd/daydream-prod.service", "ops/install-prod.sh",
         "ops/prod.env.example", "migrations/019_x.sql", "ops/requirements-prod.lock"],
        "1.5", "1.5"))
    for needle in ("edge deploy", "root units", "install-prod.sh", "root env set",
                   "migrations", "venv"):
        assert needle in joined, needle


def test_plan_lists_what_goes_out_and_what_else_it_needs(srv, fake_repo, capsys):
    first = prodctl.resolve_ref("HEAD")
    prodctl.point("current", prodctl.build_release(first))
    (fake_repo / "worlds" / "lost-hours").mkdir(parents=True)
    (fake_repo / "worlds" / "lost-hours" / "world.json").write_text("{}\n")
    (fake_repo / "edge").mkdir()
    (fake_repo / "edge" / "worker.js").write_text("// w\n")
    _git(fake_repo, "add", "-A")
    _git(fake_repo, "commit", "-q", "-m", "a new line for the lamplighter")
    capsys.readouterr()
    assert prodctl.plan("HEAD") == 0
    out = capsys.readouterr().out
    assert "a new line for the lamplighter" in out
    assert "pushed: not yet" in out  # the fixture repo has no remote
    assert "world refresh --check" in out and "edge deploy" in out
    prodctl.point("current", prodctl.build_release(prodctl.resolve_ref("HEAD")))
    prodctl.plan("HEAD")
    assert "nothing to ship" in capsys.readouterr().out


def test_a_venv_is_sealed_read_only_and_refused_if_not_the_operators(tmp_path, monkeypatch):
    """Security review 2026-09-29: the prod venv was group-writable by the
    service's group, and the operator runs its python on every deploy."""
    venv = tmp_path / "venvs" / "abc"
    (venv / "lib").mkdir(parents=True)
    pth = venv / "lib" / "x.pth"
    pth.write_text("")
    os.chmod(pth, 0o664)
    os.chmod(venv / "lib", 0o2775)
    prodctl._seal_venv(venv)
    assert not os.stat(pth).st_mode & 0o022
    assert not os.stat(venv / "lib").st_mode & 0o022
    monkeypatch.setattr(prodctl.os, "getuid", lambda: os.stat(pth).st_uid + 1)
    ran = []
    monkeypatch.setattr(prodctl.subprocess, "run", lambda *a, **k: ran.append(a))
    with pytest.raises(prodctl.ProdError, match="not yours"):
        prodctl._seal_venv(venv)
    assert ran == []  # refused before any chmod, whose EPERM would hide the reason


@pytest.mark.parametrize("argv,ok", [
    (["world", "patch", "p.json"], False), (["world", "patch", "p.json", "--check"], True),
    (["dream", "apply", "p.json"], False), (["dream", "install", "p.json"], True),
    (["dream", "digest"], True),
])
def test_a_dream_reaches_prod_only_through_install(argv, ok):
    """Security review 2026-09-29: `world patch` and `dream apply` changed the
    live DB with no rehearsal and the service running."""
    if ok:
        prodctl._refuse_side_doors(argv)
    else:
        with pytest.raises(prodctl.ProdError, match="dream install"):
            prodctl._refuse_side_doors(argv)
