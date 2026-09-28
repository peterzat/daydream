"""ops/root/daydream-root, the root helper (docs/ADMIN-ROOT.md).

The unit validator against the committed units and hostile variants, prod.env
through `env set`, the verbs' vocabulary, and the rule that nothing from the
release or the repo ever runs as root. Everything runs in a scratch tree with
subprocess faked: no sudo, no systemd, nothing under /etc or /srv."""

import ast
import hashlib
import importlib.util
import os
import re
import shutil
import subprocess
import types
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

REPO = Path(__file__).resolve().parent.parent
HELPER = REPO / "ops" / "root" / "daydream-root"
UNITS_DIR = REPO / "ops" / "systemd"
OPERATOR, REPO_PATH = "tester", "/home/tester/src/daydream"
RELEASE = "abcdef123456"


def _load():
    loader = SourceFileLoader("daydream_root", str(HELPER))
    spec = importlib.util.spec_from_loader("daydream_root", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


root = _load()

PROD, BACKUP = "daydream-prod.service", "daydream-backup.service"
TUNNEL, KEEP = "cloudflared-daydream.service", "daydream-keepsakes.service"
BACKUP_TIMER = "daydream-backup.timer"


def rendered(name: str) -> str:
    return root.render(name, (UNITS_DIR / name).read_text(), root.Conf(OPERATOR, REPO_PATH))


def problems(name: str, text: str) -> list[str]:
    return root.validate_unit(name, text, OPERATOR, REPO_PATH)


def add(text: str, line: str, section: str = "[Service]") -> str:
    """`line` placed first in `section`."""
    assert section + "\n" in text
    return text.replace(section + "\n", f"{section}\n{line}\n", 1)


def swap(old: str, new: str):
    def change(text: str) -> str:
        assert old in text, old
        return text.replace(old, new, 1)
    return change


# ---- the committed units -------------------------------------------------------------


def test_the_helper_knows_exactly_the_committed_units():
    assert set(root.UNITS) == {f.name for f in UNITS_DIR.iterdir()}


@pytest.mark.parametrize("name", sorted(p.name for p in UNITS_DIR.iterdir()))
def test_every_committed_unit_validates_clean(name):
    assert problems(name, rendered(name)) == []


def test_rendering_fills_the_operator_jobs_like_the_installer():
    text = rendered(KEEP)
    assert f"User={OPERATOR}" in text and f"ExecStart={REPO_PATH}/bin/game prod keepsakes" in text
    assert "@" not in text
    assert rendered(PROD) == (UNITS_DIR / PROD).read_text()  # the rest go in verbatim


# ---- hostile variants: each refused, with a problem that says why ------------------------

HOSTILE = [
    ("User=root", PROD, swap("User=daydream", "User=root"), ["User=root"]),
    ("no User=", PROD, swap("User=daydream\n", ""), ["User= is missing"]),
    ("operator job as root", KEEP, swap(f"User={OPERATOR}", "User=root"), ["User=root"]),
    ("operator job as someone else", KEEP, swap(f"User={OPERATOR}", "User=daydream"),
     [f"must be {OPERATOR}"]),
    ("operator job with no User=", KEEP, swap(f"User={OPERATOR}\n", ""), ["User= is missing"]),
    ("tunnel as root", TUNNEL, lambda t: add(t, "User=root"), ["User=root"]),
    ("tunnel with a User=", TUNNEL, lambda t: add(t, "User=nobody"), ["User= is not allowed"]),
    ("tunnel without DynamicUser", TUNNEL, swap("DynamicUser=yes\n", ""),
     ["DynamicUser= is missing"]),
    ("a later empty User= (root)", PROD, swap("Group=daydream\n", "Group=daydream\nUser=\n"),
     ["appears more than once"]),
    ("a second [Service]", PROD, lambda t: t + "\n[Service]\nUser=root\n",
     ["User=root", "appears more than once"]),
    ("ExecStart=+", BACKUP, lambda t: re.sub(r"ExecStart=.*", "ExecStart=+/bin/sh", t),
     ["privilege prefix"]),
    ("ExecStartPre=!", PROD, lambda t: add(t, "ExecStartPre=!/bin/true"),
     ["privilege prefix", "ExecStartPre= is not allowed"]),
    ("ExecStart=!!", BACKUP,
     lambda t: re.sub(r"ExecStart=.*", "ExecStart=!!/srv/daydream/current/.venv/bin/python", t),
     ["privilege prefix"]),
    ("a program outside the release", BACKUP,
     lambda t: re.sub(r"ExecStart=.*", "ExecStart=/bin/sh -c id", t),
     ["must run a program under /srv/daydream/current/"]),
    ("a path climbing out of the release", BACKUP,
     lambda t: re.sub(r"ExecStart=.*", "ExecStart=/srv/daydream/current/../../../bin/sh", t),
     ["must run a program under"]),
    ("AmbientCapabilities=CAP_SYS_ADMIN", PROD,
     swap("AmbientCapabilities=\n", "AmbientCapabilities=CAP_SYS_ADMIN\n"),
     ["AmbientCapabilities=CAP_SYS_ADMIN"]),
    ("AmbientCapabilities where none is allowed", BACKUP,
     lambda t: add(t, "AmbientCapabilities=CAP_NET_ADMIN"), ["AmbientCapabilities= is not allowed"]),
    ("CapabilityBoundingSet=CAP_SYS_ADMIN", PROD,
     swap("CapabilityBoundingSet=\n", "CapabilityBoundingSet=CAP_SYS_ADMIN\n"),
     ["CapabilityBoundingSet=CAP_SYS_ADMIN"]),
    ("SupplementaryGroups=docker", PROD, lambda t: add(t, "SupplementaryGroups=docker"),
     ["SupplementaryGroups"]),
    ("PermissionsStartOnly", BACKUP, lambda t: add(t, "PermissionsStartOnly=yes"),
     ["PermissionsStartOnly"]),
    ("Group=root", PROD, swap("Group=daydream", "Group=root"), ["Group=root"]),
    ("Group=docker", BACKUP, swap("Group=daydream", "Group=docker"), ["Group=docker"]),
    ("Group= on an operator job", KEEP, lambda t: add(t, "Group=shadow"), ["Group= is not allowed"]),
    ("prod without NoNewPrivileges", PROD, swap("NoNewPrivileges=yes\n", ""),
     ["NoNewPrivileges= is missing"]),
    ("NoNewPrivileges=no", PROD, swap("NoNewPrivileges=yes", "NoNewPrivileges=no"),
     ["NoNewPrivileges=no"]),
    ("ProtectSystem=full", PROD, swap("ProtectSystem=strict", "ProtectSystem=full"),
     ["ProtectSystem=full"]),
    ("ProtectHome=read-only", PROD, swap("ProtectHome=yes", "ProtectHome=read-only"),
     ["ProtectHome=read-only"]),
    ("no PrivateDevices", PROD, swap("PrivateDevices=yes\n", ""), ["PrivateDevices= is missing"]),
    ("a wider write path", PROD, swap("ReadWritePaths=/srv/daydream/data", "ReadWritePaths=/"),
     ["ReadWritePaths=/"]),
    ("egress beyond loopback", PROD, swap("IPAddressAllow=localhost", "IPAddressAllow=any"),
     ["IPAddressAllow=any"]),
    ("no IPAddressDeny", PROD, swap("IPAddressDeny=any\n", ""), ["IPAddressDeny= is missing"]),
    ("a wider socket family", PROD,
     swap("RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX",
          "RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX AF_PACKET"),
     ["RestrictAddressFamilies"]),
    ("an inverted socket family list", PROD,
     swap("RestrictAddressFamilies=AF_INET AF_INET6 AF_UNIX", "RestrictAddressFamilies=~AF_PACKET"),
     ["RestrictAddressFamilies"]),
    ("a looser syscall filter", PROD,
     swap("SystemCallFilter=@system-service", "SystemCallFilter=~@mount"), ["SystemCallFilter"]),
    ("EnvironmentFile=/etc/shadow", PROD, lambda t: add(t, "EnvironmentFile=/etc/shadow"),
     ["EnvironmentFile=/etc/shadow"]),
    ("the tunnel token into prod", PROD,
     lambda t: add(t, "EnvironmentFile=/etc/cloudflared/daydream.env"),
     ["EnvironmentFile=/etc/cloudflared/daydream.env"]),
    ("prod.env into the tunnel", TUNNEL,
     swap("EnvironmentFile=/etc/cloudflared/daydream.env", "EnvironmentFile=/srv/daydream/etc/prod.env"),
     ["EnvironmentFile=/srv/daydream/etc/prod.env"]),
    ("prod without prod.env", PROD, swap("EnvironmentFile=/srv/daydream/etc/prod.env\n", ""),
     ["must include /srv/daydream/etc/prod.env"]),
    ("an unknown key", PROD, lambda t: add(t, "Foo=bar"), ["[Service] Foo= is not allowed"]),
    ("LoadCredential", PROD, lambda t: add(t, "LoadCredential=s:/etc/shadow"), ["LoadCredential"]),
    ("output into a root file", BACKUP, lambda t: add(t, "StandardOutput=file:/etc/passwd"),
     ["StandardOutput"]),
    ("a specifier", PROD, swap("WorkingDirectory=/srv/daydream/current", "WorkingDirectory=%h"),
     ["specifiers"]),
    ("pulling in another unit", PROD, swap("Wants=network-online.target", "Wants=reboot.target"),
     ["Wants=reboot.target"]),
    ("the backup enabled at boot", BACKUP, lambda t: t + "\n[Install]\nWantedBy=multi-user.target\n",
     ["[Install] WantedBy= is not allowed"]),
    ("an operator job not run by the repo's bin/game", KEEP,
     swap(f"ExecStart={REPO_PATH}/bin/game", "ExecStart=/tmp/game"),
     ["ExecStart=/tmp/game", f"must be exactly {REPO_PATH}/bin/game prod keepsakes"]),
    ("an operator job running another verb", KEEP,
     swap("bin/game prod keepsakes", "bin/game prod world reset --yes"), ["ExecStart="]),
    ("the tunnel given a local ingress", TUNNEL,
     swap("tunnel run", "tunnel --url http://127.0.0.1:22 run"), ["ExecStart="]),
    ("a timer that runs another unit", BACKUP_TIMER,
     lambda t: add(t, "Unit=daydream-prod.service", "[Timer]"), ["[Timer] Unit= is not allowed"]),
    ("a timer wanted at boot", BACKUP_TIMER,
     swap("WantedBy=timers.target", "WantedBy=multi-user.target"), ["WantedBy=multi-user.target"]),
    ("whitespace after a continuing backslash", PROD, lambda t: add(t, "Environment=A=1 \\ "),
     ["whitespace after a line-continuing backslash"]),
    ("carriage returns", PROD, lambda t: t.replace("\n", "\r\n"), ["control characters"]),
    ("a line systemd reads another way", PROD, lambda t: add(t, ".include /etc/evil.conf"),
     ["not a KEY=VALUE line"]),
    ("a key before any section", PROD, lambda t: "User=root\n" + t, ["before any [Section]"]),
]


@pytest.mark.parametrize("label,name,change,needles", HOSTILE, ids=[h[0] for h in HOSTILE])
def test_a_hostile_unit_is_refused_with_a_clear_problem(label, name, change, needles):
    got = problems(name, change(rendered(name)))
    assert got, f"{label}: accepted"
    joined = "\n".join(got)
    for needle in needles:
        assert needle in joined, joined
    assert all(p.startswith(name) for p in got), got  # each problem names its unit


def test_an_unreadable_unit_is_one_problem_not_a_flood():
    (p,) = problems(PROD, rendered(PROD).replace("\n", "\r\n"))
    assert "control characters" in p and "on 71 line(s)" in p


def test_an_unknown_unit_name_is_refused():
    (p,) = problems("sshd.service", "[Service]\nExecStart=/usr/sbin/sshd\n")
    assert "not a unit this helper manages" in p


# ---- the parser reads a unit the way systemd does ------------------------------------------


def test_a_continued_line_joins_across_comments():
    entries, probs = root.parse_unit("[Service]\nExecStart=/a \\\n# c\n; d\n  --flag\nUser=x\n")
    assert probs == []
    assert entries == [(2, "Service", "ExecStart", "/a    --flag"), (6, "Service", "User", "x")]


def test_a_continued_line_swallows_the_next_as_systemd_does():
    """systemd reads this User=root as part of the Description, so it must
    not be read (or refused) as a directive here either."""
    entries, probs = root.parse_unit("[Unit]\nDescription=x \\\nUser=root\n")
    assert probs == [] and entries == [(2, "Unit", "Description", "x  User=root")]


def test_an_escaped_backslash_does_not_continue():
    entries, _ = root.parse_unit("[Unit]\nDescription=a\\\\\nAfter=b\n")
    assert [e[2] for e in entries] == ["Description", "After"]


def test_a_continuation_off_the_end_is_a_problem():
    _, probs = root.parse_unit("[Unit]\nDescription=a \\")
    assert any("runs off the end" in p for p in probs)


def test_whitespace_around_keys_is_stripped_as_systemd_does():
    entries, _ = root.parse_unit("[Service]\n  User = root  \n")
    assert entries == [(2, "Service", "User", "root")]
    assert any("User=root" in p for p in problems(PROD, rendered(PROD).replace(
        "User=daydream", "User = root")))


# ---- a scratch box ---------------------------------------------------------------------------


@pytest.fixture
def box(tmp_path, monkeypatch):
    """/etc and /srv/daydream in miniature, the release's units copied from
    the repo, subprocess recorded (every command succeeds)."""
    base = tmp_path.resolve()
    conf_dir = base / "etc" / "daydream"
    systemd = base / "etc" / "systemd" / "system"
    sudoers_d = base / "etc" / "sudoers.d"
    srv = base / "srv" / "daydream"
    release_units = srv / "releases" / RELEASE / "ops" / "systemd"
    for d in (conf_dir, systemd, sudoers_d, release_units, srv / "etc"):
        d.mkdir(parents=True)
    (conf_dir / "root.conf").write_text(f"# test\nOPERATOR={OPERATOR}\nREPO={REPO_PATH}\n")
    (sudoers_d / "daydream").write_text(
        f"{OPERATOR} ALL=(root) NOPASSWD: /usr/local/sbin/daydream-root\n")
    for f in UNITS_DIR.iterdir():
        shutil.copyfile(f, release_units / f.name)
    (srv / "current").symlink_to(Path("releases") / RELEASE)
    shutil.copyfile(REPO / "ops" / "prod.env.example", srv / "etc" / "prod.env")
    for d in (conf_dir, systemd, sudoers_d):
        os.chmod(d, 0o755)
    os.chmod(srv / "etc", 0o750)
    os.chmod(conf_dir / "root.conf", 0o644)
    os.chmod(sudoers_d / "daydream", 0o440)
    os.chmod(srv / "etc" / "prod.env", 0o640)
    monkeypatch.setattr(root, "SRV", str(srv))
    monkeypatch.setattr(root, "SYSTEMD_DIR", str(systemd))
    monkeypatch.setattr(root, "ROOT_CONF", str(conf_dir / "root.conf"))
    monkeypatch.setattr(root, "SUDOERS", str(sudoers_d / "daydream"))
    chowns = []
    monkeypatch.setattr(root, "_chown", lambda fd, uid, gid: chowns.append((uid, gid)))
    monkeypatch.setattr(root, "_service_gid", lambda: 4242)
    monkeypatch.setattr(root, "_service_user_groups", lambda: {"daydream"})
    calls, kwargs = [], []
    results = {}

    def fake_run(cmd, **kw):
        calls.append(list(cmd))
        kwargs.append(kw)
        rc, out = results.get(cmd[0], (0, "[]\n"))
        return subprocess.CompletedProcess(cmd, rc, stdout=out, stderr="")

    monkeypatch.setattr(root.subprocess, "run", fake_run)
    return types.SimpleNamespace(srv=srv, systemd=systemd, conf=conf_dir / "root.conf",
                                 sudoers=sudoers_d / "daydream", release_units=release_units,
                                 prod_env=srv / "etc" / "prod.env", calls=calls, kwargs=kwargs,
                                 chowns=chowns, results=results)


def _logged(box) -> list[str]:
    return [c[-1] for c in box.calls if c[0] == root.LOGGER]


def _systemctl(box) -> list[list[str]]:
    return [c[1:] for c in box.calls if c[0] == root.SYSTEMCTL]


# ---- units --------------------------------------------------------------------------------------


def test_units_shows_the_difference_and_changes_nothing(box, capsys):
    assert root.main(["units"]) == 0
    out = capsys.readouterr().out
    assert f"release {RELEASE}" in out and "(not installed)" in out
    assert "+User=daydream" in out and "8 unit(s) differ" in out
    assert list(box.systemd.iterdir()) == [] and box.calls == []


def test_units_apply_installs_logs_reloads_and_enables_the_timers(box, capsys):
    assert root.main(["units", "--apply"]) == 0
    for name in root.UNITS:
        installed = box.systemd / name
        assert installed.read_text() == rendered(name)
        assert installed.stat().st_mode & 0o777 == 0o644
    assert box.chowns == [(0, 0)] * len(root.UNITS)
    assert ["daemon-reload"] in _systemctl(box)
    assert ["enable", "--now", *root.TIMERS] in _systemctl(box)
    logged = _logged(box)
    for name in root.UNITS:
        sha = hashlib.sha256(rendered(name).encode()).hexdigest()
        assert f"units: installed {name} sha256={sha} from release {RELEASE}" in logged
    assert not [p for p in box.systemd.iterdir() if p.name.startswith(".")]  # no temp left
    # A second run finds nothing to install and does not reload.
    box.calls.clear()
    capsys.readouterr()
    assert root.main(["units", "--apply"]) == 0
    out = capsys.readouterr().out
    assert all(f"{name}: up to date" in out for name in root.UNITS)
    assert ["daemon-reload"] not in _systemctl(box)
    assert not [line for line in _logged(box) if line.startswith("units: installed")]


def test_units_apply_replaces_only_what_changed(box):
    for name in root.UNITS:
        (box.systemd / name).write_text(rendered(name))
    (box.systemd / PROD).write_text("[Unit]\nDescription=old\n")
    assert root.main(["units", "--apply"]) == 0
    assert [line for line in _logged(box) if line.startswith("units: installed")] == [
        f"units: installed {PROD} sha256={hashlib.sha256(rendered(PROD).encode()).hexdigest()} "
        f"from release {RELEASE}"]


def test_a_hostile_release_installs_nothing(box, capsys):
    unit = box.release_units / PROD
    unit.write_text(unit.read_text().replace("User=daydream", "User=root"))
    assert root.main(["units", "--apply"]) == 1
    assert "User=root" in capsys.readouterr().out
    assert list(box.systemd.iterdir()) == [] and box.calls == []


def test_a_unit_the_helper_does_not_know_blocks_the_release(box, capsys):
    (box.release_units / "daydream-evil.service").write_text("[Service]\nExecStart=/bin/sh\n")
    assert root.main(["units", "--apply"]) == 1
    assert "does not know: daydream-evil.service" in capsys.readouterr().out
    assert list(box.systemd.iterdir()) == []


def test_a_release_unit_that_is_a_symlink_is_not_followed(box, capsys):
    unit = box.release_units / PROD
    unit.unlink()
    unit.symlink_to("/etc/passwd")
    assert root.main(["units"]) == 1
    out = capsys.readouterr().out
    assert "symlink" in out and "root:x:0:0" not in out


def test_a_symlinked_directory_in_the_release_is_not_followed(box, capsys):
    real = box.release_units.parent / "real-systemd"
    box.release_units.rename(real)
    box.release_units.symlink_to(real)
    assert root.main(["units"]) == 1
    assert "symlink" in capsys.readouterr().err


def test_current_must_name_a_release(box, capsys):
    (box.srv / "current").unlink()
    (box.srv / "current").symlink_to("/home/tester/src/daydream")
    assert root.main(["units"]) == 1
    assert "not releases/<sha>" in capsys.readouterr().err


def test_an_installed_unit_that_is_a_symlink_blocks_apply(box):
    (box.systemd / PROD).symlink_to("/dev/null")  # masked by hand
    assert root.main(["units", "--apply"]) == 1
    assert (box.systemd / PROD).is_symlink() and box.calls == []


# ---- root.conf ------------------------------------------------------------------------------------


@pytest.mark.parametrize("text,needle", [
    ("OPERATOR=root\nREPO=/home/x/src/daydream\n", "OPERATOR='root'"),
    ("OPERATOR=daydream\nREPO=/home/x/src/daydream\n", "OPERATOR='daydream'"),
    ("OPERATOR=x y\nREPO=/home/x/src/daydream\n", "OPERATOR="),
    ("OPERATOR=x\nREPO=/home/x/my repo\n", "REPO="),
    ("OPERATOR=x\nREPO=/home/x/../root\n", "REPO="),
    ("OPERATOR=x\nREPO=relative/path\n", "REPO="),
    ("OPERATOR=x\nREPO=/home/x/%h\n", "REPO="),
    ("OPERATOR=x\nREPO=/a\nOPERATOR=root\n", "once each"),
    ("OPERATOR=x\nREPO=/a\nEXTRA=1\n", "once each"),
])
def test_root_conf_holds_only_plain_facts(box, text, needle, capsys):
    box.conf.write_text(text)
    assert root.main(["units"]) == 1
    assert needle in capsys.readouterr().err


def test_root_conf_must_be_writable_by_root_alone(box, capsys):
    os.chmod(box.conf, 0o664)
    assert root.main(["units"]) == 1
    assert "writable by its group or others" in capsys.readouterr().err


def test_a_missing_root_conf_names_the_installer(box, capsys):
    box.conf.unlink()
    assert root.main(["units"]) == 1
    assert "sudo ops/install-prod.sh" in capsys.readouterr().err


# ---- env ------------------------------------------------------------------------------------------


def test_env_set_replaces_one_line_and_keeps_every_other(box):
    before = box.prod_env.read_text().splitlines(keepends=True)
    assert root.main(["env", "set", "DAYDREAM_OPERATOR_NAME", "the Lamp Keeper"]) == 0
    after = box.prod_env.read_text().splitlines(keepends=True)
    changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
    assert len(before) == len(after) and len(changed) == 1
    assert after[changed[0]] == 'DAYDREAM_OPERATOR_NAME="the Lamp Keeper"\n'
    assert before[changed[0]].startswith("DAYDREAM_OPERATOR_NAME=")
    assert any(line.startswith("#") for line in after)  # comments kept
    assert box.prod_env.stat().st_mode & 0o777 == 0o640
    assert box.chowns == [(0, 4242)]  # root:daydream
    assert any(line.startswith("env set DAYDREAM_OPERATOR_NAME=the Lamp Keeper") for line in _logged(box))


def test_env_set_appends_a_key_not_yet_there(box):
    before = box.prod_env.read_text()
    assert "DAYDREAM_LOG_LEVEL" not in before
    assert root.main(["env", "set", "DAYDREAM_LOG_LEVEL", "DEBUG"]) == 0
    assert box.prod_env.read_text() == before + "DAYDREAM_LOG_LEVEL=DEBUG\n"


def test_env_set_drops_a_later_duplicate_of_the_same_key(box):
    box.prod_env.write_text(box.prod_env.read_text() + "DAYDREAM_MEMORY_ENABLED=1\n")
    assert root.main(["env", "set", "DAYDREAM_MEMORY_ENABLED", "0"]) == 0
    lines = box.prod_env.read_text().splitlines()
    assert [line for line in lines if line.startswith("DAYDREAM_MEMORY_ENABLED")] == [
        "DAYDREAM_MEMORY_ENABLED=0"]


@pytest.mark.parametrize("key,value", [
    ("DAYDREAM_LOG_LEVEL", "WARNING"), ("DAYDREAM_LOG_LEVEL", "ERROR"),
    ("DAYDREAM_OPERATOR_NAME", "the Night Warden"), ("DAYDREAM_OPERATOR_NAME", "x" * 60),
    ("DAYDREAM_JOURNAL_ENABLED", "0"), ("DAYDREAM_REGEN_UI", "1"),
    ("DAYDREAM_MEMORY_ENABLED", "1"), ("DAYDREAM_DRIFT_ENABLED", "0"),
    ("DAYDREAM_VILLAGE_ENABLED", "1"), ("DAYDREAM_DIRECTOR_LLM", "0"),
    ("DAYDREAM_LLM_CONCURRENCY", "1"), ("DAYDREAM_LLM_CONCURRENCY", "8"),
])
def test_env_set_takes_the_allowlisted_keys(box, key, value):
    assert root.main(["env", "set", key, value]) == 0
    assert root.parse_env(box.prod_env.read_text())[key] == value


@pytest.mark.parametrize("key", [*root.REFUSED_KEYS, "PATH", "LD_PRELOAD", "DAYDREAM_GPU_LOCK",
                                 "DAYDREAM_PASSWORD_HASH_PROFILE", "daydream_log_level"])
def test_env_set_refuses_the_keys_that_decide_trust_and_anything_unknown(box, key, capsys):
    before = box.prod_env.read_text()
    assert root.main(["env", "set", key, "1"]) == 1
    err = capsys.readouterr().err
    assert ("stays with the operator" if key in root.REFUSED_KEYS else "not a key env set manages") in err
    assert box.prod_env.read_text() == before and box.calls == []


@pytest.mark.parametrize("key,value", [
    ("DAYDREAM_LOG_LEVEL", "debug"), ("DAYDREAM_LOG_LEVEL", "TRACE"), ("DAYDREAM_LOG_LEVEL", ""),
    ("DAYDREAM_OPERATOR_NAME", 'the "Warden"'), ("DAYDREAM_OPERATOR_NAME", "it's"),
    ("DAYDREAM_OPERATOR_NAME", "a\nDAYDREAM_ACCESS=public"), ("DAYDREAM_OPERATOR_NAME", "x" * 61),
    ("DAYDREAM_OPERATOR_NAME", "$HOME"), ("DAYDREAM_OPERATOR_NAME", "a\\b"),
    ("DAYDREAM_OPERATOR_NAME", ""), ("DAYDREAM_OPERATOR_NAME", " padded"),
    ("DAYDREAM_OPERATOR_NAME", "tab\there"), ("DAYDREAM_OPERATOR_NAME", "rtl\u202eoverride"),
    ("DAYDREAM_JOURNAL_ENABLED", "yes"), ("DAYDREAM_JOURNAL_ENABLED", "1\n"),
    ("DAYDREAM_REGEN_UI", "2"), ("DAYDREAM_LLM_CONCURRENCY", "0"),
    ("DAYDREAM_LLM_CONCURRENCY", "9"), ("DAYDREAM_LLM_CONCURRENCY", "3.5"),
    ("DAYDREAM_LLM_CONCURRENCY", "-1"), ("DAYDREAM_LLM_CONCURRENCY", "4 "),
])
def test_env_set_refuses_a_bad_value(box, key, value):
    before = box.prod_env.read_text()
    assert root.main(["env", "set", key, value]) == 1
    assert box.prod_env.read_text() == before and box.calls == []


def test_the_boot_guard_runs_as_the_service_user_before_anything_is_written(box):
    assert root.main(["env", "set", "DAYDREAM_LOG_LEVEL", "DEBUG"]) == 0
    guard, = [c for c in box.calls if c[0] == root.RUNUSER]
    assert guard[:8] == [root.RUNUSER, "-u", "daydream", "--", "/usr/bin/env", "-i", "-C",
                         "/srv/daydream/current"]
    assert "DAYDREAM_LOG_LEVEL=DEBUG" in guard  # the proposed file, not the old one
    assert "DAYDREAM_ACCESS=edge" in guard and "DAYDREAM_OPERATOR_NAME=the Night Warden" in guard
    assert guard[-3:] == ["/srv/daydream/current/.venv/bin/python", "-c", root.BOOT_GUARD]
    assert "config.boot_problems()" in root.BOOT_GUARD
    assert box.calls.index(guard) < next(i for i, c in enumerate(box.calls) if c[0] == root.LOGGER)


def test_env_set_refuses_when_the_boot_guard_does(box, capsys):
    before = box.prod_env.read_text()
    box.results[root.RUNUSER] = (1, "['prod must bind loopback']\n")
    assert root.main(["env", "set", "DAYDREAM_LOG_LEVEL", "DEBUG"]) == 1
    assert "prod must bind loopback" in capsys.readouterr().err
    assert box.prod_env.read_text() == before and _logged(box) == []


def test_env_set_refuses_a_prod_env_it_cannot_trust(box):
    os.chmod(box.prod_env, 0o660)  # group-writable: not root's alone
    assert root.main(["env", "set", "DAYDREAM_LOG_LEVEL", "DEBUG"]) == 1
    assert box.calls == []


def test_env_show_prints_the_file(box, capsys):
    assert root.main(["env", "show"]) == 0
    assert capsys.readouterr().out == box.prod_env.read_text()


# ---- the unit verbs, usage, version, doctor -------------------------------------------------------


def test_start_stop_restart_and_status_work_on_the_daydream_units_only(box):
    assert root.main(["restart", PROD]) == 0
    assert root.main(["start", "daydream-keepsakes.service"]) == 0
    assert root.main(["status", BACKUP_TIMER]) == 0
    assert _systemctl(box) == [["restart", PROD], ["start", "daydream-keepsakes.service"],
                               ["status", "--no-pager", BACKUP_TIMER]]
    assert _logged(box) == [f"restart {PROD}: exit 0", "start daydream-keepsakes.service: exit 0",
                            f"status {BACKUP_TIMER}: exit 0"]
    box.calls.clear()
    for argv in (["start", BACKUP_TIMER], ["stop", "sshd.service"], ["restart", "../x.service"],
                 ["status", "docker.service"], ["start", f"{PROD} --now"]):
        assert root.main(argv) == 2, argv
    assert box.calls == []


@pytest.mark.parametrize("argv", [
    [], ["bogus"], ["units", "--force"], ["units", "--apply", "x"], ["units", "--app"],
    ["env"], ["env", "edit"], ["env", "set", "DAYDREAM_LOG_LEVEL"],
    ["env", "set", "DAYDREAM_LOG_LEVEL", "DEBUG", "x"], ["start"], ["doctor", "x"],
    ["version", "--sha"], ["--help"],
])
def test_anything_else_is_a_usage_error(argv, capsys):
    assert root.main(argv) == 2
    assert "usage: daydream-root" in capsys.readouterr().err


def test_version_prints_its_own_sha256(capsys):
    assert root.main(["version"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out == [f"daydream-root {root.VERSION}",
                   f"sha256 {hashlib.sha256(HELPER.read_bytes()).hexdigest()}"]


def test_doctor_is_quiet_when_all_is_well(box, capsys):
    assert root.main(["units", "--apply"]) == 0
    box.calls.clear()
    assert root.main(["doctor"]) == 0
    out = capsys.readouterr().out
    assert "doctor: all well" in out and f"units: {PROD}: matches release {RELEASE}" in out
    assert _logged(box) == [] and _systemctl(box) == []  # read-only


def test_doctor_names_what_needs_attention(box, monkeypatch, capsys):
    (box.systemd / f"{PROD}.d").mkdir()
    box.sudoers.chmod(0o640)
    box.sudoers.write_text("# the old entry, without the helper\n")
    box.sudoers.chmod(0o440)
    monkeypatch.setattr(root, "_service_user_groups", lambda: {"daydream", "docker"})
    assert root.main(["doctor"]) == 1
    out = capsys.readouterr().out
    assert f"units: {PROD}: not installed" in out
    assert "does not name /usr/local/sbin/daydream-root" in out
    assert "privileged: docker" in out
    assert f"{PROD}.d exists" in out


# ---- nothing from the release or the repo runs as root ------------------------------------------

STDLIB = {"__future__", "difflib", "grp", "hashlib", "os", "pwd", "re", "stat", "subprocess", "sys"}


def _tree():
    return ast.parse(HELPER.read_text())


def test_the_helper_is_isolated_stdlib_python():
    lines = HELPER.read_text().splitlines()
    assert lines[0] == "#!/usr/bin/python3 -I"
    assert os.access(HELPER, os.X_OK)
    imported = set()
    for node in ast.walk(_tree()):
        if isinstance(node, ast.Import):
            imported |= {a.name.split(".")[0] for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= STDLIB, imported - STDLIB  # never the release's or the repo's code


def test_the_helper_runs_commands_in_one_place_and_reads_no_environment():
    """Every subprocess call sits in _run (which admits only the system tools
    and drops to the service user for anything else); nothing execs, spawns,
    evals or reads the caller's environment."""
    tree = _tree()
    run_fn = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "_run")
    inside_run = {id(n) for n in ast.walk(run_fn)}
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
            if node.value.id == "subprocess" and node.attr not in (
                    "CompletedProcess", "DEVNULL", "SubprocessError"):
                assert id(node) in inside_run, f"subprocess.{node.attr} outside _run (line {node.lineno})"
            if node.value.id == "os":
                assert not node.attr.startswith(("exec", "spawn", "posix_spawn", "system", "popen",
                                                 "environ", "getenv", "putenv", "fork")), node.attr
        if isinstance(node, ast.Name):
            assert node.id not in ("eval", "exec", "compile", "__import__", "environ"), node.id


def test_run_admits_only_the_system_tools(box):
    for cmd in (["/srv/daydream/current/bin/game", "prod"], [f"{REPO_PATH}/bin/game", "prod"],
                ["systemctl", "start", PROD], ["/bin/sh", "-c", "id"],
                [root.RUNUSER, "-u", "root", "--", "/usr/bin/env"],
                [root.RUNUSER, "-u", "daydream", "--", "/srv/daydream/current/.venv/bin/python"],
                [root.SYSTEMCTL, "link", "/srv/daydream/current/ops/systemd/x.service"],
                [root.LOGGER, "-f", "/etc/shadow"]):
        with pytest.raises(root.HelperError):
            root._run(cmd)
    assert box.calls == []


def test_every_command_the_helper_runs_is_a_system_tool_or_the_service_user(box):
    """Drive every verb and look at what reached subprocess: the release and
    the repo appear only in a command that has already dropped to daydream."""
    for argv in (["units", "--apply"], ["env", "set", "DAYDREAM_LOG_LEVEL", "INFO"],
                 ["restart", PROD], ["status", BACKUP_TIMER], ["doctor"], ["env", "show"]):
        root.main(argv)
    assert box.calls
    for cmd, kw in zip(box.calls, box.kwargs):
        assert cmd[0] in (root.SYSTEMCTL, root.LOGGER, root.RUNUSER), cmd
        assert kw["env"] == root.CLEAN_ENV and kw["cwd"] == "/"
        if any("/srv/daydream" in a or str(box.srv) in a or REPO_PATH in a for a in cmd):
            assert cmd[:5] == [root.RUNUSER, "-u", "daydream", "--", "/usr/bin/env"], cmd
