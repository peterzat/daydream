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
- `plan [ref]` (read-only: what a deploy of ref ships, and what it needs
  besides the deploy; docs/runbooks/publish.md)
- `deploy [ref] [--skip-tests]`
- `rollback`
- `logs [-f]`
- `wake`
- `sleep [--note TEXT] [--grace SECONDS] [--keep-engines]`
- `backup`
- `keepsakes` (sync keepsakes to the edge; hourly by timer)
- `offsite` / `offsite-restore NAME DEST` (age-encrypted backups in R2; weekly)
- `pull` (a prod backup into dev)
- `root <verb>` (the root-owned helper, /usr/local/sbin/daydream-root: units
  from the release, the timer jobs, allowlisted prod.env keys;
  docs/ADMIN-ROOT.md, docs/runbooks/root.md)
- pass-throughs to the release's `bin/game`: `world`, `dream`, `account`,
  `invite`, `prebake`, `play`

Agent policy: CLAUDE.md "Prod" (the operator's standing grant, and the verbs
that always prompt). Playbooks: docs/runbooks/.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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
PASSTHROUGH = ("world", "dream", "account", "invite", "prebake", "play", "text-scan", "jev")
# The egress gateway (daydream/egress.py, docs/EXTERNAL.md): prod's one way out
# to the hosted services the project declares. Optional: without it, or
# without a key, the village runs its local paths.
EGRESS = "daydream-egress.service"
ROOT_HELPER = Path("/usr/local/sbin/daydream-root")


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


# `bin/game prod <verb> ... --instance NAME` acts on an instance that is not
# the attached one (docs/INSTANCES.md); unset, commands act on the attached
# one. The option comes AFTER the verb, never before it: the agent's
# permission rules match a verb by its prefix (`bin/game prod world reset *`
# always asks), and a leading option would walk around them.
INSTANCE: str | None = None
INSTANCE_NAME = re.compile(r"^[a-z][a-z0-9-]{0,31}$")


def data_root() -> Path:
    """The box's data dir (prod.env's DAYDREAM_DATA_DIR): the GPU lock, the
    service user's HOME, and (with instances) `instances/` and `active`."""
    return Path(prod_env().get("DAYDREAM_DATA_DIR", str(SRV / "data")))


def instance_dir(name: str | None = None) -> Path:
    """The data dir a prod command acts on: `--instance NAME`, else the
    attached instance (the `active` link), else the whole data dir (a box
    not yet migrated to instances). The operator only resolves the link;
    everything inside is read and written as the service user."""
    root = data_root()
    name = name or INSTANCE
    if name:
        if not INSTANCE_NAME.match(name):
            raise ProdError(f"{name!r} is not an instance name")
        d = root / "instances" / name
        if not d.is_dir():
            raise ProdError(f"no instance {name!r} (bin/game prod instance list)")
        return d
    active = root / "active"
    return active.resolve() if active.is_symlink() else root


def data_dir() -> Path:
    """The instance's data dir (backups, the CLI's cookie, what commands touch)."""
    return instance_dir()


def release_env(release: Path, data: Path | None = None) -> dict[str, str]:
    """The clean environment a prod command runs in: prod.env, the release's
    build id, where the engines live, and DAYDREAM_DATA_DIR set to the
    instance's own data dir (so bin/game's bash paths and Python agree; HOME
    stays the box's). The service is started and stopped by this module
    (DAYDREAM_LIFECYCLE=external), never by the command itself."""
    env = {
        "PATH": "/usr/local/bin:/usr/bin:/bin",
        "LANG": "C.UTF-8",
        "PYTHONDONTWRITEBYTECODE": "1",
    }
    env.update(prod_env())
    env["DAYDREAM_DATA_DIR"] = str(data or data_dir())
    env["HOME"] = str(data_root())
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
                       capture: bool = False, data: Path | None = None) -> subprocess.CompletedProcess:
    cmd = as_prod([str(release / ".venv" / "bin" / "python"), *args], release_env(release, data))
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
    _refuse_side_doors(args)
    _refuse_unreadable_paths(args)
    staged = None
    if args[:1] == ["prebake"] and "--from-cache" in args:
        i = args.index("--from-cache")
        staged = _stage_art(Path(args[i + 1]).expanduser())
        args[i + 1] = str(staged)
    was_up = needs_stop(args) and not _detached() and unit_active(UNIT)
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


def _detached() -> bool:
    """`--instance` names an instance the service is not serving: its data
    changes without stopping anyone (codereview WARN 2026-09-28e)."""
    active = data_root() / "active"
    return INSTANCE is not None and not (active.is_symlink() and active.resolve().name == INSTANCE)


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


def _refuse_side_doors(args: list[str]) -> None:
    """A dream reaches the live village only through `dream install`, which
    proves it by rehearsal and stops the service around it. The lower-level
    appliers would change the live DB unproven, under a running service
    (security review 2026-09-29)."""
    key = tuple(args[:2])
    if key == ("world", "patch") and "--check" not in args:
        raise ProdError("in prod a dream goes in by `dream install <patch>` (rehearsed first); "
                        "`world patch` here only checks (--check)")
    if key == ("dream", "apply"):
        raise ProdError("in prod a dream goes in by `dream install <patch>` (rehearsed first)")


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


def egress(action: str) -> bool:
    """Start or stop the egress gateway through the root helper (whose
    vocabulary has it); False, said, when that fails (never fatal)."""
    if not ROOT_HELPER.exists():
        say("egress: the root helper is not installed; the gateway stays as it is")
        return False
    r = subprocess.run(["sudo", "-n", str(ROOT_HELPER), action, EGRESS], capture_output=True,
                       text=True)
    if r.returncode != 0:
        say(f"egress: {action} failed ({(r.stderr or r.stdout).strip()[:160] or r.returncode}); "
            "the village runs its local paths")
        return False
    return True


def egress_routes() -> dict | None:
    """Which of the gateway's routes have a key, or None when it is down."""
    from daydream import config

    body = http_ok(f"{config.EGRESS_URL}/routes", timeout=1.0)
    try:
        return (json.loads(body) or {}).get("routes") if body else None
    except ValueError:
        return None


def egress_line() -> str:
    routes = egress_routes()
    if routes is None:
        return f"egress: {'up but not answering' if unit_active(EGRESS) else 'down'} ({EGRESS})"
    keyed = [n for n, on in routes.items() if on]
    return (f"egress: up ({EGRESS}); routes with a key: {', '.join(keyed) or 'none'}"
            f"{'' if 'jev' in keyed else ' (jev off)'}")


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
    _seal_venv(venv)
    (tmp / ".venv").symlink_to(Path("..") / ".." / "venvs" / venv.name)
    # -I -S: the stdlib's compileall only, never the venv's site (a .pth
    # there would run as the operator).
    subprocess.run([str(venv / "bin" / "python"), "-I", "-S", "-m", "compileall", "-q",
                    str(tmp / "daydream")], check=True, env={"PATH": "/usr/bin:/bin"})
    subprocess.run(["chmod", "-R", "a-w", str(tmp)], check=True)
    os.chmod(tmp, 0o2750)  # the dir itself stays renameable/removable by us
    tmp.rename(release)
    say(f"release {short}: built")
    return release


def _seal_venv(venv: Path) -> None:
    """A venv is the operator's and read-only to everyone else, like a
    release: the setgid parent and a 0002 umask left it writable by the
    service's group, and the operator runs its python on every deploy, so a
    process running as the service user outside its sandbox could plant a
    .pth that ran as the operator (security review 2026-09-29). Refuses a
    venv holding anything the operator does not own, before the chmod (which
    could not change such a file anyway)."""
    me = os.getuid()
    for root, dirs, files in os.walk(venv):
        for name in [*dirs, *files]:
            if os.lstat(os.path.join(root, name)).st_uid != me:
                raise ProdError(f"{venv} holds {os.path.join(root, name)}, which is not "
                                "yours; move the venv aside and deploy again to rebuild it")
    subprocess.run(["chmod", "-R", "go-w", str(venv)], check=True)


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


def _backup(release: Path, data: Path | None = None) -> Path | None:
    r = run_release_python(release, ["-m", "daydream.admin", "backup", "--keep", "14"],
                           check=True, capture=True, data=data)
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


def flag_words(release: Path, data: Path | None = None) -> dict | None:
    """The attached instance's words for the edge's flag (the place, its
    title, the operator's title, the session cookie), computed by the release
    as the service user (docs/INSTANCES.md)."""
    r = run_release_python(release, ["-m", "daydream.instance", "flag-words"], check=False,
                           capture=True, data=data)
    if r.returncode != 0:
        return None
    try:
        words = json.loads(r.stdout)
    except ValueError:
        return None
    return words if isinstance(words, dict) else None


def _set_edge_flag(edge, state: str, note: str | None = "", words: dict | None = None) -> bool:
    """Best effort (codereview WARN 2026-09-28): a Cloudflare API error must
    not abort a sleep or wake half done. An unset asleep flag is covered
    anyway: the Worker reads an unreachable origin as asleep."""
    try:
        edge.set_state(state, note=note, words=words)
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
    if egress("start"):
        say("egress: up")
    systemctl("start", TUNNEL)
    systemctl("start", UNIT)
    if not wait_healthy():
        raise ProdError("the service did not answer /healthz; look at bin/game prod logs")
    say(f"daydream prod {rel.name}: awake on 127.0.0.1:{port()}")
    edge = _edge()
    if edge is not None:
        if _set_edge_flag(edge, "awake", words=flag_words(rel)):
            say("edge: awake")
    else:
        say("edge: not configured yet (docs/CLOUDFLARE-SETUP.md); the edge state is unchanged")
    return 0


def sleep_(note: str, grace: int, keep_engines: bool) -> int:
    rel = _require_current()
    words = flag_words(rel)
    if unit_active(UNIT):
        if grace > 0:
            place = (words or {}).get("place") or "the village"
            text = (f"The lamps are dimming; {place} will sleep in a minute or so. "
                    "What you carry is safe, and your journal will remember today.")
            # Written by the service user (never the operator: the data dir is
            # the sandbox's); the server picks it up within seconds
            # (daydream/announce.py). There is no web endpoint for it.
            run_release_python(rel, ["-m", "daydream.announce", "send", text], check=False)
            say(f"told everyone; waiting {grace}s ...")
            time.sleep(grace)
        edge = _edge()
        if edge is not None and _set_edge_flag(edge, "asleep", note, words):
            say("edge: asleep")
    # Stop both whatever their state: a failed or auto-restarting unit is not
    # "active" yet may be looping; stopping an inactive unit is a no-op.
    systemctl("stop", TUNNEL)
    systemctl("stop", UNIT)
    say("service + tunnel: stopped")
    if unit_active(EGRESS) and egress("stop"):
        say("egress: stopped")
    # Rest everyone and write their journals while the engines are still up
    # (the release's own code, against prod data, with the server stopped).
    r = run_release_python(rel, ["-m", "daydream.admin", "rest-all", "--journal"], check=False,
                           capture=True)
    say(r.stdout.strip() or "rest-all: done")
    edge = _edge()
    if edge is not None:
        _set_edge_flag(edge, "asleep", note, words)  # also when the service was already down
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
    # Every instance, attached or not (docs/INSTANCES.md), each under its own
    # name; a box without instances seals its one data dir as before.
    root = data_root() / "instances"
    dirs = sorted(d for d in root.iterdir() if d.is_dir() and INSTANCE_NAME.match(d.name)) \
        if (data_root() / "active").is_symlink() and root.is_dir() else [data_dir()]
    sent = 0
    for d in dirs:
        backup = _backup(rel, data=d)
        if backup is None:
            say(f"offsite: {d.name}: nothing to back up yet")
            continue
        label = f"{d.name}-" if d.parent == root else ""
        with tempfile.TemporaryDirectory(prefix="daydream-offsite-") as tmp:
            tmpd = Path(tmp)
            name = f"prod-{label}{backup.name}.tar.gz"
            # The service user tars (it owns what is in the data dir); the
            # operator only receives the bytes and encrypts them.
            (tmpd / name).write_bytes(run_as_prod_bytes(rel, ["tar", "-czf", "-", "-C",
                                                              str(backup), "."]))
            sealed = tmpd / (name + ".age")
            subprocess.run(["age", "-R", str(age_recipients(tmpd / "recipients")),
                            "-o", str(sealed), str(tmpd / name)], check=True)
            _wrangler(["r2", "object", "put", f"{R2_BUCKET}/{sealed.name}", "--file",
                       str(sealed), "--remote"])
        say(f"offsite: {sealed.name} -> r2://{R2_BUCKET}")
        sent += 1
    if not sent:
        raise ProdError("nothing to back up yet")
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
    active = data_root() / "active"
    if active.is_symlink():
        words = flag_words(rel) if rel is not None else None
        say(f"instance: {active.resolve().name} ({(words or {}).get('title', '?')}); "
            "others: bin/game prod instance list")
    say(f"service: {'awake' if unit_active(UNIT) else 'asleep'} ({UNIT})")
    say(f"tunnel:  {'up' if unit_active(TUNNEL) else 'down'} ({TUNNEL})")
    say(egress_line())
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


# ---- what a publish ships (docs/runbooks/publish.md) ------------------------------


def _under(path: str, *prefixes: str) -> bool:
    return any(path == p or path.startswith(p.rstrip("/") + "/") for p in prefixes)


def followups(changed: list[str], old_world: str | None, new_world: str | None) -> list[str]:
    """What shipping these changed paths needs besides `prod deploy`, in the
    order to do it. Pure, so the rules are tested rather than remembered."""
    out: list[str] = []
    major = lambda v: (v or "").split(".")[0]  # noqa: E731
    if old_world and new_world and major(old_world) != major(new_world):
        out.append(f"WORLD_VERSION {old_world} -> {new_world} is a MAJOR change: the deploy's "
                   "preflight refuses it. That is a new village (a reset), the operator's "
                   "call: docs/runbooks/reset.md")
    if any(_under(p, "migrations", "migrations_accounts") for p in changed):
        out.append("migrations run at the restart (the deploy backs up first)")
    if "ops/requirements-prod.lock" in changed:
        out.append("a new prod venv is built (a few minutes)")
    dreams = [p for p in changed if re.match(r"worlds/[^/]+/dreams/", p)]
    # Walkthroughs are the tests' replays, not content the live world holds.
    content = sorted({p.split("/")[1].removesuffix(".json") for p in changed
                      if _under(p, "worlds") and p not in dreams
                      and not re.match(r"worlds/[^/]+/walkthroughs/", p)})
    if content or (old_world and new_world and old_world != new_world):
        which = f" ({', '.join(content)} changed)" if content else ""
        out.append(f"content{which}: `bin/game prod world refresh --check`, then "
                   "`bin/game prod world refresh`, if the attached instance plays it")
    if dreams:
        out.append("a dream folder changed: install it after the deploy "
                   "(docs/runbooks/content.md, \"A dream\")")
    if any(_under(p, "edge") for p in changed):
        out.append("the Worker changed: `bin/game edge deploy`")
    if any(_under(p, "ops/systemd") for p in changed):
        out.append("units changed: `bin/game prod root units`, then "
                   "`bin/game prod root units --apply` (it asks)")
    if any(_under(p, "ops/root", "ops/sudoers.d", "ops/install-prod.sh") for p in changed):
        out.append("root-installed files changed: the operator re-runs `sudo ops/install-prod.sh`")
    if "ops/prod.env.example" in changed:
        out.append("prod.env is not touched by a deploy: `bin/game prod root env set KEY VALUE` "
                   "for an allowlisted key, sudo for the rest")
    return out


def world_version_at(commit: str) -> str | None:
    try:
        src = git("show", f"{commit}:daydream/version.py")
    except subprocess.CalledProcessError:
        return None
    m = re.search(r'^WORLD_VERSION\s*=\s*"([0-9]+\.[0-9]+)"', src, re.M)
    return m.group(1) if m else None


def plan(ref: str) -> int:
    """Read-only: what `prod deploy <ref>` would ship over the running
    release, whether it is pushed, and what it needs besides the deploy."""
    sha = resolve_ref(ref)
    rel = current_release()
    say(f"release: {rel.name if rel else 'none yet'}; {ref} is {sha[:12]}")
    if ref == "HEAD" and git("status", "--porcelain"):
        say("the working tree has uncommitted changes: commit them first (prod runs commits)")
    if rel is not None and sha.startswith(rel.name):
        say("nothing to ship: prod already runs it")
        return 0
    pushed = git("branch", "-r", "--contains", sha)
    say("pushed: yes" if pushed else "pushed: not yet (a publish pushes first, through the review gate)")
    # CI on main, so a red run is seen before anything ships (2026-09-29: it
    # failed silently for a day).
    from daydream import ci

    verdict, words = ci.main_status()
    say(f"ci on main: {words}")
    # Jev (daydream/jev), the optional hosted decision model, is on wherever
    # a key is reachable. The first line is this checkout's (.env): zero or
    # not zero, from a paid probe. Prod holds no key (prod.env has none, and
    # the service reaches loopback only); it calls through the egress
    # gateway, whose line says whether its jev route has one.
    from daydream.jev import cli as jev_cli

    say(jev_cli.status_line(probe=True) + " [this checkout's .env]")
    say(egress_line() + " [prod]")
    if verdict == "failed":
        say("  CI is RED on main: fix it before publishing (`bin/game ci`, then "
            "`gh run view <id> --log-failed`)")
    base = rel.name if rel is not None else None
    if base is not None and subprocess.run(
            ["git", "-C", str(REPO), "merge-base", "--is-ancestor", base, sha],
            capture_output=True).returncode == 0:
        say(f"going out ({base[:12]}..{sha[:12]}):")
        for line in git("log", "--oneline", "--no-decorate", f"{base}..{sha}").splitlines():
            say(f"  {line}")
        changed = git("diff", "--name-only", f"{base}..{sha}").splitlines()
    else:
        say("the running release is not in this ref's history: the whole tree ships")
        changed = git("ls-tree", "-r", "--name-only", sha).splitlines()
    todo = followups(changed, world_version_at(base) if base else None, world_version_at(sha))
    if not todo:
        say("then: nothing else; `bin/game prod deploy`, `bin/game prod check`. "
            "Open tabs reload themselves.")
    else:
        say("then, after `bin/game prod deploy`:")
        for step in todo:
            say(f"  - {step}")
        say("and `bin/game prod check`.")
    return 0


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


# ---- root: the validated helper (docs/ADMIN-ROOT.md) ------------------------------------


def root(args: list[str]) -> int:
    """`bin/game prod root <verb> ...`: the root-owned helper through its one
    sudoers line. The helper parses and refuses its own arguments; this only
    hands them over. `doctor` also says when the repo's copy of the helper
    differs from the installed one (only the installer replaces it)."""
    if not ROOT_HELPER.exists():
        raise ProdError(f"{ROOT_HELPER} is not installed: the operator runs sudo ops/install-prod.sh")
    rc = subprocess.run(["sudo", "-n", str(ROOT_HELPER), *args]).returncode
    if args[:1] != ["doctor"]:
        return rc
    installed = _installed_helper_sha()
    repo = hashlib.sha256((REPO / "ops" / "root" / "daydream-root").read_bytes()).hexdigest()
    if installed is None:
        say("helper: could not read the installed helper's version (is its sudoers line "
            "installed? the operator runs sudo ops/install-prod.sh)")
        return rc or 1
    if installed != repo:
        say(f"helper: installed {installed[:12]}, repo {repo[:12]}: the repo's helper is newer: "
            "the operator runs sudo ops/install-prod.sh")
        return rc or 1
    say(f"helper: the installed helper is the repo's ({repo[:12]})")
    return rc


def _installed_helper_sha() -> str | None:
    r = subprocess.run(["sudo", "-n", str(ROOT_HELPER), "version"], capture_output=True, text=True)
    if r.returncode != 0:
        return None
    for line in r.stdout.splitlines():
        if line.startswith("sha256 "):
            return line.split()[1]
    return None


# ---- main ------------------------------------------------------------------------------


# ---- instances (docs/INSTANCES.md) ---------------------------------------------


def _instance_cli(rel: Path, args: list[str]) -> subprocess.CompletedProcess:
    """daydream.instance run by the release as the service user, against the
    box's data dir (it creates, lists and links instances)."""
    return run_release_python(rel, ["-m", "daydream.instance", *args], check=False,
                              capture=True, data=data_root())


def served_instance(release: Path) -> str | None:
    cookie = cli_cookie(release)
    body = http_ok(f"http://127.0.0.1:{port()}/status/build",
                   headers={"Cookie": cookie}) if cookie else None
    for line in (body or "").splitlines():
        if line.startswith("instance: "):
            return line.split(": ", 1)[1].strip()
    return None


def instance_list() -> int:
    rel = _require_current()
    r = _instance_cli(rel, ["list"])
    if r.returncode != 0:
        raise ProdError(r.stderr.strip() or "instance list failed")
    rows = json.loads(r.stdout or "[]")
    if not rows:
        say("no instances: this box serves one data dir (bin/game prod instance migrate)")
        return 0
    for row in rows:
        mark = "*" if row["attached"] else " "
        world = "world" if row["world"] else "no world"
        say(f"{mark} {row['name']:<16} {row['title']}  ({row['place']}; {world})")
    say("(* attached to the public URL)")
    return 0


def instance_create(name: str, words: dict) -> int:
    """A new instance: its dir and instance.json, then its world loaded from
    its envelope (the release's own copy), keyless. Not attached."""
    rel = _require_current()
    if not (data_root() / "active").is_symlink():
        raise ProdError("this box has no instances yet: bin/game prod instance migrate first")
    r = _instance_cli(rel, ["create", name, json.dumps(words)])
    if r.returncode != 0:
        raise ProdError(r.stderr.strip() or "instance create failed")
    d = instance_dir(name)
    envelope = rel / (words.get("envelope") or "worlds/lost-hours.json")
    live = d / f"worlds-{prod_env().get('DAYDREAM_ENV', 'prod')}" / "live.db"
    r = run_release_python(rel, ["-m", "daydream.admin", "load", str(envelope), "--force",
                                 "--output", str(live)], check=False, capture=True, data=d)
    say(r.stdout.strip())
    if r.returncode != 0:
        # Remove the new dir (it holds no world), or a retry fails on "File exists".
        gone = _instance_cli(rel, ["discard", name]).returncode == 0
        raise ProdError(f"the world did not load: {r.stderr.strip()[-300:]}; "
                        + ("the new instance was removed, so a retry starts clean" if gone
                           else f"{d} was left as it is"))
    say(f"created instance {name}; attach it with: bin/game prod instance use {name}")
    return 0


def instance_migrate(name: str) -> int:
    """The one-time move of this box's flat data dir into instances/<name>
    and the active link to it. Backs up first; stops the service around the
    move; restores the flag's words (the session cookie's name changes)."""
    rel = _require_current()
    if (data_root() / "active").is_symlink() or (data_root() / "instances").exists():
        raise ProdError("this box already has instances (bin/game prod instance list)")
    _backup(rel, data=data_root())
    was_up = unit_active(UNIT)
    if was_up:
        say("stopping the service for the move ...")
        systemctl("stop", UNIT)
    try:
        r = _instance_cli(rel, ["migrate", name])
        say(r.stdout.strip())
        if r.returncode != 0:
            raise ProdError(r.stderr.strip() or "migrate failed")
    finally:
        if was_up:
            systemctl("start", UNIT)
            say("service: " + ("back up" if wait_healthy() else "NOT healthy after restart"))
    edge = _edge()
    if edge is not None:
        _set_edge_flag(edge, edge.get_state().get("state", "awake"), note=None,
                       words=flag_words(rel))
        try:
            edge.sync_keepsakes(rel)
        except Exception as e:
            say(f"keepsakes: not synced ({e})")
    say(f"migrated: {name} is attached. Everyone signs in again (the cookie is per instance now).")
    return 0


def instance_use(name: str, grace: int, note: str | None) -> int:
    """Attach another instance to the public URL (the swap). Its state and
    the current one's are kept whole; if anything fails after the stop, the
    previous instance is attached again and started. The flag keeps its note
    unless `note` is given."""
    rel = _require_current()
    link = data_root() / "active"
    if not link.is_symlink():
        raise ProdError("this box has no instances yet: bin/game prod instance migrate first")
    current = link.resolve().name
    target = instance_dir(name)
    if name == current:
        say(f"{name} is already attached")
        return 0
    r = run_release_python(rel, ["-m", "daydream.admin", "preflight"], check=False,
                           capture=True, data=target)
    say(f"preflight {name}: " + " ".join(r.stdout.split()))
    if r.returncode == 3:
        raise ProdError(f"{name}'s world cannot be carried forward by this release "
                        "(WORLD_VERSION MAJOR); nothing changed")
    # A world-less instance would boot on an empty data dir and answer as the
    # target, so the swap would "succeed" with friends in no world at all.
    worlds = [line for line in r.stdout.splitlines()
              if line.startswith("live_world: ") and line != "live_world: missing"]
    if r.returncode != 0 or not worlds:
        raise ProdError(f"{name} has no world to serve (preflight: "
                        f"{'failed' if r.returncode else 'no live world'}); nothing changed. "
                        f"Give it one first: bin/game prod world reset --yes --instance {name}")
    _backup(rel, data=target)
    _backup(rel, data=instance_dir(current))
    was_up = unit_active(UNIT)
    if was_up:
        words = flag_words(rel) or {}
        if grace > 0:
            place = words.get("place") or "the village"
            run_release_python(rel, ["-m", "daydream.announce", "send",
                                     f"The lamps are dimming; {place} will close for a while "
                                     "in a minute or so. What you carry is safe."], check=False)
            say(f"told everyone; waiting {grace}s ...")
            time.sleep(grace)
        systemctl("stop", UNIT)
        r = run_release_python(rel, ["-m", "daydream.admin", "rest-all", "--journal"],
                               check=False, capture=True)
        say(r.stdout.strip() or "rest-all: done")
    try:
        r = _instance_cli(rel, ["attach", name])
        if r.returncode != 0:
            raise ProdError(r.stderr.strip() or "attach failed")
        if was_up:
            systemctl("start", UNIT)
            if not wait_healthy():
                raise ProdError(f"{name} did not answer /healthz")
            served = served_instance(rel)
            if served != name:
                raise ProdError(f"the service answers as {served!r}, not {name!r}")
    except Exception:
        say(f"swap failed; attaching {current} again")
        _instance_cli(rel, ["attach", current])
        if was_up:
            systemctl("restart", UNIT)
            say("service: " + ("back up" if wait_healthy() else "NOT healthy"))
        raise
    edge = _edge()
    if edge is not None:
        state = edge.get_state().get("state", "awake")
        _set_edge_flag(edge, state if state in ("awake", "asleep") else "awake", note,
                       flag_words(rel))
        try:
            edge.sync_keepsakes(rel)
        except Exception as e:
            say(f"keepsakes: not synced ({e})")
    say(f"attached {name} (was {current}); run bin/game prod check")
    return 0


def main(argv: list[str] | None = None) -> int:
    global INSTANCE
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["root"]:
        # The helper's arguments reach it exactly as typed, before --instance
        # is read: the helper has no instances, and `root units --instance x
        # --apply` must not arrive as `units --apply` around the ask rule on
        # `prod root units --apply` (the helper refuses it as a usage error).
        try:
            return root(argv[1:])
        except ProdError as e:
            print(f"error: {e}", file=sys.stderr)
            return 1
    if argv[:1] == ["--instance"]:
        print("put --instance after the verb: bin/game prod <verb> ... --instance NAME "
              "(the permission rules read the verb first)", file=sys.stderr)
        return 2
    if "--instance" in argv:
        # Act on an instance that is not the attached one (an invite before
        # it is up, its backup, its world). Only as the LAST two arguments:
        # anywhere inside the command it could split a two-word verb
        # (`world --instance x reset`) past its ask rule (codereview
        # 2026-09-28d).
        i = argv.index("--instance")
        if (i != len(argv) - 2 or argv.count("--instance") != 1
                or not INSTANCE_NAME.match(argv[i + 1])):
            print("usage: bin/game prod <verb> ... --instance NAME (the last two "
                  "arguments, so the permission rules read the whole verb)", file=sys.stderr)
            return 2
        # Only the verbs that act on one instance's data take it: the others
        # (sleep, deploy, keepsakes, instance use, ...) act on the attached one
        # and would retarget half their work (codereview WARN 2026-09-28e).
        if argv[0] not in (*PASSTHROUGH, "backup"):
            print(f"--instance applies only to {', '.join(PASSTHROUGH)} and backup; "
                  f"`{argv[0]}` does not take it", file=sys.stderr)
            return 2
        INSTANCE, argv = argv[i + 1], argv[:i]
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
    pl = sub.add_parser("plan", help="what a deploy of ref ships, and what else it needs (read-only)")
    pl.add_argument("ref", nargs="?", default="HEAD")
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
    ins = sub.add_parser("instance", help="several instances behind one door (docs/INSTANCES.md)")
    isub = ins.add_subparsers(dest="icmd", required=True)
    isub.add_parser("list", help="the instances, and which is attached")
    im = isub.add_parser("migrate", help="one time: move this flat data dir into an instance")
    im.add_argument("name", nargs="?", default="village")
    ic = isub.add_parser("create", help="a new instance with its world (not attached)")
    ic.add_argument("name")
    for flag in ("envelope", "title", "place", "lede", "operator", "door-image", "invite-blurb"):
        ic.add_argument(f"--{flag}", default=None)
    iu = isub.add_parser("use", help="attach an instance to the public URL (the swap)")
    iu.add_argument("name")
    iu.add_argument("--grace", type=int, default=60, help="seconds of warning for players")
    iu.add_argument("--note", default=None,
                    help="the asleep page's note while it is closed (default: keep the flag's)")
    # `root` is dispatched above, before --instance is read; listed here for --help.
    rt = sub.add_parser("root", help="root actions through the validated helper "
                                     "(docs/runbooks/root.md)")
    rt.add_argument("args", nargs=argparse.REMAINDER,
                    help="version | doctor | units [--apply] | start|stop|restart|status UNIT "
                         "| env show | env set KEY VALUE")
    args = p.parse_args(argv)
    try:
        if args.cmd == "status":
            return status()
        if args.cmd == "check":
            from daydream import prodcheck
            return prodcheck.main()
        if args.cmd == "plan":
            return plan(args.ref)
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
        if args.cmd == "instance":
            if args.icmd == "list":
                return instance_list()
            if args.icmd == "migrate":
                return instance_migrate(args.name)
            if args.icmd == "create":
                words = {k.replace("-", "_"): v for k, v in vars(args).items()
                         if k in ("envelope", "title", "place", "lede", "operator",
                                  "door_image", "invite_blurb") and v is not None}
                return instance_create(args.name, words)
            if args.icmd == "use":
                return instance_use(args.name, args.grace, args.note)
    except (ProdError, subprocess.CalledProcessError, OSError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
