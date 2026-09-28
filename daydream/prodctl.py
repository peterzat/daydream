"""`bin/game prod ...`: deploy and run daydream prod on this box (SPEC
2026-09-27 criteria 9-15; docs/GOING-LIVE.md section 7).

Runs as the operator, from the dev checkout, with the standard library only.
The layout is made once by `sudo ops/install-prod.sh`:

    /srv/daydream/releases/<sha>/  a `git archive` of one commit, read-only;
                                   .release.env pins DAYDREAM_BUILD_SHA;
                                   .venv -> ../../venvs/<lockhash>
    /srv/daydream/venvs/<hash>/    built from ops/requirements-prod.lock
    /srv/daydream/current          -> releases/<sha> (what the unit runs)
    /srv/daydream/previous         -> the release before it (for rollback)
    /srv/daydream/data/            DAYDREAM_DATA_DIR (world, accounts, art)
    /srv/daydream/etc/prod.env     the whole prod environment

Every prod command that touches data runs the CURRENT RELEASE's own code
with prod's environment on a clean slate (`env -i`), never dev code against
the prod database. That rules out migration skew and a dev `.env` leaking
into prod.

Verbs:

- `status`
- `check` (live verification of the edge and prod invariants; daydream/prodcheck.py)
- `deploy [ref] [--skip-tests]`
- `rollback`
- `logs [-f]`
- `wake`
- `sleep [--note TEXT] [--grace SECONDS] [--keep-engines]`
- `backup`
- `keepsakes` (sync keepsakes to the edge; hourly by timer)
- `offsite` / `offsite-restore NAME DEST` (age-encrypted backups in R2; weekly)
- `pull` (a prod backup into dev)
- pass-throughs to the release's `bin/game`: `world`, `dream`, `account`,
  `invite`, `prebake`, `play`

Agent policy: CLAUDE.md "Prod" (the operator's standing grant, and the verbs
that always prompt). Playbooks: docs/runbooks/.
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRV = Path(os.environ.get("DAYDREAM_PROD_ROOT", "/srv/daydream"))
UNIT = "daydream-prod.service"
TUNNEL = "cloudflared-daydream.service"
KEEP_RELEASES = 5
PASSTHROUGH = ("world", "dream", "account", "invite", "prebake", "play")


class ProdError(RuntimeError):
    pass


def say(msg: str) -> None:
    print(msg, flush=True)


# ---- environment -----------------------------------------------------------------


def parse_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines; comments and blanks ignored; one layer of quotes
    stripped. The format systemd's EnvironmentFile reads."""
    out: dict[str, str] = {}
    if not path.exists():
        return out
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        out[key.strip()] = value
    return out


def prod_env() -> dict[str, str]:
    env = parse_env_file(SRV / "etc" / "prod.env")
    if not env:
        raise ProdError(f"{SRV}/etc/prod.env is missing or empty; run sudo ops/install-prod.sh")
    return env


# Every prod command that touches the data dir runs AS THE SERVICE USER, never
# as the operator: the data dir is writable by the sandboxed service, so the
# operator's own tools following a path planted there (a symlinked "portrait",
# a symlinked announce file) would carry the sandbox's reach out to everything
# the operator can read and write (SECURITY WARN 2026-09-27). The operator
# only handles bytes a prod command hands back on stdout. Dropping to the
# service user is safe to allow without a password (sudoers: (daydream) ALL).
# DAYDREAM_PROD_AS_USER="" runs as the caller (rehearsals in a scratch root).
AS_USER = os.environ.get("DAYDREAM_PROD_AS_USER", "daydream")


def data_dir() -> Path:
    return Path(prod_env().get("DAYDREAM_DATA_DIR", str(SRV / "data")))


def release_env(release: Path) -> dict[str, str]:
    """The clean environment a prod command runs in: prod.env, the release's
    build id, where the engines live. The service is started and stopped by
    this module (DAYDREAM_LIFECYCLE=external), never by the command itself."""
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(prod_env())
    env["HOME"] = str(data_dir())
    env.update(parse_env_file(release / ".release.env"))
    env["DAYDREAM_ENGINES_ROOT"] = str(REPO)
    env["DAYDREAM_LIFECYCLE"] = "external"
    return env


def as_prod(cmd: list[str], env: dict[str, str]) -> list[str]:
    """`cmd` run as the service user with exactly `env`."""
    pairs = [f"{k}={v}" for k, v in env.items()]
    prefix = ["sudo", "-n", "-u", AS_USER] if AS_USER else []
    return [*prefix, "/usr/bin/env", "-i", *pairs, *cmd]


def current_release() -> Path | None:
    link = SRV / "current"
    return link.resolve() if link.exists() else None


def _require_current() -> Path:
    rel = current_release()
    if rel is None:
        raise ProdError("no release yet: run `bin/game prod deploy` first")
    return rel


def run_release_python(release: Path, args: list[str], *, check: bool = True,
                       capture: bool = False) -> subprocess.CompletedProcess:
    cmd = as_prod([str(release / ".venv" / "bin" / "python"), *args], release_env(release))
    return subprocess.run(cmd, cwd=release, check=check, text=True, capture_output=capture)


def run_as_prod_bytes(release: Path, cmd: list[str]) -> bytes:
    """A command's stdout as bytes, run as the service user (tar, cat)."""
    r = subprocess.run(as_prod(cmd, release_env(release)), cwd=release, capture_output=True)
    if r.returncode != 0:
        raise ProdError(f"{cmd[0]} failed: {r.stderr.decode('utf-8', 'replace')[-300:]}")
    return r.stdout


# Verbs that must not run against a live service: stopped first, started after.
STOP_FOR = {("world", "reset"), ("world", "refresh"), ("world", "restore"),
            ("world", "snapshot-restore"), ("world", "restore-backup"), ("world", "delete"),
            ("world", "load"), ("dream", "install"), ("prebake",)}
INCOMING_ART = "incoming-art"


def passthrough(args: list[str]) -> int:
    """Run the current release's own bin/game as the service user (prod env,
    clean slate), stopping and restarting the service around verbs that need
    it down. `prebake --from-cache DIR` first stages DIR somewhere the
    service user can read but never write."""
    rel = _require_current()
    args = list(args)
    _refuse_unreadable_paths(args)
    staged = None
    if args[:1] == ["prebake"] and "--from-cache" in args:
        i = args.index("--from-cache")
        staged = _stage_art(Path(args[i + 1]).expanduser())
        args[i + 1] = str(staged)
    was_up = needs_stop(args) and unit_active(UNIT)
    if was_up:
        say("stopping the service for this ...")
        systemctl("stop", UNIT)
    try:
        return subprocess.run(as_prod([str(rel / "bin" / "game"), *args], release_env(rel)),
                              cwd=rel).returncode
    finally:
        if staged is not None:
            shutil.rmtree(staged, ignore_errors=True)
        if was_up:
            systemctl("start", UNIT)
            say("service: " + ("back up" if wait_healthy() else "NOT healthy after restart"))


# Verbs that refuse (or only look) without their confirming flag.
NEEDS_YES = {("world", "reset"), ("world", "delete"), ("world", "restore"),
             ("world", "snapshot-restore")}


def needs_stop(args: list[str]) -> bool:
    """Stop the service only for a verb that will really change prod data: not
    `world refresh --check`, and not a destructive verb that will refuse for
    want of `--yes` (codereview NOTE 2026-09-28: those bounced every session)."""
    key2, key1 = tuple(args[:2]), tuple(args[:1])
    if key2 not in STOP_FOR and key1 not in STOP_FOR:
        return False
    if key2 == ("world", "refresh") and "--check" in args:
        return False
    if key2 in NEEDS_YES and "--yes" not in args:
        return False
    return True


def _refuse_unreadable_paths(args: list[str]) -> None:
    """A pass-through runs as the service user, who cannot read the
    operator's home: say so plainly instead of a bare usage error. A dream
    patch reaches prod committed and deployed (docs/runbooks/content.md)."""
    home = Path.home()
    for n, a in enumerate(args[1:], start=1):
        if a.startswith("-") or a.startswith(str(SRV)) or args[n - 1] == "--from-cache":
            continue  # (--from-cache's dir is staged for the service user)
        p = Path(a).expanduser()
        if p.is_absolute() and (p == home or home in p.parents):
            raise ProdError(
                f"{a} is under {home}, which the prod service user cannot read. Commit it, "
                "`bin/game prod deploy`, then pass its path relative to the repo (for a dream: "
                "worlds/lost-hours/dreams/<id>/patch.json); art goes through prebake --from-cache")


def _stage_art(src: Path) -> Path:
    """Copy the operator's graded image cache (their own files) into a dir the
    operator owns and the service user can only read (made by
    ops/install-prod.sh): the prod prebake reads from there."""
    if not src.is_dir():
        raise ProdError(f"{src} is not a directory")
    dest = SRV / INCOMING_ART / time.strftime("%Y%m%d-%H%M%S")
    shutil.copytree(src, dest, symlinks=False)
    return dest


# ---- systemd + health -----------------------------------------------------------


def unit_active(unit: str) -> bool:
    return subprocess.run(["systemctl", "is-active", "--quiet", unit]).returncode == 0


def systemctl(action: str, unit: str) -> None:
    r = subprocess.run(["sudo", "-n", "/usr/bin/systemctl", action, unit])
    if r.returncode != 0:
        raise ProdError(f"sudo systemctl {action} {unit} failed (is ops/install-prod.sh installed?)")


def port() -> int:
    return int(prod_env().get("DAYDREAM_PORT", "54322"))


def http_ok(url: str, timeout: float = 2.0, headers: dict | None = None) -> str | None:
    """The body of a 200 response, else None."""
    try:
        req = urllib.request.Request(url, headers=headers or {})
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read().decode("utf-8", "replace") if r.status == 200 else None
    except (urllib.error.URLError, OSError, ValueError):
        return None


def wait_healthy(seconds: float = 45.0) -> bool:
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if http_ok(f"http://127.0.0.1:{port()}/healthz") is not None:
            return True
        time.sleep(0.5)
    return False


def cli_cookie(release: Path) -> str | None:
    r = run_release_python(release, ["-m", "daydream.accounts_cli", "account", "cli-cookie",
                                     "--cache", str(data_dir() / ".cli-cookie")],
                           check=False, capture=True)
    return r.stdout.strip() if r.returncode == 0 and r.stdout.strip() else None


def served_build(release: Path) -> str | None:
    cookie = cli_cookie(release)
    if not cookie:
        return None
    body = http_ok(f"http://127.0.0.1:{port()}/status/build", headers={"Cookie": cookie})
    if body is None:
        return None
    for line in body.splitlines():
        if line.startswith("build: "):
            return line.split(": ", 1)[1].strip()
    return None


def engines_reachable() -> dict[str, bool]:
    env = prod_env()
    llm = env.get("DAYDREAM_LLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/")
    comfy = env.get("DAYDREAM_COMFYUI_BASE_URL", "http://127.0.0.1:8188").rstrip("/")
    return {"vllm": http_ok(llm + "/models") is not None,
            "comfyui": http_ok(comfy + "/system_stats") is not None}


# ---- releases -----------------------------------------------------------------------


def git(*args: str, capture: bool = True) -> str:
    r = subprocess.run(["git", "-C", str(REPO), *args], check=True, text=True,
                       capture_output=capture)
    return (r.stdout or "").strip()


def resolve_ref(ref: str) -> str:
    return git("rev-parse", "--verify", f"{ref}^{{commit}}")


def lock_hash(release: Path) -> str:
    lock = release / "ops" / "requirements-prod.lock"
    return hashlib.sha256(lock.read_bytes()).hexdigest()[:16]


def run_tests_at(sha: str) -> None:
    """The short and medium tiers against exactly `sha`, in a throwaway
    worktree, with the dev venv and a scrubbed environment."""
    tmp = Path(tempfile.mkdtemp(prefix="daydream-deploy-"))
    try:
        git("worktree", "add", "--detach", str(tmp / "tree"), sha)
        # Tests that shell out to bin/game need the checkout's own .venv; a
        # fresh worktree has none, so it borrows the dev venv.
        (tmp / "tree" / ".venv").symlink_to(REPO / ".venv")
        env = {k: v for k, v in os.environ.items() if not k.startswith("DAYDREAM_")}
        env["PYTHONPATH"] = str(tmp / "tree")
        say(f"tests: short + medium at {sha[:12]} ...")
        r = subprocess.run([str(REPO / ".venv" / "bin" / "python"), "-m", "pytest", "-q", "-x",
                            "-p", "no:cacheprovider", "-m", "tier_short or tier_medium"],
                           cwd=tmp / "tree", env=env, text=True, capture_output=True)
        tail = "\n".join(r.stdout.strip().splitlines()[-3:])
        if r.returncode != 0:
            raise ProdError(f"tests failed at {sha[:12]}; not deploying:\n{tail}")
        say(f"tests: {tail.splitlines()[-1] if tail else 'passed'}")
    finally:
        subprocess.run(["git", "-C", str(REPO), "worktree", "remove", "--force", str(tmp / "tree")],
                       capture_output=True)
        shutil.rmtree(tmp, ignore_errors=True)


def build_release(sha: str) -> Path:
    """Archive `sha` into releases/<short>/ (reused if already complete) with
    its venv linked by lockfile hash and its bytecode precompiled."""
    short = sha[:12]
    release = SRV / "releases" / short
    if (release / ".release.env").exists():
        say(f"release {short}: already built")
        return release
    tmp = SRV / "releases" / f".{short}.tmp"
    if tmp.exists():
        _force_rmtree(tmp)
    tmp.mkdir(parents=True)
    archive = subprocess.Popen(["git", "-C", str(REPO), "archive", sha], stdout=subprocess.PIPE)
    subprocess.run(["tar", "-x", "-C", str(tmp)], stdin=archive.stdout, check=True)
    if archive.wait() != 0:
        raise ProdError(f"git archive {short} failed")
    (tmp / ".release.env").write_text(f"DAYDREAM_BUILD_SHA={short}\n")
    venv = SRV / "venvs" / lock_hash(tmp)
    if not (venv / "bin" / "python").exists():
        say(f"venv {venv.name}: building from ops/requirements-prod.lock ...")
        vtmp = venv.with_name(venv.name + ".tmp")
        if vtmp.exists():
            shutil.rmtree(vtmp)
        subprocess.run(["python3", "-m", "venv", str(vtmp)], check=True)
        subprocess.run([str(vtmp / "bin" / "pip"), "install", "-q", "-r",
                        str(tmp / "ops" / "requirements-prod.lock")], check=True)
        vtmp.rename(venv)
    else:
        say(f"venv {venv.name}: reused")
    (tmp / ".venv").symlink_to(Path("..") / ".." / "venvs" / venv.name)
    subprocess.run([str(venv / "bin" / "python"), "-m", "compileall", "-q", str(tmp / "daydream")],
                   check=True, env={"PATH": "/usr/bin:/bin"})
    subprocess.run(["chmod", "-R", "a-w", str(tmp)], check=True)
    os.chmod(tmp, 0o2750)  # the dir itself stays renameable/removable by us
    tmp.rename(release)
    say(f"release {short}: built")
    return release


def _force_rmtree(path: Path) -> None:
    subprocess.run(["chmod", "-R", "u+w", str(path)], check=False)
    shutil.rmtree(path, ignore_errors=True)


def point(link_name: str, release: Path) -> None:
    """Atomically repoint SRV/<link_name> at `release`."""
    link = SRV / link_name
    tmp = SRV / f".{link_name}.new"
    if tmp.is_symlink() or tmp.exists():
        tmp.unlink()
    tmp.symlink_to(Path("releases") / release.name)
    os.replace(tmp, link)


def prune_releases() -> None:
    keep = {p.resolve() for p in (SRV / "current", SRV / "previous") if p.exists()}
    rels = sorted((d for d in (SRV / "releases").iterdir()
                   if d.is_dir() and not d.name.startswith(".")),
                  key=lambda d: d.stat().st_mtime, reverse=True)
    for d in rels[KEEP_RELEASES:]:
        if d.resolve() not in keep:
            _force_rmtree(d)
            say(f"pruned release {d.name}")


def _preflight(release: Path) -> dict[str, str]:
    r = run_release_python(release, ["-m", "daydream.admin", "preflight"], check=False,
                           capture=True)
    info = {}
    for line in r.stdout.splitlines():
        if ": " in line:
            k, _, v = line.partition(": ")
            info[k.strip()] = v.strip()
    if r.returncode == 3:
        raise ProdError("preflight refused the release:\n" + r.stdout)
    if r.returncode != 0:
        raise ProdError("preflight failed:\n" + r.stdout + r.stderr)
    return info


def _backup(release: Path) -> Path | None:
    r = run_release_python(release, ["-m", "daydream.admin", "backup", "--keep", "14"],
                           check=True, capture=True)
    say(r.stdout.strip())
    for token in r.stdout.split():
        if token.startswith(str(SRV)) and "backups" in token:
            return Path(token.rstrip(":"))
    return None


def deploy(ref: str, skip_tests: bool) -> int:
    sha = resolve_ref(ref)
    head = resolve_ref("HEAD")
    if sha == head and git("status", "--porcelain"):
        raise ProdError("the working tree has uncommitted changes; commit first (prod runs commits)")
    if not skip_tests:
        run_tests_at(sha)
    release = build_release(sha)
    info = _preflight(release)
    pending = sum(int(info.get(k, "0") or 0) for k in
                  ("world_migrations_pending", "accounts_migrations_pending"))
    backup = _backup(release)
    before = current_release()
    prev_link = SRV / "previous"
    before_previous = prev_link.resolve() if prev_link.is_symlink() else None
    point("current", release)
    if before is not None and before != release:
        point("previous", before)
    if not unit_active(UNIT):
        say(f"deployed {release.name}; the village is asleep, so it will run this at "
            "`bin/game prod wake`")
        prune_releases()
        return 0
    systemctl("restart", UNIT)
    if wait_healthy() and served_build(release) == release.name:
        say(f"deployed {release.name}: healthy")
        prune_releases()
        return 0
    say(f"release {release.name} did not come up healthy; rolling back")
    if before is None:
        raise ProdError("no previous release to roll back to; the unit is down")
    point("current", before)
    # Undo the previous-link move too, so a later `prod rollback` still goes
    # one release further back (codereview NOTE 2026-09-28).
    if before_previous is not None and before_previous.is_dir():
        point("previous", before_previous)
    elif prev_link.is_symlink():
        prev_link.unlink()
    if pending and backup is not None:
        systemctl("stop", UNIT)
        _restore_backup(backup, before)
    systemctl("restart", UNIT)
    ok = wait_healthy()
    raise ProdError(f"deploy of {release.name} rolled back to {before.name} "
                    f"({'healthy' if ok else 'NOT healthy: look at bin/game prod logs'})")


def _restore_backup(backup: Path, release: Path) -> None:
    """Put a backup's DBs back (service stopped), as the service user."""
    r = run_release_python(release, ["-m", "daydream.admin", "restore-backup", str(backup)],
                           check=False, capture=True)
    say((r.stdout + r.stderr).strip())


def rollback() -> int:
    prev = SRV / "previous"
    if not prev.exists():
        raise ProdError("no previous release recorded")
    before = current_release()
    target = prev.resolve()
    point("current", target)
    if before is not None:
        point("previous", before)
    if unit_active(UNIT):
        systemctl("restart", UNIT)
        say("healthy" if wait_healthy() else "NOT healthy: look at bin/game prod logs")
    say(f"current -> {target.name}")
    return 0


# ---- sleep / wake -------------------------------------------------------------------


def _edge():
    """The edge module when the Cloudflare side is configured, else None."""
    try:
        from daydream import edge
    except ImportError:
        return None
    return edge if edge.configured() else None


def _set_edge_flag(edge, state: str, note: str = "") -> bool:
    """Best effort (codereview WARN 2026-09-28): a Cloudflare API error must
    not abort a sleep or wake half done. An unset asleep flag is covered
    anyway: the Worker reads an unreachable origin as asleep."""
    try:
        edge.set_state(state, note=note)
        return True
    except (edge.EdgeError, OSError) as e:
        say(f"edge: the flag is not {state} ({e}); set it later with bin/game edge "
            + ("wake" if state == "awake" else "sleep"))
        return False


def wake() -> int:
    rel = _require_current()
    reach = engines_reachable()
    if not all(reach.values()):
        say("engines: starting vLLM and ComfyUI ...")
        dev_game = REPO / "bin" / "game"
        subprocess.run([str(dev_game), "vllm-up"], check=False)
        subprocess.run([str(dev_game), "comfyui-up"], check=False)
        deadline = time.monotonic() + 240
        while time.monotonic() < deadline and not all(engines_reachable().values()):
            time.sleep(3)
        reach = engines_reachable()
        if not all(reach.values()):
            raise ProdError(f"engines did not come up: {reach}")
    say("engines: up")
    systemctl("start", TUNNEL)
    systemctl("start", UNIT)
    if not wait_healthy():
        raise ProdError("the service did not answer /healthz; look at bin/game prod logs")
    say(f"daydream prod {rel.name}: awake on 127.0.0.1:{port()}")
    edge = _edge()
    if edge is not None:
        if _set_edge_flag(edge, "awake"):
            say("edge: awake")
    else:
        say("edge: not configured yet (docs/CLOUDFLARE-SETUP.md); the edge state is unchanged")
    return 0


def sleep_(note: str, grace: int, keep_engines: bool) -> int:
    rel = _require_current()
    if unit_active(UNIT):
        if grace > 0:
            text = ("The lamps are dimming; the village will sleep in a minute or so. "
                    "What you carry is safe, and your journal will remember today.")
            # Written by the service user (never the operator: the data dir is
            # the sandbox's); the server picks it up within seconds
            # (daydream/announce.py). There is no web endpoint for it.
            run_release_python(rel, ["-m", "daydream.announce", "send", text], check=False)
            say(f"told everyone; waiting {grace}s ...")
            time.sleep(grace)
        edge = _edge()
        if edge is not None and _set_edge_flag(edge, "asleep", note):
            say("edge: asleep")
    # Stop both whatever their state: a failed or auto-restarting unit is not
    # "active" yet may be looping; stopping an inactive unit is a no-op.
    systemctl("stop", TUNNEL)
    systemctl("stop", UNIT)
    say("service + tunnel: stopped")
    # Rest everyone and write their journals while the engines are still up
    # (the release's own code, against prod data, with the server stopped).
    r = run_release_python(rel, ["-m", "daydream.admin", "rest-all", "--journal"], check=False,
                           capture=True)
    say(r.stdout.strip() or "rest-all: done")
    edge = _edge()
    if edge is not None:
        _set_edge_flag(edge, "asleep", note)  # also when the service was already down
        try:
            edge.sync_keepsakes(rel)
        except Exception as e:  # keepsakes are a courtesy; never block sleep on them
            say(f"keepsakes: not synced ({e})")
    if not keep_engines:
        dev_game = REPO / "bin" / "game"
        subprocess.run([str(dev_game), "vllm-down"], check=False)
        subprocess.run([str(dev_game), "comfyui-down"], check=False)
        say("engines: stopped; the GPU is free")
    say("the village is asleep")
    return 0


def keepsakes() -> int:
    """Push keepsakes to the edge while the village is awake (the hourly
    timer), so even an unplanned outage leaves friends a recent copy. A no-op
    while asleep: `sleep` already synced on the way down."""
    if not unit_active(UNIT):
        say("keepsakes: the village is asleep; nothing new to sync")
        return 0
    edge = _edge()
    if edge is None:
        say("keepsakes: the edge is not configured")
        return 0
    edge.sync_keepsakes(_require_current())
    return 0


# ---- offsite backups (criterion 22) --------------------------------------------------

R2_BUCKET = os.environ.get("DAYDREAM_R2_BUCKET", "daydream-backups")
SSH_DIR = Path.home() / ".ssh"


def age_recipients(out: Path) -> Path:
    """A recipients file for age: every SSH key allowed into this box (their
    private halves live on the operator's own machines, so a backup survives
    the box) plus the box's own key (so a restore can be proven here). Only
    bare `ssh-ed25519`/`ssh-rsa` lines: authorized_keys options would trip age."""
    keys = []
    for src in (SSH_DIR / "authorized_keys", SSH_DIR / "id_ed25519.pub"):
        if src.exists():
            for line in src.read_text().splitlines():
                line = line.strip()
                for kind in ("ssh-ed25519 ", "ssh-rsa "):
                    i = line.find(kind)
                    if i >= 0:
                        keys.append(" ".join(line[i:].split()[:2]))
    if not keys:
        raise ProdError("no SSH public keys to encrypt to (~/.ssh/authorized_keys)")
    out.write_text("\n".join(sorted(set(keys))) + "\n")
    return out


def _wrangler(args: list[str]) -> None:
    from daydream import edge

    edge._ensure_node_modules()
    r = subprocess.run(["npx", "--no-install", "wrangler", *args], cwd=edge.EDGE,
                       env=edge._wrangler_env())
    if r.returncode != 0:
        raise ProdError("wrangler " + " ".join(args[:3]) + " failed")


def offsite() -> int:
    """A fresh consistent backup, tarred, age-encrypted to the operator's SSH
    keys, uploaded to the private R2 bucket. Weekly by timer; retention is the
    bucket's lifecycle rule (docs/CLOUDFLARE-SETUP.md)."""
    if shutil.which("age") is None:
        raise ProdError("age is not installed (sudo ops/install-prod.sh installs it)")
    rel = _require_current()
    backup = _backup(rel)
    if backup is None:
        raise ProdError("nothing to back up yet")
    with tempfile.TemporaryDirectory(prefix="daydream-offsite-") as tmp:
        tmpd = Path(tmp)
        name = f"prod-{backup.name}.tar.gz"
        # The service user tars (it owns what is in the data dir); the
        # operator only receives the bytes and encrypts them.
        (tmpd / name).write_bytes(run_as_prod_bytes(rel, ["tar", "-czf", "-", "-C", str(backup), "."]))
        sealed = tmpd / (name + ".age")
        subprocess.run(["age", "-R", str(age_recipients(tmpd / "recipients")),
                        "-o", str(sealed), str(tmpd / name)], check=True)
        _wrangler(["r2", "object", "put", f"{R2_BUCKET}/{sealed.name}", "--file", str(sealed),
                   "--remote"])
    say(f"offsite: {sealed.name} -> r2://{R2_BUCKET}")
    return 0


def offsite_restore(name: str, dest: Path) -> int:
    """Fetch one offsite backup and unpack it into `dest` (never over live
    data): the restore half of criterion 22. Decrypts with the box's own key;
    from another machine, `age -d -i <your key>` does the same."""
    if shutil.which("age") is None:
        raise ProdError("age is not installed")
    dest.mkdir(parents=True, exist_ok=False)
    with tempfile.TemporaryDirectory(prefix="daydream-offsite-") as tmp:
        sealed = Path(tmp) / name
        _wrangler(["r2", "object", "get", f"{R2_BUCKET}/{name}", "--file", str(sealed), "--remote"])
        plain = Path(tmp) / "backup.tar.gz"
        subprocess.run(["age", "-d", "-i", str(SSH_DIR / "id_ed25519"), "-o", str(plain),
                        str(sealed)], check=True)
        subprocess.run(["tar", "-xzf", str(plain), "-C", str(dest)], check=True)
    say(f"restored {name} into {dest}: " + ", ".join(sorted(p.name for p in dest.iterdir())))
    return 0


# ---- status / logs / pull -------------------------------------------------------------


def status() -> int:
    rel = current_release()
    head = resolve_ref("HEAD")[:12]
    if rel is None:
        say("release: none yet (bin/game prod deploy)")
    else:
        say(f"release: {rel.name} (HEAD {head}; {behind(rel.name, head)})")
    say(f"service: {'awake' if unit_active(UNIT) else 'asleep'} ({UNIT})")
    say(f"tunnel:  {'up' if unit_active(TUNNEL) else 'down'} ({TUNNEL})")
    for name, up in engines_reachable().items():
        say(f"{name}: {'reachable' if up else 'down'}")
    if unit_active(UNIT) and rel is not None:
        say(f"health: {'ok' if http_ok(f'http://127.0.0.1:{port()}/healthz') else 'NOT answering'}")
        cookie = cli_cookie(rel)
        if cookie:
            body = http_ok(f"http://127.0.0.1:{port()}/status/arbiter", headers={"Cookie": cookie})
            if body:
                say(body.strip())
            body = http_ok(f"http://127.0.0.1:{port()}/status/who", headers={"Cookie": cookie})
            if body:
                say(body.strip())
    from daydream import prodcheck

    jobs = prodcheck.timer_checks()
    say("jobs:    " + "; ".join(f"{c.name.removesuffix(' job')} {c.detail}" for c in jobs)
        + ("" if all(c.ok for c in jobs) else "  <- FAILED: journalctl -u daydream-<job>"))
    edge = _edge()
    if edge is not None:
        try:
            say("edge: " + edge.describe_state())
        except (edge.EdgeError, OSError) as e:
            say(f"edge: unknown ({e})")
    else:
        say("edge: not configured (docs/CLOUDFLARE-SETUP.md)")
    return 0


def behind(release: str, head: str) -> str:
    """How far the release is behind HEAD, in words. A release whose commit
    is gone or off HEAD's history (a history rewrite) is reported, not
    raised: status must always print (codereview NOTE 2026-09-28)."""
    if release == head[:len(release)]:
        return "up to date"
    anc = subprocess.run(["git", "-C", str(REPO), "merge-base", "--is-ancestor", release, "HEAD"],
                         capture_output=True)
    if anc.returncode != 0:
        return "not in HEAD's history (a rewrite or another branch): redeploy"
    r = subprocess.run(["git", "-C", str(REPO), "rev-list", "--count", f"{release}..HEAD"],
                       capture_output=True, text=True)
    n = r.stdout.strip() if r.returncode == 0 else "?"
    return f"{n} commit(s) behind"


def logs(follow: bool) -> int:
    args = ["journalctl", "-u", UNIT, "-u", TUNNEL, "--no-pager", "-n", "200"]
    if follow:
        args.append("-f")
    return subprocess.run(args).returncode


def pull() -> int:
    """A fresh prod backup installed as the dev world, to reproduce a friend's
    bug. The dev server must be down; dev's current world is snapshotted first."""
    rel = _require_current()
    backup = _backup(rel)
    if backup is None or not (backup / "live.db").exists():
        raise ProdError("prod has no world to pull")
    dev_game = REPO / "bin" / "game"
    if subprocess.run(["curl", "-s", "-o", "/dev/null", "--max-time", "1",
                       "http://127.0.0.1:54321/healthz"]).returncode == 0:
        raise ProdError("the dev server is up; `bin/game down` first")
    dev_data = Path(os.environ.get("DAYDREAM_DATA_DIR", str(Path.home() / "data" / "daydream")))
    live = dev_data / "worlds-dev" / "live.db"
    if live.exists():
        keep = dev_data / "snapshots" / f"dev-before-pull-{time.strftime('%Y%m%d-%H%M%S')}.db"
        keep.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(live), keep)
        for sfx in ("-wal", "-shm"):
            side = live.with_name(live.name + sfx)
            if side.exists():
                side.unlink()
        say(f"dev world kept at {keep}")
    live.parent.mkdir(parents=True, exist_ok=True)
    # Read by the service user, written by the operator into their own dir.
    live.write_bytes(run_as_prod_bytes(rel, ["cat", str(backup / "live.db")]))
    # Prod's account ids mean nothing in dev: unowned, a friend's toon can be
    # adopted by a dev account to reproduce their bug (codereview WARN 2026-09-28).
    conn = sqlite3.connect(str(live))
    try:
        with conn:
            conn.execute("UPDATE objects SET owner_account = NULL WHERE kind = 'toon'")
    finally:
        conn.close()
    say(f"prod world ({backup.name}) installed as the dev world; `{dev_game} up` to look. "
        "Its toons are unowned here: a dev account adopts one with POST api/slots/<slot>/claim "
        "(GET api/slots lists them to an admin).")
    return 0


# ---- main ------------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in PASSTHROUGH:
        try:
            return passthrough(argv)
        except ProdError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    p = argparse.ArgumentParser(prog="bin/game prod", description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("check", help="live verification of the edge and prod invariants (read-only)")
    d = sub.add_parser("deploy")
    d.add_argument("ref", nargs="?", default="HEAD")
    d.add_argument("--skip-tests", action="store_true",
                   help="skip the short+medium run (only for a ref already tested)")
    sub.add_parser("rollback")
    lg = sub.add_parser("logs")
    lg.add_argument("-f", "--follow", action="store_true")
    sub.add_parser("wake")
    s = sub.add_parser("sleep")
    s.add_argument("--note", default="", help='shown on the asleep page ("back Sunday")')
    s.add_argument("--grace", type=int, default=60, help="seconds of warning for players")
    s.add_argument("--keep-engines", action="store_true", help="leave vLLM and ComfyUI running")
    sub.add_parser("backup")
    sub.add_parser("pull")
    sub.add_parser("keepsakes", help="sync keepsakes to the edge now (the hourly timer runs this)")
    sub.add_parser("offsite", help="encrypted backup to R2 (weekly by timer)")
    orr = sub.add_parser("offsite-restore", help="fetch + decrypt one offsite backup into a new dir")
    orr.add_argument("name", help="object name, e.g. prod-20261004-043000.tar.gz.age")
    orr.add_argument("dest", type=Path, help="a directory that does not exist yet")
    args = p.parse_args(argv)
    try:
        if args.cmd == "status":
            return status()
        if args.cmd == "check":
            from daydream import prodcheck
            return prodcheck.main()
        if args.cmd == "deploy":
            return deploy(args.ref, args.skip_tests)
        if args.cmd == "rollback":
            return rollback()
        if args.cmd == "logs":
            return logs(args.follow)
        if args.cmd == "wake":
            return wake()
        if args.cmd == "sleep":
            return sleep_(args.note, args.grace, args.keep_engines)
        if args.cmd == "backup":
            _backup(_require_current())
            return 0
        if args.cmd == "pull":
            return pull()
        if args.cmd == "keepsakes":
            return keepsakes()
        if args.cmd == "offsite":
            return offsite()
        if args.cmd == "offsite-restore":
            return offsite_restore(args.name, args.dest)
    except (ProdError, subprocess.CalledProcessError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
