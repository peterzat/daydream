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
