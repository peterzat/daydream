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
        "DAYDREAM_PUBLIC_ORIGIN='https://www.eidolon.com'\nDAYDREAM_PORT=54322\n"
        f"DAYDREAM_DATA_DIR={root / 'data'}\n")
    monkeypatch.setattr(prodctl, "SRV", root)
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
    assert env["DAYDREAM_PUBLIC_ORIGIN"] == "https://www.eidolon.com"
    assert env["DAYDREAM_BUILD_SHA"] == "abc123def456"
    assert env["DAYDREAM_LIFECYCLE"] == "systemd"
    assert env["DAYDREAM_ENGINES_ROOT"] == str(prodctl.REPO)  # the checkout that ran us
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
    assert set(prodctl.PASSTHROUGH) == {"world", "dream", "account", "invite", "prebake", "play"}


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
