"""The systemd units under ops/ (installed by ops/install-prod.sh)."""

import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

UNITS = Path(__file__).resolve().parent.parent / "ops" / "systemd"


@pytest.mark.parametrize("name", ["daydream-keepsakes.service", "daydream-offsite.service"])
def test_operator_jobs_that_drop_to_the_service_user_can_use_sudo(name):
    """`bin/game prod keepsakes|offsite` runs its export as the daydream user
    through sudo; NoNewPrivileges would make that sudo fail, so the timer
    would fail every run while a hand run works (SECURITY WARN 2026-09-28)."""
    text = (UNITS / name).read_text()
    assert "bin/game prod" in text
    assert not any(line.strip().startswith("NoNewPrivileges=") for line in text.splitlines())


def test_the_prod_service_itself_keeps_no_new_privileges():
    text = (UNITS / "daydream-prod.service").read_text()
    assert "NoNewPrivileges=yes" in text


# ---- the ops files agree with each other and with the code -------------------------

import re  # noqa: E402

from daydream import prodctl  # noqa: E402

OPS = UNITS.parent
REPO = OPS.parent


def _env_file(path: Path) -> dict[str, str]:
    return prodctl.parse_env_file(path)


def _wrangler_vars() -> dict[str, str]:
    text = (REPO / "edge" / "wrangler.toml").read_text()
    block = text.split("[vars]", 1)[1].split("[", 1)[0]
    return dict(re.findall(r'^(\w+)\s*=\s*"([^"]*)"', block, flags=re.M))


def test_sudoers_lets_prodctl_start_and_stop_what_it_manages():
    """prodctl runs `sudo -n /usr/bin/systemctl <action> <unit>`; a unit or
    action missing from the sudoers entry fails only on the box."""
    sudoers = (OPS / "sudoers.d" / "daydream").read_text()
    for unit in (prodctl.UNIT, prodctl.TUNNEL):
        for action in ("start", "stop", "restart"):
            assert f"/usr/bin/systemctl {action} {unit}" in sudoers, (action, unit)
    assert "peter ALL=(daydream) NOPASSWD: ALL" in sudoers  # the privilege drop


def test_sudoers_grants_exactly_the_units_the_service_user_and_the_root_helper():
    """Every rule, pinned: a new one is a review event (docs/ADMIN-ROOT.md)."""
    sudoers = (OPS / "sudoers.d" / "daydream").read_text()
    rules = [line for line in sudoers.splitlines() if line.startswith("peter ")]
    assert rules == ["peter ALL=(root) NOPASSWD: DAYDREAM_UNITS",
                     "peter ALL=(daydream) NOPASSWD: ALL",
                     f"peter ALL=(root) NOPASSWD: {prodctl.ROOT_HELPER}"]
    assert str(prodctl.ROOT_HELPER) == "/usr/local/sbin/daydream-root"


def test_the_sudoers_file_parses():
    """A sudoers syntax error would lock the operator out of sudo."""
    import subprocess

    visudo = "/usr/sbin/visudo"
    if not Path(visudo).exists():
        pytest.skip("visudo is not installed")
    r = subprocess.run([visudo, "-cf", str(OPS / "sudoers.d" / "daydream")],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def _helper_module():
    import importlib.util
    from importlib.machinery import SourceFileLoader

    loader = SourceFileLoader("daydream_root_ops", str(OPS / "root" / "daydream-root"))
    spec = importlib.util.spec_from_loader("daydream_root_ops", loader)
    mod = importlib.util.module_from_spec(spec)
    loader.exec_module(mod)
    return mod


def test_the_installer_installs_the_root_helper_and_a_root_conf_it_accepts(tmp_path, monkeypatch):
    script = (OPS / "install-prod.sh").read_text()
    helper = 'install -o root -g root -m 0755 "$OPS/root/daydream-root" /usr/local/sbin/daydream-root'
    conf = 'install -o root -g root -m 0644 "$tmp" /etc/daydream/root.conf'
    sudoers = 'install -o root -g root -m 0440 "$tmp" /etc/sudoers.d/daydream'
    assert helper in script and conf in script and sudoers in script
    assert "install -d -o root -g root -m 0755 /etc/daydream" in script
    # The helper and its facts are in place before sudoers names the helper.
    assert script.index(helper) < script.index(sudoers) and script.index(conf) < script.index(sudoers)
    # What the installer writes is what the helper reads.
    fmt = re.search(r"printf '([^']*OPERATOR=%s[^']*)'", script).group(1)
    text = fmt.replace("\\n", "\n").replace("%s", "peter", 1).replace("%s", "/home/peter/src/daydream", 1)
    etc = tmp_path.resolve() / "daydream"
    etc.mkdir(mode=0o755)
    os.chmod(etc, 0o755)
    (etc / "root.conf").write_text(text)
    os.chmod(etc / "root.conf", 0o644)
    mod = _helper_module()
    monkeypatch.setattr(mod, "ROOT_CONF", str(etc / "root.conf"))
    got = mod.load_conf()
    assert (got.operator, got.repo) == ("peter", "/home/peter/src/daydream")


def test_the_installer_takes_its_operator_from_sudo_and_never_guesses():
    """Run as root without sudo, a guessed operator would get the sudoers
    rules, root.conf and the operator jobs on a fork (codereview WARN
    2026-09-28e). The guard runs here for real, minus the EUID check."""
    import subprocess

    script = (OPS / "install-prod.sh").read_text()
    start = script.index('OPERATOR="${SUDO_USER')
    guard = script[start:script.index("\nREPO=", start)]
    assert not re.search(r"SUDO_USER:-[^}]", script)  # no fallback name, anyone's
    for sudo_user, ok in ((None, False), ("", False), ("root", False), ("alice", True)):
        env = {"PATH": os.environ["PATH"]}
        if sudo_user is not None:
            env["SUDO_USER"] = sudo_user
        r = subprocess.run(["bash", "-c", guard + '\necho "operator=$OPERATOR"'], env=env,
                           capture_output=True, text=True)
        assert (r.returncode == 0) is ok, (sudo_user, r.stdout, r.stderr)
        assert ("operator=alice" in r.stdout) is ok
        assert ok or "run it with sudo as the operator" in r.stderr


def test_the_installer_installs_every_unit_and_enables_every_timer():
    script = (OPS / "install-prod.sh").read_text()
    for f in sorted(UNITS.iterdir()):
        assert f.name in script, f"ops/install-prod.sh does not install {f.name}"
        if f.suffix == ".timer":
            assert (UNITS / f.name.replace(".timer", ".service")).exists()
            assert re.search(rf"enable --now[^\n]*{re.escape(f.name)}", script)
    # Only timers are enabled at boot: the village stays down after a reboot.
    for line in re.findall(r"systemctl enable[^\n]*", script):
        units = [w for w in line.split() if w.endswith((".service", ".timer"))]
        assert units and all(u.endswith(".timer") for u in units), line


def test_prod_env_example_passes_the_boot_guard(monkeypatch):
    from daydream import config

    for k, v in _env_file(OPS / "prod.env.example").items():
        monkeypatch.setenv(k, v)
    assert config.boot_problems() == []


def test_the_worker_and_prod_env_describe_the_same_site():
    env, w = _env_file(OPS / "prod.env.example"), _wrangler_vars()
    host = env["DAYDREAM_PUBLIC_ORIGIN"].split("://", 1)[1].rstrip("/")
    assert w["PUBLIC_HOST"] == host
    assert w["BASE"] == env["DAYDREAM_PUBLIC_BASE"]
    assert w["COOKIE_NAME"] == f"dd_session_{env['DAYDREAM_ENV']}"
    assert w["OPERATOR"] == env["DAYDREAM_OPERATOR_NAME"]
    routes = (REPO / "edge" / "wrangler.toml").read_text()
    assert f'pattern = "{host}{w["BASE"].rstrip("/")}*"' in routes
    assert w["ORIGIN"].startswith("https://") and env["DAYDREAM_BIND_HOST"] in ("127.0.0.1", "::1")


def test_the_prod_service_keeps_its_sandbox():
    """The posture docs/GOING-LIVE.md section 7 promises, pinned."""
    unit = (UNITS / "daydream-prod.service").read_text()
    for line in ("User=daydream", "NoNewPrivileges=yes", "ProtectHome=yes", "ProtectSystem=strict",
                 "ReadWritePaths=/srv/daydream/data", "IPAddressDeny=any",
                 "IPAddressAllow=localhost", "EnvironmentFile=/srv/daydream/etc/prod.env"):
        assert line in unit, line
    assert "--host ${DAYDREAM_BIND_HOST} --port ${DAYDREAM_PORT}" in unit
    tunnel = (UNITS / "cloudflared-daydream.service").read_text()
    for line in ("DynamicUser=yes", "EnvironmentFile=/etc/cloudflared/daydream.env",
                 "ProtectHome=yes", "NoNewPrivileges=yes"):
        assert line in tunnel, line
    assert "[Install]" in unit and "WantedBy" in unit  # installable, but never enabled
