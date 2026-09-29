#!/usr/bin/env python3
"""A PreToolUse guard for Claude Code sessions in this repo (security review
2026-09-29).

Player text reaches the agent (the dream digest, `bin/game play`, letters,
dreamer names), and the session holds the prod grant. Permission rules match
a command's text by prefix, so a different spelling of a gated verb (an
absolute path, `bash -c`, an alias verb) slips past them. This hook reads the
command the way the shell will, and:

- DENIES any command or file read that names the credentials on this box
  (~/.ssh, ~/.config/gh, ~/.config/daydream, /srv/daydream/etc,
  /etc/cloudflared) or prints the GitHub token;
- ASKS before the `bin/game prod` / `bin/game edge` verbs that mint access,
  remove a person, replace the world, reach players, or change root or the
  edge's secrets, however the command is spelled.

Everything else gets no opinion (the normal rules apply). It reads the hook
payload on stdin and prints Claude Code's hookSpecificOutput JSON. Wired in
`.claude/settings.local.json` (template: docs/claude-settings.local.example.json);
tests: tests/test_agent_guard.py. Standard library only.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

CREDENTIAL_PATHS = (".ssh/", ".ssh", ".config/gh", ".config/daydream", "/srv/daydream/etc",
                    "/etc/cloudflared")
WRAPPERS = {"timeout", "time", "nice", "nohup", "stdbuf", "command", "builtin", "env",
            "exec", "xargs", "sudo", "setsid", "ionice", "flock", "watch"}
SHELLS = {"bash", "sh", "zsh", "dash"}

# (subcommand, verb[, ...]) prefixes of `bin/game prod|edge` that always ask.
ASK_PROD = [
    ("invite", "create"), ("invite", "reset"), ("invite", "revoke"), ("invite", "unblock"),
    ("account", "create"), ("account", "role"), ("account", "cli-cookie"), ("account", "delete"),
    ("account", "disable"), ("account", "enable"), ("account", "rename"),
    ("world", "reset"), ("world", "delete"), ("world", "restore"), ("world", "snapshot-restore"),
    ("world", "restore-backup"), ("world", "load"), ("world", "delete-toon"),
    ("world", "rest-toon"), ("world", "skill"), ("world", "patch"), ("world", "swap"),
    ("dream", "apply"),
    ("play",), ("offsite-restore",), ("pull",), ("instance",), ("rollback",), ("sleep",),
    ("root", "units"), ("root", "env"),
]
ASK_EDGE = [("secrets",), ("kv-create",), ("sleep",)]


def _split_commands(command: str) -> list[list[str]]:
    """The simple commands in a line, each as argv, across ; && || | & and
    newlines, subshell parentheses, and $( ) / backticks."""
    text = re.sub(r"\$\(|`|\(|\)", " ; ", command)
    lex = shlex.shlex(text, posix=True, punctuation_chars=";&|\n")
    lex.whitespace_split = True
    out, cur = [], []
    try:
        for tok in lex:
            if tok and set(tok) <= set(";&|\n"):
                if cur:
                    out.append(cur)
                cur = []
            else:
                cur.append(tok)
    except ValueError:  # unbalanced quotes: judge the raw words
        return [command.split()]
    if cur:
        out.append(cur)
    return out


def _unwrap(argv: list[str]) -> list[list[str]]:
    """Strip env assignments and process wrappers; a `bash -c '...'` is read
    as the commands inside it."""
    i = 0
    while i < len(argv):
        w = argv[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w):
            i += 1
            continue
        base = os.path.basename(w)
        if base in WRAPPERS:
            i += 1
            while i < len(argv) and (argv[i].startswith("-") or re.fullmatch(r"[\d.]+[smhd]?", argv[i])):
                i += 1
            continue
        if base in SHELLS and "-c" in argv[i + 1:]:
            j = argv.index("-c", i + 1)
            if j + 1 < len(argv):
                return [cmd for part in _split_commands(argv[j + 1]) for cmd in _unwrap(part)]
        return [argv[i:]]
    return []


def _names_credentials(words: list[str]) -> str | None:
    for w in words:
        w2 = w.replace("$HOME", "~")
        for p in CREDENTIAL_PATHS:
            if p in w2:
                return p
    return None


def _gated(argv: list[str]) -> str | None:
    if not argv:
        return None
    exe = argv[0]
    if exe.endswith("bin/game") or exe == "game":
        args = argv[1:]
        if not args or args[0] not in ("prod", "edge"):
            return None
        rules = ASK_PROD if args[0] == "prod" else ASK_EDGE
        rest = [a for a in args[1:] if a != "--instance"]
        for rule in rules:
            if tuple(rest[:len(rule)]) == rule:
                if rule == ("world", "patch") and "--check" in rest:
                    return None
                return f"bin/game {args[0]} {' '.join(rule)}"
        if rest[:2] == ["account", "sessions"] and "--revoke" in rest:
            return "bin/game prod account sessions --revoke"
        if args[0] == "prod" and rest[:1] == ["deploy"]:
            extra = [a for a in rest[1:] if a not in ("HEAD",)]
            if extra:
                return "bin/game prod deploy of another ref, or without its tests"
    return None


def decide(payload: dict) -> tuple[str, str] | None:
    tool = payload.get("tool_name")
    inp = payload.get("tool_input") or {}
    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        p = _names_credentials([str(inp.get("file_path") or inp.get("notebook_path") or "")])
        if p:
            return "deny", f"{p} holds this box's credentials; the agent does not open it"
        return None
    if tool != "Bash":
        return None
    command = str(inp.get("command") or "")
    for argv in (c for part in _split_commands(command) for c in _unwrap(part)):
        p = _names_credentials(argv)
        if p:
            return "deny", f"{p} holds this box's credentials; the agent does not open it"
        base = os.path.basename(argv[0]) if argv else ""
        if base == "gh" and (argv[1:3] == ["auth", "token"] or
                             ("auth" in argv[1:2] and ("-t" in argv or "--show-token" in argv))):
            return "deny", "the GitHub token stays where it is"
        if base == "gh" and argv[1:2] in (["gist"], ["ssh-key"], ["secret"]):
            return "ask", f"gh {argv[1]} can publish or grant access; the operator decides"
        why = _gated(argv)
        if why:
            return "ask", f"{why}: this mints access, reaches players, removes something or " \
                          "changes the edge or root; the operator confirms it"
    return None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    got = decide(payload)
    if got:
        decision, reason = got
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": decision,
            "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
