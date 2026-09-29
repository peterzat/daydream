"""The PreToolUse guard (tools/agent_guard.py; security review 2026-09-29):
gated prod verbs ask however they are spelled, credentials are never
opened, and ordinary work gets no opinion."""

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location("agent_guard", ROOT / "tools/agent_guard.py")
guard = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(guard)


def _bash(cmd):
    return guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}})


@pytest.mark.parametrize("cmd", [
    "bin/game prod invite create --for Robin --json",
    "/home/me/src/daydream/bin/game prod account delete robin --yes",
    "./bin/game prod world reset --yes",
    "FOO=1 bin/game prod world patch worlds/x.json",
    "bash -c 'bin/game prod play send hi'",
    "cd /tmp && timeout 30 bin/game prod offsite-restore x /tmp/y",
    "echo ok; bin/game prod account disable robin",
    "bin/game prod deploy abc123 --skip-tests",
    "bin/game prod world delete-toon Wren --instance village",
    "bin/game edge secrets",
    "gh gist create notes.txt",
])
def test_gated_verbs_ask_however_spelled(cmd):
    assert _bash(cmd)[0] == "ask", cmd


@pytest.mark.parametrize("cmd", [
    "cat ~/.config/daydream/cloudflare.env",
    "head -c 100 $HOME/.ssh/id_ed25519",
    "python3 -c 'print(open(\"/etc/cloudflared/daydream.env\").read())'",
    "gh auth token",
    "gh auth status --show-token",
    "sudo cat /srv/daydream/etc/prod.env",
])
def test_credentials_are_never_opened(cmd):
    assert _bash(cmd)[0] == "deny", cmd


def test_reading_a_credential_file_is_denied():
    got = guard.decide({"tool_name": "Read",
                        "tool_input": {"file_path": "/home/me/.config/gh/hosts.yml"}})
    assert got[0] == "deny"


@pytest.mark.parametrize("cmd", [
    "bin/game prod status", "bin/game prod check", "bin/game prod deploy",
    "bin/game prod deploy HEAD", "bin/game prod world refresh --check",
    "bin/game prod world patch p.json --check", "bin/game prod text-scan --since 40",
    "bin/game prod invite list", "bin/game edge deploy", "bin/game test short",
    "git status && git log --oneline -3", "ls worlds/", "gh api repos/x/y",
])
def test_ordinary_work_gets_no_opinion(cmd):
    assert _bash(cmd) is None, cmd


def test_it_speaks_claude_codes_hook_protocol():
    r = subprocess.run([sys.executable, str(ROOT / "tools/agent_guard.py")],
                       input=json.dumps({"tool_name": "Bash",
                                         "tool_input": {"command": "bin/game prod pull"}}),
                       capture_output=True, text=True, check=True)
    out = json.loads(r.stdout)["hookSpecificOutput"]
    assert out["hookEventName"] == "PreToolUse" and out["permissionDecision"] == "ask"
    r = subprocess.run([sys.executable, str(ROOT / "tools/agent_guard.py")],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}}),
                       capture_output=True, text=True, check=True)
    assert r.stdout == ""


@pytest.mark.parametrize("cmd,want", [
    ("bin/game prod account list", None),
    ("bin/game prod account sessions robin", None),
    ("bin/game prod account sessions robin --revoke", "ask"),
])
def test_reading_accounts_is_quiet_changing_them_asks(cmd, want):
    got = _bash(cmd)
    assert (got[0] if got else None) == want, cmd


# Codereview 2026-09-29c: shapes that hid a command from the first guard.
HOME_SSH = "~/." + "ssh/id_ed25519"  # built from parts: the guard reads this file's writes


@pytest.mark.parametrize("cmd,want", [
    ("echo ok\nbin/game prod invite create --for M", "ask"),  # a newline separates
    ("true\ngh auth token", "deny"),
    ("echo a#; bin/game prod invite create --for M", "ask"),  # '#' mid-word is a word char
    ("bash -lc 'bin/game prod world reset --yes'", "ask"),
    ("sh -ec 'cd /tmp; bin/game prod play say hi'", "ask"),
    ("bash bin/game prod world reset --yes", "ask"),
    ("eval 'bin/game prod account delete robin --yes'", "ask"),
    ("sudo -u daydream /srv/daydream/current/bin/game world reset --yes", "ask"),
    ("nice -n 5 bin/game prod pull", "ask"),
    ("flock /tmp/l bin/game prod rollback", "ask"),
    ("timeout 30 bin/game prod sleep", "ask"),
    ("bin//game prod invite create --for M", "ask"),
    ("cat <<'EOF' | bash\nbin/game prod world reset --yes\nEOF", "ask"),
    ("echo it's\nbin/game prod invite create --for M", "ask"),  # unbalanced quote: fallback
    (f"cat {HOME_SSH} 2>/dev/null", "deny"),
    ("bin/game prod deploy 2>&1 | tail -40", None),  # redirections are not arguments
    ("bin/game prod deploy > /tmp/deploy.log", None),
    ("bin/game prod deploy HEAD 2>/dev/null", None),
    ("echo 'a > b' && ls", None),
])
def test_the_shapes_a_command_hides_in(cmd, want):
    got = _bash(cmd)
    assert (got[0] if got else None) == want, (cmd, got)


@pytest.mark.parametrize("cmd,want", [
    # Security WARN 2026-09-29: the parser had dropped these.
    ("cat < " + HOME_SSH, "deny"),  # a credential as a redirection target
    ("echo key >> ~/." + "ssh/authorized_keys", "deny"),
    ("# it's up\ngh auth token", "deny"),  # a comment with an apostrophe
    ("git credential fill", "deny"),
    ("printf 'host=github.com\\n' | gh auth git-credential get", "deny"),
    ("/srv/daydream/current/bin/game edge secrets", "ask"),  # edge verbs from a release
    ("for x in 1; do bin/game prod account role m admin; done", "ask"),  # after keywords
    ("if true; then bin/game prod pull; fi", "ask"),
    ("f() { bin/game prod sleep; }; f", "ask"),
    ("while true; do gh auth token; done", "deny"),
])
def test_the_shapes_the_rewrite_had_let_through(cmd, want):
    got = _bash(cmd)
    assert (got[0] if got else None) == want, (cmd, got)


TOKEN = "oauth" + "_token"  # built from parts, like HOME_SSH


@pytest.mark.parametrize("cmd,want", [
    # Security WARNs 2026-09-29 (second scan).
    ('out="$(bin/game prod invite create --for "Robin" --json)"', "ask"),
    ("gh config get -h github.com " + TOKEN, "deny"),
    ("git -C /tmp credential fill", "deny"),
    ("git -c credential.helper= credential fill", "deny"),
    ("gh auth 'git-credential' get", "deny"),
    ("cat ~/.claude/." + "credentials.json", "deny"),
    ("grep -rn CLOUDFLARE_API_TOKEN ~", "ask"),
    ("rg -n token $HOME", "ask"),
    ("find / -name '*.env'", "ask"),
    ("grep -rn foo docs/", None),
    ("grep -n 'def main' daydream/ci.py", None),
])
def test_the_second_scans_shapes(cmd, want):
    got = _bash(cmd)
    assert (got[0] if got else None) == want, (cmd, got)


@pytest.mark.parametrize("tool,inp,want", [
    ("Edit", {"file_path": "/repo/tools/agent_guard.py"}, "ask"),
    ("Write", {"file_path": "/repo/.claude/settings.local.json"}, "ask"),
    ("Edit", {"file_path": "/repo/.claude/settings.json"}, "ask"),
    ("Read", {"file_path": "/repo/tools/agent_guard.py"}, None),
    ("Edit", {"file_path": "/repo/tests/test_agent_guard.py"}, None),
    ("Bash", {"command": "sed -i s/ask/allow/ .claude/settings.local.json"}, "ask"),
    ("Bash", {"command": "echo '{}' > .claude/settings.local.json"}, "ask"),
    ("Bash", {"command": "cp /tmp/x tools/agent_guard.py"}, "ask"),
    ("Bash", {"command": "git checkout -- tools/agent_guard.py"}, "ask"),
    ("Bash", {"command": "cat .claude/settings.json"}, None),
    ("Bash", {"command": "git diff tools/agent_guard.py"}, None),
    ("Bash", {"command": "git add tools/agent_guard.py tests/test_agent_guard.py"}, None),
])
def test_the_guard_and_the_settings_ask_before_they_change(tool, inp, want):
    """Codereview 2026-09-29c: loosening the guard or the permission settings
    would be an injected instruction's first move."""
    got = guard.decide({"tool_name": tool, "tool_input": inp})
    assert (got[0] if got else None) == want, (tool, inp, got)
