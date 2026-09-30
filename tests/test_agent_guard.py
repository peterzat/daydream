"""The PreToolUse guard (tools/agent_guard.py; security review 2026-09-29):
gated prod verbs ask however they are spelled, credentials are never
opened, and ordinary work gets no opinion."""

import importlib.util
import json
import subprocess
import sys
import time
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


CONFIG = "~/." + "config"  # the folder that holds gh's and daydream's credentials
REPO = guard._HOME + "/src/daydream"


def _bash_in(cmd, cwd=REPO):
    return guard.decide({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd})


@pytest.mark.parametrize("cmd,want", [
    # Security WARN 2026-09-29, closed 2026-09-30: a search, archive or copy
    # rooted one folder below home, however the folder is spelled.
    ("grep -rn CLOUDFLARE_API_TOKEN " + CONFIG, "ask"),
    ("grep -rn TOKEN " + CONFIG + "/", "ask"),
    ("rg -n token $HOME/." + "config", "ask"),
    ("rg -n token ${HOME}/." + "config/", "ask"),
    ("find " + CONFIG + " -type f -exec cat {} +", "ask"),
    ("grep -r token ~/." + "claude", "ask"),
    ("cd ~ && grep -r token .", "ask"),
    ("cd " + CONFIG + " && rg token", "ask"),
    ("grep -rn token ../..", "ask"),  # from the repo: home
    ("tar czf /tmp/c.tgz " + CONFIG, "ask"),
    ("cp -r " + CONFIG + " /tmp/c", "ask"),
    ("rsync -a " + CONFIG + "/ /tmp/c/", "ask"),
    # ...and a credential folder spelled so no name matches: denied.
    ("cat " + CONFIG + "/./" + "gh/hosts.yml", "deny"),
    ("cd " + CONFIG + " && cat gh/hosts.yml", "deny"),
    ("cd " + CONFIG + "; cd gh; cat hosts.yml", "deny"),
    ("gh auth status -th github.com", "deny"),  # -t inside a short-flag bundle
    ("gh auth status -ht github.com", "deny"),
    ("grep " + TOKEN + " notes.txt", "deny"),  # the token's field name, anywhere
    # ordinary work stays quiet
    ("gh auth status", None),
    ("gh auth status -h github.com", None),
    ("grep -rn foo ~/data/daydream", None),
    ("rg -n foo ~/." + "claude/projects", None),
    ("cp -r worlds /tmp/w", None),
    ("tar czf /tmp/a.tgz ~/data/daydream/backups", None),
    ("grep -rn foo docs/ daydream/", None),
    ("cd /tmp && rg foo", None),
])
def test_folders_that_hold_credentials(cmd, want):
    got = _bash_in(cmd)
    assert (got[0] if got else None) == want, (cmd, got)


@pytest.mark.parametrize("cmd,want", [
    # Security NOTE 2026-09-29, closed 2026-09-30: the raw gated-verb pass.
    ("bin/game prod >/dev/null invite create --for M", "ask"),  # a redirection ends nothing
    ("bin/game prod > /tmp/x.log invite create --for M", "ask"),
    ('python3 -c \'import subprocess; subprocess.run(["bin/game", "prod", "invite", '
     '"create"])\'', "ask"),  # list form
    ("bin/game prod pull; cat " + CONFIG + "/./" + "gh/hosts.yml", "deny"),  # a deny wins
    ("bin/game prod deploy > /tmp/deploy.log", None),
])
def test_the_raw_pass_reads_past_redirections_and_lists(cmd, want):
    got = _bash_in(cmd)
    assert (got[0] if got else None) == want, (cmd, got)


GH_ALT = CONFIG + "/./" + "gh/hosts.yml"  # gh's credential, spelled so no name matches


@pytest.mark.parametrize("head,want", [
    ("cat " + GH_ALT, "deny"),
    ("bin/game prod invite create --for M", "ask"),
])
def test_a_long_adversarial_line_is_judged_quickly(head, want):
    """Codereview 2026-09-30b: `--git-dir=x` matched both alternatives of the
    git-credential pattern's repeated group; seventeen of them timed the real
    hook out, and a timeout lets the command run with no opinion."""
    cmd = head + "; git" + " --git-dir=x" * 40 + " y"
    assert len(cmd) >= 500
    r = subprocess.run([sys.executable, str(ROOT / "tools/agent_guard.py")],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                                         "cwd": REPO}),
                       capture_output=True, text=True, check=True, timeout=5)
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == want
    start = time.perf_counter()
    got = _bash_in(cmd)
    assert got[0] == want and time.perf_counter() - start < 0.05, (got, cmd)


@pytest.mark.parametrize("cmd,want", [
    # Codereview 2026-09-30b: the raw pass split `2>&1`, `>&f` and `&>f` on
    # their `&` before it read them, and a redirection target holding `=`,
    # `,` or a quoted space leaked a word into the verb.
    ('out="$(bin/game prod 2>&1 invite create --for M)"', "ask"),
    ('out="$(bin/game prod >&/tmp/x invite create --for M)"', "ask"),
    ('out="$(bin/game prod &>/dev/null invite create --for M)"', "ask"),
    ('out="$(bin/game prod > /tmp/a=b invite create --for M)"', "ask"),
    ('out="$(bin/game prod > /tmp/a,b invite create --for M)"', "ask"),
    ("out=\"$(bin/game prod > '/tmp/a b' invite create --for M)\"", "ask"),
    ('out="$(bin/game prod > /tmp/"a b"c invite create --for M)"', "ask"),
    ('out="$(bin/game prod > /tmp/a\\ b invite create --for M)"', "ask"),
    ('out="$(bin/game prod 2>&- invite create --for M)"', "ask"),  # a lone - takes no target
    ('out="$(bin/game prod >-x invite create --for M)"', "ask"),  # ...but -x is one
    # `>|` was a redirection in neither pass
    ("bin/game prod >| /tmp/x invite create --for M", "ask"),
    ("bin/game prod >| /tmp/x world reset --yes", "ask"),
    ('out="$(bin/game prod >| /tmp/x world reset --yes)"', "ask"),
    # ordinary redirections stay quiet
    ('out="$(bin/game prod deploy 2>&1)"; echo "$out" > /tmp/d.log', None),
    ("bin/game prod status >| /tmp/status.txt", None),
])
def test_a_redirection_and_its_target_are_read_whole(cmd, want):
    got = _bash_in(cmd)
    assert (got[0] if got else None) == want, (cmd, got)


def test_the_parser_reads_a_clobbering_redirection():
    """`>|` and its target are not the command's arguments; the target comes
    back as a path to judge."""
    assert guard._split_commands("bin/game prod >| /tmp/x world reset --yes") == [
        [">", "/tmp/x"], ["bin/game", "prod", "world", "reset", "--yes"]]


@pytest.mark.parametrize("cmd,want", [
    # Codereview 2026-09-30b: a cd that never takes effect (a subshell, a
    # failed cd before `;`) moved the guard but not the shell. Every
    # directory the line may be in is judged.
    ("(cd /tmp/a/b); cat ../../." + "config/./" + "gh/hosts.yml", "deny"),
    ("cd /no/such/dir/x; cat ../../." + "config/./" + "gh/hosts.yml", "deny"),
    ("(cd /tmp/a/b/c); grep -rn token ../..", "ask"),
    ("cd -P " + CONFIG + "; cat ./" + "gh/hosts.yml", "deny"),  # cd's option is not its target
    ("cd " + CONFIG + " && tar czf /tmp/c.tgz gh", "ask"),  # a bare root inside a credential
    ("".join(f"cd /d{i}; " for i in range(16)) + "cd " + CONFIG + "; cat ./" + "gh/hosts.yml",
     "ask"),  # more directories than the guard follows: the operator confirms
    ("cd /tmp && make && cd - && rg foo", None),  # cd - returns to a counted directory
    ("cd daydream && rg foo", None),
])
def test_a_cd_that_may_not_take_effect(cmd, want):
    got = _bash_in(cmd)
    assert (got[0] if got else None) == want, (cmd, got)


def test_a_long_line_of_cds_is_judged_within_the_hooks_timeout():
    """Codereview 2026-09-30b: the old tracking folded an ever longer path
    (`cd a; ` sixteen thousand times took 6.8 s, past the hook's 5 s), and
    a deny after the cap still wins over its ask."""
    cmd = "cd a; " * 16000 + "cat " + GH_ALT
    r = subprocess.run([sys.executable, str(ROOT / "tools/agent_guard.py")],
                       input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd},
                                         "cwd": REPO}),
                       capture_output=True, text=True, check=True, timeout=5)
    assert json.loads(r.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


@pytest.mark.parametrize("cmd,want", [
    # Codereview 2026-09-30b: a glob named a credential and no name matched.
    ("cat " + CONFIG + "/*/hosts.yml", "deny"),
    ("head ~/.con" + "*/gh/*", "deny"),
    ("cat ~/.s" + "?h/id_ed25519", "deny"),
    ("cat /etc/cloudflare" + "?/*", "deny"),
    ("cd " + CONFIG + " && cat g" + "*/hosts.yml", "deny"),
    ("cat ~/.[s]" + "sh/id_ed25519", "deny"),
    ("cat /srv/daydream/[e]" + "tc/prod.env", "deny"),
    ("cat ~/.s{s,x}" + "h/id_ed25519", "deny"),  # a brace group is a spelling too
    ("cat < " + GH_ALT, "deny"),  # ...and so is a redirection target
    ("cat < ~/.s" + "?h/id_ed25519", "deny"),
    ("cd " + CONFIG + "; cat < g" + "?/hosts.yml", "deny"),
    ("cp -r ~/.con" + "* /tmp/c", "ask"),  # a folder that holds one
    ("cd " + CONFIG + " && tar czf /tmp/c.tgz g" + "*", "ask"),
    # ordinary globs and braces stay quiet
    ("ls ~/.claude/projects/*/memory", None),
    ("grep -rn foo ~/data/daydream/*.log", None),
    ("ls /srv/daydream/releases/*", None),
    ("rg -n foo daydream/{api,llm}/", None),
    ("cat docs/*.md > /tmp/all.md", None),
    ("sort < data.txt > out.txt", None),
])
def test_globs_braces_and_redirection_targets(cmd, want):
    got = _bash_in(cmd)
    assert (got[0] if got else None) == want, (cmd, got)


def test_a_credential_path_spelled_another_way_is_not_read():
    path = guard._HOME + "/." + "config/./" + "gh/hosts.yml"
    got = guard.decide({"tool_name": "Read", "tool_input": {"file_path": path}})
    assert got and got[0] == "deny"


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
