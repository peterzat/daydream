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
SHELL_KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "{", "}", "!",
                  "function"}
# Commands that print a credential without naming its file (this box's git
# credential helper for github.com is gh).
TOKEN_PRINTERS = re.compile(
    r"\bgh\s+auth\s+token\b|\bgh\s+auth\s+status\b[^\n;|&]*(-t\b|--show-token)"
    r"|\bgh\s+auth\s+git-credential\b|\bgit\s+credential\s+(fill|get)\b"
    r"|\bgit\s+credential-\w+\s+get\b")

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


# Wrapper options that take a value, so the value is not taken for the
# program (`sudo -u daydream prog`, `nice -n 5 prog`).
WRAPPER_VALUE_OPTS = {
    "sudo": {"-u", "-g", "-C", "-h", "-p", "-U", "-r", "-t", "-D"},
    "nice": {"-n"}, "ionice": {"-c", "-n", "-t"}, "env": {"-u", "-C", "-S"},
    "timeout": {"-s", "-k"}, "flock": {"-w", "-E"}, "watch": {"-n", "-d"},
    "xargs": {"-I", "-n", "-P", "-d", "-a", "-L", "-s", "-E"}, "stdbuf": {"-i", "-o", "-e"},
}
# ...and wrappers whose first plain word is theirs, not the program's.
WRAPPER_FIRST_WORD = {"timeout", "flock"}
REDIRECT = re.compile(r"^\d*(>>?|<<?<?|&>>?|>&|<&)-?$")


def _split_commands(command: str) -> list[list[str]]:
    """The simple commands in a line, each as argv, across ; && || | & and
    newlines, subshell parentheses, and $( ) / backticks, with redirections
    and their targets left out. A `#` inside a word is a word character, as
    in bash."""
    text = re.sub(r"\$\(|`|\(|\)", " ; ", command)
    lex = shlex.shlex(text, posix=True, punctuation_chars=";&|\n<>")
    lex.whitespace = " \t\r"
    lex.whitespace_split = True
    lex.commenters = ""
    out, cur = [], []
    skip_next = False
    try:
        for tok in lex:
            if skip_next:
                skip_next = False
                continue
            if tok and set(tok) <= set(";&|\n"):
                if cur:
                    out.append(cur)
                cur = []
            elif tok and (REDIRECT.match(tok) or set(tok) <= set("<>&")):
                if cur and cur[-1].isdigit():
                    cur.pop()  # the fd of "2>": part of the redirection
                skip_next = not tok.endswith("-")  # its target
            else:
                cur.append(tok)
    except ValueError:  # unbalanced quotes (a heredoc body): judge every word
        return _fallback(command)
    if cur:
        out.append(cur)
    return out


def _fallback(command: str) -> list[list[str]]:
    """Unparseable: every word, and each run that starts at a bin/game."""
    words = command.split()
    runs = [words]
    for i, w in enumerate(words):
        if os.path.normpath(w.strip("'\"")).endswith("bin/game"):
            runs.append([x.strip("'\"") for x in words[i:]])
    return runs


def _unwrap(argv: list[str]) -> list[list[str]]:
    """Strip env assignments and process wrappers; a shell given a script
    (`bash -lc '...'`, `sh -ec '...'`), a shell running a file, and `eval`
    are read as the commands they run."""
    i = 0
    while i < len(argv):
        w = argv[i]
        if re.match(r"^[A-Za-z_][A-Za-z0-9_]*=", w) or w in SHELL_KEYWORDS:
            # `do bin/game ...`, `then gh ...`, `{ cmd; }`: the command follows
            # (security WARN 2026-09-29).
            i += 1
            continue
        base = os.path.basename(w)
        if base in WRAPPERS:
            value_opts = WRAPPER_VALUE_OPTS.get(base, set())
            i += 1
            while i < len(argv) and argv[i].startswith("-"):
                i += 2 if argv[i] in value_opts else 1
            if base in WRAPPER_FIRST_WORD and i < len(argv):
                i += 1  # timeout's duration, flock's lock file
            continue
        if base == "eval":
            return [c for part in _split_commands(" ".join(argv[i + 1:])) for c in _unwrap(part)]
        if base in SHELLS:
            j = i + 1
            while j < len(argv) and argv[j].startswith("-"):
                if not argv[j].startswith("--") and "c" in argv[j][1:]:
                    if j + 1 < len(argv):
                        return [c for part in _split_commands(argv[j + 1])
                                for c in _unwrap(part)]
                    return []
                j += 1
            if j < len(argv):
                return _unwrap(argv[j:])  # `bash some/script args`: the script runs
            return [argv[i:]]
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
    exe = os.path.normpath(argv[0])
    if exe.endswith("bin/game") or exe == "game":
        args = argv[1:]
        if exe.startswith("/srv/daydream/") and args[:1] not in (["prod"], ["edge"]):
            # A release's own bin/game run directly: its verbs are prod's.
            args = ["prod", *args]
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


# The guard and the permission settings: changing them asks the operator
# (codereview 2026-09-29c: an injected instruction's first move would be to
# loosen them).
PROTECTED = re.compile(r"(^|/)tools/agent_guard\.py$|(^|/)\.claude/settings[^/]*\.json$")
WRITERS = {"sed", "tee", "cp", "mv", "rm", "truncate", "python", "python3", "perl", "dd",
           "install", "ln", "chmod", "git"}


def _protected_write(command: str) -> str | None:
    words = re.findall(r"[^\s'\";|&<>()]+", command)
    hits = [w for w in words if PROTECTED.search(w)]
    if not hits:
        return None
    writes = bool(re.search(r"(^|[^<])>|\btee\b|\bsed\b[^|;&]*-i", command)) or any(
        os.path.basename(argv[0]) in WRITERS
        for part in _split_commands(command) for argv in _unwrap(part) if argv
        and any(PROTECTED.search(a) for a in argv) and os.path.basename(argv[0]) != "git"
    ) or bool(re.search(r"\bgit\s+(checkout|restore|rm|mv|apply)\b", command))
    return hits[0] if writes else None


def decide(payload: dict) -> tuple[str, str] | None:
    tool = payload.get("tool_name")
    inp = payload.get("tool_input") or {}
    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        p = _names_credentials([path])
        if p:
            return "deny", f"{p} holds this box's credentials; the agent does not open it"
        if tool != "Read" and PROTECTED.search(path):
            return "ask", f"{path} guards this session's permissions; the operator confirms a change"
        return None
    if tool != "Bash":
        return None
    command = str(inp.get("command") or "")
    # Over the raw line, before any parsing: a credential path anywhere,
    # redirection targets included (`cat < file`), and the commands that
    # print a token without naming a file (security WARN 2026-09-29: the
    # parsed argv left redirection targets and comment-broken lines out).
    p = _names_credentials(re.findall(r"\S+", command))
    if p:
        return "deny", f"{p} holds this box's credentials; the agent does not open it"
    if TOKEN_PRINTERS.search(command):
        return "deny", "the GitHub token stays where it is"
    hit = _protected_write(command)
    if hit:
        return "ask", f"{hit} guards this session's permissions; the operator confirms a change"
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
