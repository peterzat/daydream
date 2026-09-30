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
  /etc/cloudflared), plainly or with `..`, `./`, a glob (`*`, `?`, `[...]`)
  or a brace group, as an argument or a redirection target, and any command
  that prints the GitHub token. What the shell computes at run time is not
  modeled: variables and command substitution (`D=~/.config; cat $D/gh/...`,
  `$(echo ~)`);
- ASKS before a search, archive or copy rooted at a folder that holds one of
  them (`grep -rn ... ~/.config`);
- ASKS before the `bin/game prod` / `bin/game edge` verbs that mint access,
  remove a person, replace the world, reach players, or change root or the
  edge's secrets, however the command is spelled;
- ASKS when it cannot read a command whole: one over 16 KB, one nested
  past sixteen levels of `eval` or a shell, or one it fails on;
- ASKS before a change to the live guard (the installed copy) or to the
  permission settings, and before `bin/game guard install`.

A deny anywhere in a command wins over an ask. A subagent is never asked:
what would ask the operator is denied to a subagent, which reports it and
lets the main session decide. Everything else gets no opinion (the normal
rules apply).

It reads a command as the shell will, and no further (playtest of the
guard, 2026-09-30: 176 prompts over 152 sessions, two thirds of them
false): a heredoc, found as the shell finds it, fed only to programs that
read text (`cat > file`, `git commit -F -`) is text; one fed to an
interpreter (python, perl, node) is code, read for credential paths and
for lines that run a program; any other is commands, and so is every
heredoc of a line that also runs a script file, a body never closed, and
every body of a command the heredoc reader does not follow (arithmetic, a
stray parenthesis). A file written with the Write tool is not read
either: the guard judges what runs, not what is written.

The hook runs the INSTALLED copy (~/.local/share/daydream/guard/), so this
file is ordinary code: edited and tested freely, live only once the
operator runs `! bin/game guard install` (a `!` command runs outside the
hook). It reads the hook payload on stdin and prints Claude Code's
hookSpecificOutput JSON. Wired in `.claude/settings.local.json`
(template: docs/claude-settings.local.example.json); tests:
tests/test_agent_guard.py. Standard library only.
"""
from __future__ import annotations

import fnmatch
import json
import os
import re
import shlex
import sys

CREDENTIAL_PATHS = (".ssh/", ".ssh", ".config/gh", ".config/daydream", "/srv/daydream/etc",
                    "/etc/cloudflared", ".claude/.credentials", ".config/rclone")
# The same places as absolute paths, for arguments that spell them another
# way (`~/.config/./gh`, `../../.config`) and for the folders that hold them.
_HOME = os.path.expanduser("~")
CREDENTIAL_LOCATIONS = tuple(os.path.normpath(p) for p in (
    f"{_HOME}/.ssh", f"{_HOME}/.config/gh", f"{_HOME}/.config/daydream",
    f"{_HOME}/.config/rclone", f"{_HOME}/.claude/.credentials.json", "/srv/daydream/etc",
    "/etc/cloudflared"))
# A search rooted here reads every credential file beneath it (security WARN
# 2026-09-29: `grep -rn <token name> ~` printed the Cloudflare token's line).
SEARCHERS = {"grep", "egrep", "fgrep", "rg", "ag", "ack", "find"}
# Searchers that read the working directory when given no path.
TREE_BY_DEFAULT = {"rg", "ag", "ack", "find"}
# Commands that read or carry a whole tree: rooted at a folder that holds a
# credential, they print it or copy it somewhere the path checks can't see
# (security WARN 2026-09-29, second scan).
TREE_READERS = SEARCHERS | {"tar", "zip", "cp", "rsync", "scp", "7z"}
BROAD_ROOTS = {"~", "~/", "$HOME", "$HOME/", "${HOME}", "${HOME}/", "/", "/root", "/home",
               "/etc", "/srv", "/srv/daydream", _HOME, _HOME + "/"}
# The most working directories a line is followed into; one more asks.
MAX_CWDS = 16
# The most levels of `eval` and shell scripts a command is read through, and
# the longest command the raw patterns read; past either, the operator
# confirms it (security WARN 2026-09-30: about 500 `eval`s passed Python's
# recursion limit, an 81 KB line took 4.7 s of the hook's 5 s, and a crash
# or a timeout lets the command run with no decision).
MAX_NESTING = 16
MAX_COMMAND_CHARS = 16 * 1024
WRAPPERS = {"timeout", "time", "nice", "nohup", "stdbuf", "command", "builtin", "env",
            "exec", "xargs", "sudo", "setsid", "ionice", "flock", "watch"}
SHELLS = {"bash", "sh", "zsh", "dash"}
SHELL_KEYWORDS = {"if", "then", "else", "elif", "do", "while", "until", "{", "}", "!",
                  "function"}
# Commands that print a credential without naming its file (this box's git
# credential helper for github.com is gh). `gh auth status` shows the token
# with -t in any short-flag bundle (`-th github.com`), and the token's field
# name in any command is a request to read it (security WARN 2026-09-29).
TOKEN_PRINTERS = re.compile(
    r"\bgh\s+auth\s+token\b"
    r"|\bgh\s+auth\s+status\b[^\n;|&]*(?:\s-[A-Za-z]*t[A-Za-z]*\b|--show-token)"
    r"|\bgh\s+auth\s+git-credential\b|oauth_token"
    # One lazy run, not a repeated option group: `--git-dir=x` matched both of
    # the old group's alternatives and backtracked past the hook's timeout
    # (codereview 2026-09-30b).
    r"|\bgit\b[^\n;|&]*?\bcredential(?:-\w+)?\s+(?:fill|get)\b")

# (subcommand, verb[, ...]) prefixes of `bin/game prod|edge` that always ask.
ASK_PROD = [
    ("invite", "create"), ("invite", "reset"), ("invite", "revoke"), ("invite", "unblock"),
    ("account", "create"), ("account", "role"), ("account", "cli-cookie"), ("account", "delete"),
    ("account", "disable"), ("account", "enable"), ("account", "rename"),
    ("world", "reset"), ("world", "delete"), ("world", "restore"), ("world", "snapshot-restore"),
    ("world", "restore-backup"), ("world", "load"), ("world", "delete-toon"),
    ("world", "rest-toon"), ("world", "skill"), ("world", "patch"), ("world", "swap"),
    ("dream", "apply"),
    # `pull` copies prod into dev on this box and changes nothing in prod:
    # part of the preview loop, it does not ask (2026-09-30).
    ("play",), ("offsite-restore",), ("instance",), ("rollback",), ("sleep",),
    ("root", "units"), ("root", "env"),
    # The egress gateway's keys (docs/EXTERNAL.md); `egress show` says only
    # which are set.
    ("root", "egress", "set"), ("root", "egress", "unset"),
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
REDIRECT = re.compile(r"^\d*(>\||>>?|<<?<?|&>>?|>&|<&)-?$")  # shlex keeps `>|` whole
# A redirection and its target (one shell word: quoted parts and `\ ` escapes
# included), stripped from the raw text before the raw pass splits it on
# ; & | (codereview 2026-09-30b: `2>&1`, `>&f` and `&>f` were cut apart, and a
# target holding `=`, `,` or a quoted space leaked a word). Longer operators
# come first; a lone `-` takes no target (`2>&- invite` keeps `invite`). A target
# ends at a command substitution, which bash runs (`> "$(bin/game ...)"`, a
# backtick), and keeps a plain variable (`> "/tmp/$x"`; security WARN 2026-09-30).
_RAW_REDIRECTION = re.compile(
    r"\d*(?:>\||>&|&>>?|>>?|<&|<<?<?)"
    r"(?:-(?=[\s;&|()<>]|$)|\s*(?:\\.|\"(?:[^\"\\$`]|\\.|\$(?!\())*\"|'[^']*'|[^\s;&|()<>'\"\\`])+)?")


# A heredoc's operator and its delimiter, the whole shell word after it
# (`<<'X-Y'`, `<<-END.1`, `<< "E O F"`), never a here-string's `<<<`
# (codereview 2026-09-30d: an identifier prefix of the word was taken).
_HEREDOC = re.compile(r"(?<!<)<<(?!<)(-?)[ \t]*((?:'[^'\n]*'|\"(?:[^\"\\\n]|\\.)*\"|\\.|"
                      r"[^\s;&|()<>'\"\\])+)")
# What the heredoc reader follows (quotes, escapes, `$( )`, `( )`,
# backticks, `${ }`, heredocs, comments) and what stops it (arithmetic,
# ANSI-C quoting): a command it stops on has every body read as commands.
_SCAN = re.compile(r"\$\(\(|\(\(|\$\[|\$'|\$\{|\$\(|(?<!<)<<(?!<)|[\\'\"`()}#]")
MAX_HEREDOCS = 32
# A heredoc is text only when every program it feeds reads text, and code
# when the rest are interpreters; anything else runs it as commands.
TEXT_READERS = {"cat", "tee", "git", "gh", "head", "tail", "wc", "grep", "sort", "diff", "jq"}
INTERPRETERS = re.compile(r"^(python[0-9.]*|perl|node|ruby|php|lua|Rscript|deno|bun)$")
# A line of interpreter code that runs a program: the only lines of a code
# heredoc the gated-verb passes read (`subprocess.run(["bin/game", ...])`).
_RUNS = re.compile(
    r"\bsubprocess\.\w+\s*\(|\bos\.(?:system|popen|exec\w*|spawn\w*|posix_spawn\w*)\s*\(|"
    r"\bPopen\s*\(|\bpty\.spawn\s*\(|\bsystem\s*\(|\bqx\s*[({/]|"
    r"\bexec(?:Sync|File\w*)?\s*\(|\bspawn(?:Sync)?\s*\(|[\"']bin/game[\"']\s*,")
# A line that runs a script file somewhere: every heredoc on it is commands
# (`cat > x.sh <<EOF ... EOF; bash x.sh`).
_RUNS_SCRIPT = re.compile(r"(^|[;&|(\s])(bash|sh|zsh|dash|source|\.)\s+[^-\s;&|<>]|"
                          r"(^|[;&|(\s])\./[^\s;&|]")


def _delimiter(word: str) -> str:
    """A heredoc's delimiter: its word with the quotes removed."""
    try:
        return "".join(shlex.split(word))
    except ValueError:
        return re.sub(r"['\"\\]", "", word)


def _heredoc_spans(lines: list[str]) -> list[tuple] | None:
    """The heredocs the shell reads in a command's lines, found as the shell
    finds them: an operator outside quotes, `${ }` and comments, a body from
    the first newline outside quotes to the first line that is exactly its
    delimiter (leading tabs dropped for `<<-`). Each is (its line, the
    operator's match, whether that line begins a command afresh, whether it
    is inside `$( )` or `( )`, its first body line, its closing line or None
    when none closes it). None for a command this reader does not follow."""
    spans: list[tuple] = []
    pending: list[tuple] = []
    stack: list[str] = []  # the open quotes, substitutions and `${`
    n, cont = 0, False
    while n < len(lines):
        line, k = lines[n], 0
        fresh, joined, cont = not stack and not cont, cont, False
        while k < len(line):
            top = stack[-1] if stack else ""
            if top == "'":  # only a quote ends a single-quoted string
                j = line.find("'", k)
                if j < 0:
                    break
                stack.pop()
                k = j + 1
                continue
            t = _SCAN.search(line, k)
            if t is None:
                break
            tok, k = t.group(), t.end()
            if tok == "\\":
                cont, k = k >= len(line), k + 1  # an escaped newline goes on
            elif tok in ("$((", "$[", "$'") or tok == "((" and top not in ('"', "{"):
                return None  # arithmetic or ANSI-C quoting: not followed
            elif top in ('"', "{"):
                if tok == ('"' if top == '"' else "}"):
                    stack.pop()
                elif tok in ("$(", "`", "${") or top == "{" and tok in ("'", '"'):
                    stack.append(tok[-1])
            elif tok == "#":
                s = t.start()
                if s == 0 and joined or s and line[s - 1] in ";&|()<>`{}":
                    return None  # a comment this reader might misplace
                if s == 0 or line[s - 1] in " \t":
                    break  # a comment, to the end of the line
            elif tok == "<<":
                m = _HEREDOC.match(line, t.start())
                if m is None or top == "`" or line[m.end():m.end() + 1] == "(" \
                        or len(spans) + len(pending) >= MAX_HEREDOCS:
                    return None
                pending.append((n, m, fresh, bool(stack)))
                k = m.end()
            elif tok == ")":
                if top != "(":
                    return None
                stack.pop()
            elif tok == "`" and top == "`":
                stack.pop()
            elif tok != "}":
                stack.append(tok[-1])  # ' " ` ( $( ${
        n += 1
        if cont or stack and stack[-1] in ("'", '"', "{"):
            continue  # an escaped or quoted newline: the command goes on
        for p in pending:  # the bodies, one after another, from the next line
            strip, delim = p[1].group(1) == "-", _delimiter(p[1].group(2))
            closing = next((j for j in range(n, len(lines))
                            if (lines[j].lstrip("\t") if strip else lines[j]) == delim), None)
            spans.append((*p, n, closing))
            n = len(lines) if closing is None else closing + 1
        pending = []
    return None if stack or cont else spans


def _heredoc_kind(lines: list[str], span: tuple, runs_script: bool) -> str:
    """How a heredoc (a `_heredoc_spans` entry) is read: "shell", "code" or
    "text". The programs it feeds are its own command's, on either side of
    its operator, each command its output is piped into, and each command
    it is a substitution in (`git commit -m "$(cat <<EOF`), unwrapped as the
    argv pass unwraps them: text only when all of them read text, code when
    the rest are interpreters, and commands otherwise (an unknown program or
    none, as in `done <<EOF` or `{ bash; } <<EOF`), and for a body never
    closed or a command that began on an earlier line or goes on after the
    body (codereview 2026-09-30d)."""
    n, m, fresh, nested, _first, closing = span
    line = lines[n]
    post = _RAW_REDIRECTION.sub(" ", line[m.end():]).replace("|&", "|")
    if runs_script or closing is None or not fresh or line.endswith("\\") \
            or re.search(r"[(`]|\|\s*$", post):
        return "shell"
    nxt = lines[closing + 1] if closing + 1 < len(lines) else ""
    if nested and (post.strip() or nxt.endswith("\\")
                   or not re.match(r"\s*\)[\s\"']*(?:$|;|&&|\|\|)", nxt)):
        return "shell"  # a word of a command that goes on after the body
    *outer, own = re.split(r"\$?\(", _RAW_REDIRECTION.sub(" ", line[:m.start()]))
    head, *piped = re.split(r"[;&]|\|\|", post)[0].split("|")
    heads = [re.split(r"[;&|]", own)[-1] + head, *piped]
    for o in outer:  # only `x=$(...)` runs its substitution's output nowhere
        o = re.split(r"[;&|]", o)[-1]
        if not re.fullmatch(r"(?:\s*[A-Za-z_]\w*=\S*)+", o):
            heads.append(o)
    progs = [os.path.basename(a[0]) if a else "" for h in heads
             for a in _unwrap([w.strip("'\"") for w in h.split()]) or [[]]]
    if all(p in TEXT_READERS for p in progs):
        return "text"
    return "code" if all(p in TEXT_READERS or INTERPRETERS.match(p) for p in progs) \
        else "shell"


_DASH_C = re.compile(r"\b(?:python[0-9.]*|perl|node|ruby|php)\s+(?:-\w+\s+)*-[ce]\s+"
                     r"(\"(?:[^\"\\]|\\.)*\"|'[^']*')")


def _code_bodies(command: str) -> list[str]:
    """The interpreter code a line carries: its heredocs fed to an
    interpreter, and its `-c` / `-e` strings. A body never closed, and a
    command the heredoc reader does not follow, are read as code too."""
    out = [m.group(1)[1:-1] for m in _DASH_C.finditer(command)]
    if "<<" in command:
        lines = command.split("\n")
        spans = _heredoc_spans(lines)
        if spans is None:
            return [*out, command]
        for s in spans:
            if s[5] is None:
                out.append("\n".join(lines[s[4]:]))
            elif _heredoc_kind(lines, s, False) == "code":
                out.append("\n".join(lines[s[4]:s[5]]))
    return out


def _skeleton(lines: list[str], spans: list[tuple]) -> str:
    """The command without its heredoc bodies (one never closed stays): the
    words the shell itself reads (a body's prose, "the source of truth", is
    never a script run)."""
    body = {j for s in spans if s[5] is not None for j in range(s[4], s[5])}
    return "\n".join(x for j, x in enumerate(lines) if j not in body)


def _read_heredocs(command: str) -> tuple[str, str]:
    """(the line for the gated-verb, protected-file and directory passes;
    the line for the credential pass). A shell's heredoc is kept in both, an
    interpreter's whole for credentials and only its lines that run a
    program for the rest, and text is dropped from both. A body never
    closed, and every body of a command the heredoc reader does not follow,
    is commands."""
    lines = command.split("\n")
    spans = _heredoc_spans(lines) if "<<" in command else None
    if not spans:
        return command, command
    runs_script = bool(_RUNS_SCRIPT.search(_skeleton(lines, spans)))
    drop_run: set[int] = set()
    drop_cred: set[int] = set()
    for s in spans:
        kind = _heredoc_kind(lines, s, runs_script)
        if kind == "text":
            drop_run.update(range(s[4], s[5]))
            drop_cred.update(range(s[4], s[5]))
        elif kind == "code":
            drop_run.update(j for j in range(s[4], s[5]) if not _RUNS.search(lines[j]))
    return ("\n".join(x for j, x in enumerate(lines) if j not in drop_run),
            "\n".join(x for j, x in enumerate(lines) if j not in drop_cred))


def _split_commands(command: str) -> list[list[str]]:
    """The simple commands in a line, each as argv, across ; && || | & and
    newlines, subshell parentheses, and $( ) / backticks. A redirection is
    left out of its command and its target comes back as an entry of its
    own, `[">", target]`, judged as a path and never run. A `#` inside a
    word is a word character, as in bash."""
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
                # A separator is never the target: the `;` that stands for a
                # backtick or `$(` (`echo x > $(cmd)`) starts the command bash
                # runs (security WARN 2026-09-30).
                if not (tok and set(tok) <= set(";&|\n")):
                    out.append([">", tok])  # `cat < ~/.s?h/key`: the target is a path
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


_TOO_DEEP = ["(nested past MAX_NESTING)"]  # what _unwrap gives past the limit


def _unwrap(argv: list[str], depth: int = 0) -> list[list[str]]:
    """Strip env assignments and process wrappers; a shell given a script
    (`bash -lc '...'`, `sh -ec '...'`), a shell running a file, and `eval`
    are read as the commands they run, to MAX_NESTING levels (past them,
    `[_TOO_DEEP]`)."""
    if depth > MAX_NESTING:
        return [_TOO_DEEP]
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
            return [c for part in _split_commands(" ".join(argv[i + 1:]))
                    for c in _unwrap(part, depth + 1)]
        if base in SHELLS:
            j = i + 1
            while j < len(argv) and argv[j].startswith("-"):
                if not argv[j].startswith("--") and "c" in argv[j][1:]:
                    if j + 1 < len(argv):
                        return [c for part in _split_commands(argv[j + 1])
                                for c in _unwrap(part, depth + 1)]
                    return []
                j += 1
            if j < len(argv):
                return _unwrap(argv[j:], depth + 1)  # `bash some/script args`: the script runs
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


def _resolve(word: str, cwd: str) -> str:
    """A path argument as the shell will see it: ~ and $HOME expanded,
    relative to the working directory, `.` and `..` folded, and a brace
    group widened to a glob (`.s{s,x}h` is `.s*h`)."""
    w = word.replace("${HOME}", _HOME).replace("$HOME", _HOME)
    n = "{" in w
    while n:
        w, n = re.subn(r"\{[^{}]*\}", "*", w)
    w = os.path.expanduser(w)
    if not os.path.isabs(w):
        w = os.path.join(cwd, w)
    return os.path.normpath(w)


_LOCATION_PARTS = tuple((loc, loc.strip("/").split("/")) for loc in CREDENTIAL_LOCATIONS)
_GLOB = re.compile(r"[*?[]")


def _credential_relation(path: str) -> tuple[str, str] | None:
    """How a resolved path, literal or a glob, meets a credential location,
    compared component by component (fnmatch for a glob: `~/.con*/gh`):
    ("inside", loc) when every compared component matches and the path is
    as long or longer, ("holds", loc) when it is shorter, a folder above the
    location. Inside wins."""
    parts = [p for p in path.split("/") if p]
    glob = _GLOB.search(path)
    held = None
    for loc, loc_parts in _LOCATION_PARTS:
        n = min(len(parts), len(loc_parts))
        if parts[:n] == loc_parts[:n] or glob and all(
                fnmatch.fnmatchcase(name, pat)
                for name, pat in zip(loc_parts, parts, strict=False)):  # up to the shorter
            if len(parts) >= len(loc_parts):
                return "inside", loc
            held = held or ("holds", loc)
    return held


def _inside_credentials(path: str) -> str | None:
    """The credential location a resolved path is, or is inside."""
    rel = _credential_relation(path)
    return rel[1] if rel and rel[0] == "inside" else None


def _looks_like_path(word: str) -> bool:
    return (word.startswith(("/", "~", ".", "$HOME", "${HOME}")) or "/" in word) \
        and not word.startswith("-")


def _tree_roots(argv: list[str]) -> list[str]:
    """The paths a tree reader reads: its non-option words, and the working
    directory for a searcher that reads it by default."""
    base = os.path.basename(argv[0])
    words = [a for a in argv[1:] if not a.startswith("-")]
    recursive_grep = base in ("grep", "egrep", "fgrep") and any(
        a in ("--recursive", "--dereference-recursive")
        or (a.startswith("-") and not a.startswith("--") and ("r" in a or "R" in a))
        for a in argv[1:])
    if base in TREE_BY_DEFAULT or recursive_grep:
        words.append(".")
    return words


def _gated(argv: list[str]) -> str | None:
    if not argv:
        return None
    exe = os.path.normpath(argv[0])
    if exe.endswith("bin/game") or exe == "game":
        args = argv[1:]
        if args[:2] == ["guard", "install"]:
            return "bin/game guard install (the live guard)"
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


def _raw_words(segment: str) -> list[str]:
    """A segment's words for the raw gated-verb pass: quotes, `$( )`,
    backticks, list brackets and commas are separators (a quoted
    `$(bin/game ...)`, `subprocess.run(["bin/game", ...])`). Redirections
    are already gone (`_RAW_REDIRECTION`), so none ends the words after it
    (`bin/game prod >/dev/null invite create`)."""
    return [w for w in re.split(r"[\s()`$\"'=,\[\]]+", segment) if w]


# The live guard (its installed copy) and the permission settings: changing
# them asks the operator (codereview 2026-09-29c: an injected instruction's
# first move would be to loosen them). The repo's tools/agent_guard.py is
# ordinary code; it goes live only through `bin/game guard install`.
GUARD_HOME = os.path.join(_HOME, ".local", "share", "daydream", "guard")
PROTECTED = re.compile(r"(^|/)\.claude/settings[^/]*\.json$|"
                       r"(^|/)\.local/share/daydream/guard(/|$)|" + re.escape(GUARD_HOME))
_PROTECTED_WORD = r"[^\s;&|<>'\"]*(?:\.claude/settings[^/\s;&|<>'\"]*\.json|" \
                  r"\.local/share/daydream/guard[^\s;&|<>'\"]*)"
# A protected path as a whole string literal in code (`p = '.claude/settings.json'`).
_PROTECTED_LITERAL = re.compile(r"['\"]((?:[^'\"\s]*/)?(?:\.claude/settings[^'\"/\s]*\.json|"
                                r"\.local/share/daydream/guard[^'\"\s]*))['\"]")
# A redirection whose target is a protected file.
_WRITES_TO = re.compile(r"(?:>\||>>?|&>>?)\s*['\"]?" + _PROTECTED_WORD)
# Interpreter code that writes, moves or removes a file.
_CODE_WRITES = re.compile(r"\.write\(|write_text|write_bytes|open\([^)]*['\"][wax]b?\+?['\"]|"
                          r"shutil\.(copy|move)|os\.(replace|rename|remove|unlink)|\.unlink\(|"
                          r"\.rename\(|\.replace\(")
# Writers: where each writes (the last operand, every operand, or -i files).
_TO_LAST = {"cp", "mv", "install", "ln", "rsync", "scp"}
_TO_ALL = {"tee", "rm", "truncate", "chmod", "chown", "unlink", "shred", "touch"}
_IN_PLACE = {"sed", "perl"}


def _find_runs(argv: list[str]) -> list[list[str]]:
    """The commands a find runs on what it finds (`-exec`, `-execdir`, `-ok`,
    `-okdir`), with `{}` read as each path it starts from."""
    i = 1
    while i < len(argv) and re.fullmatch(r"-[HLP]|-O\d*|-D", argv[i]):
        i += 2 if argv[i] == "-D" else 1
    roots = []
    while i < len(argv) and not argv[i].startswith("-") and argv[i] not in ("(", "!", ","):
        roots.append(argv[i])
        i += 1
    runs = []
    while i < len(argv):
        if argv[i] in ("-exec", "-execdir", "-ok", "-okdir"):
            j = next((k for k in range(i + 1, len(argv)) if argv[k] in (";", "+")), len(argv))
            runs += [[w.replace("{}", r) for w in argv[i + 1:j]] for r in roots or ["."]]
            i = j
        i += 1
    return [r for r in runs if r]


def _protected_write(run: str, cred: str) -> str | None:
    """The protected file a command writes, moves or removes, if any:
    reading, testing or committing one never asks (2026-09-30: any `>` on a
    line that named one, `2>&1` included, used to ask)."""
    words = re.findall(r"[^\s'\";|&<>()=]+", cred)  # `--output=PATH`, `of=PATH`
    hits = [w for w in words if PROTECTED.search(w)]
    if not hits:
        return None
    m = _WRITES_TO.search(run)
    if m:
        return m.group(0).lstrip(">|&").strip(" '\"")
    argvs = [argv for part in _split_commands(run) for argv in _unwrap(part)]
    for argv in argvs:  # it grows: what a find runs is a command of its own
        if not argv or argv is _TOO_DEEP:
            continue
        base = os.path.basename(argv[0])
        ops = [a for a in argv[1:] if not a.startswith("-")]
        if base in _TO_LAST and ops and PROTECTED.search(ops[-1]):
            return ops[-1]
        if INTERPRETERS.match(base) and "-c" not in argv and "-e" not in argv:
            # A script given a protected path may write it: it asks, as
            # before (its own code is not read).
            for a in ops:
                if PROTECTED.search(a):
                    return a
        # In place: `-i` in any short-option cluster (`-Ei`, `-ni`, `-pi`)
        # or `--in-place` (security WARN 2026-09-30d); a second operand is
        # uniq's output.
        if base in _TO_ALL or base == "uniq" and len(ops) > 1 or base in _IN_PLACE and any(
                a.startswith("--i") or re.match(r"-[^-]", a) and "i" in a for a in argv[1:]):
            for a in ops[1:] if base == "uniq" else ops:
                if PROTECTED.search(a):
                    return a
        for i, a in enumerate(argv[1:], 1):  # sed's w and W, sort -o, any --output
            nxt = argv[i + 1] if i + 1 < len(argv) else ""
            m = re.search(r"[wW]\s*(" + _PROTECTED_WORD + ")", a) if base == "sed" else None
            if m:
                out = m.group(1)
            elif a.partition("=")[0] in ("--out", "--outp", "--outpu", "--output"):
                out = a.partition("=")[2] or nxt
            elif base == "sort" and re.match(r"-[^-]*o", a):
                out = a[a.index("o") + 1:] or nxt
            else:
                continue
            if PROTECTED.search(out):
                return out
        if base == "dd":
            for a in argv[1:]:
                if a.startswith("of=") and PROTECTED.search(a[3:]):
                    return a[3:]
        if base == "git" and argv[1:2] and argv[1] in ("checkout", "restore", "rm", "mv",
                                                       "apply", "stash"):
            for a in argv[2:]:
                if PROTECTED.search(a):
                    return a
        if base == "find":
            argvs += [c for s in _find_runs(argv) for c in _unwrap(s)]
    for code in _code_bodies(cred):
        if _CODE_WRITES.search(code):
            m = _PROTECTED_LITERAL.search(code)
            if m:
                return m.group(1)
    return None


_DENY_CREDENTIALS = "{} holds this box's credentials; the agent does not open it"
_DENY_TOKEN = "the GitHub token stays where it is"
_ASK_GATED = "{}: this mints access, reaches players, removes something or changes the " \
             "edge or root; the operator confirms it"


def decide(payload: dict) -> tuple[str, str] | None:
    """The guard's decision, with a subagent's ask made a deny: a subagent
    never stops for the operator; it reports what it could not do."""
    got = _decide(payload)
    if got and got[0] == "ask" and (payload.get("agent_id") or payload.get("agent_type")):
        return "deny", f"{got[1]}. A subagent does not run this: say so in your report, and " \
                       "the main session decides"
    return got


# A find that only lists names prints no file's contents; these print or act
# on each file it finds.
_FIND_ACTS = {"-exec", "-execdir", "-ok", "-okdir", "-delete", "-fprint", "-fprint0",
              "-fprintf", "-fls"}
# ...and what its names may reach and still be only listed: text filters
# reading them on stdin (security WARN 2026-09-30d: `| timeout 5 xargs cat`,
# `| while IFS= read`, `cat $(find ...)` and `| grep x | xargs cat` read files).
_LIST_FILTERS = {"head", "tail", "wc", "sort", "uniq", "grep", "cut"}
# Redirections that write no file: to /dev/null, one stream to another,
# and the errors.
_QUIET_REDIRECTION = re.compile(r"\d*>&\d+-?|\d*&?>>?\s*/dev/null\b|2>>?\s*[^\s;&|]+")


def _finds_list_only(run: str) -> bool:
    """Whether every find in a command only prints names: none inside a
    substitution, a subshell or a group, no output of its pipeline written
    to a file, and every later command of its pipeline a text filter."""
    text = re.sub(r"\\[()]", "", run)  # find's own \( \)
    if re.search(r"[()`]|(?:^|[\s;&|])[{}](?=[\s;&|]|$)", text):
        return False
    text = _QUIET_REDIRECTION.sub(" ", text).replace("|&", "|").replace("&>", ">") \
        .replace(">&", ">")
    for pipeline in re.split(r"\|\||[;&\n]", text):
        stages = pipeline.split("|")
        for i, stage in enumerate(stages):
            if "find" not in stage or not any(
                    a and os.path.basename(a[0]) == "find" for a in _unwrap(stage.split())):
                continue
            if ">" in "".join(stages[i:]):
                return False
            for later in stages[i + 1:]:
                words = [w.strip("'\"") for w in later.split()]
                progs = [os.path.basename(a[0]) for a in _unwrap(words) if a]
                ops = [w for w in words[1:] if not w.startswith("-")]
                if not progs or any(p not in _LIST_FILTERS for p in progs) \
                        or {"xargs", "parallel"} & {os.path.basename(w) for w in words} \
                        or "sort" in progs and any(re.match(r"-[^-]*o|--o", w) for w in words) \
                        or "uniq" in progs and len(ops) > 1:
                    return False
    return True


def _decide(payload: dict) -> tuple[str, str] | None:
    tool = payload.get("tool_name")
    inp = payload.get("tool_input") or {}
    if tool in ("Read", "Edit", "Write", "NotebookEdit"):
        path = str(inp.get("file_path") or inp.get("notebook_path") or "")
        p = _names_credentials([path]) or (
            _inside_credentials(_resolve(path, payload.get("cwd") or os.getcwd()))
            if path else None)
        if p:
            return "deny", _DENY_CREDENTIALS.format(p)
        if tool != "Read" and PROTECTED.search(path):
            return "ask", f"{path} guards this session's permissions; the operator confirms a change"
        return None
    if tool != "Bash":
        return None
    command = str(inp.get("command") or "")
    # What the shell runs, and what may read a file (_read_heredocs): the
    # credential passes read `cred`, the rest `run`.
    run, cred = _read_heredocs(command)
    # Over the raw line, before any parsing: a credential path anywhere,
    # redirection targets included (`cat < file`), and the commands that
    # print a token without naming a file (security WARN 2026-09-29: the
    # parsed argv left redirection targets and comment-broken lines out).
    p = _names_credentials(re.findall(r"\S+", cred))
    if p:
        return "deny", _DENY_CREDENTIALS.format(p)
    # A deny found later still wins over an ask found here (security NOTE
    # 2026-09-29): the first ask is kept and returned only at the end.
    ask: str | None = None
    # The raw patterns below outlast the hook's timeout on a long enough line
    # (security WARN 2026-09-30): a line over the limit skips them and asks,
    # and the parsed pass still reads it for a deny.
    raw = run
    if len(command) > MAX_COMMAND_CHARS:
        raw = ""
        ask = f"a command over {MAX_COMMAND_CHARS // 1024} KB is more than the guard reads " \
              "in its time; the operator confirms it"
    if TOKEN_PRINTERS.search(re.sub(r"['\"\\]", "", cred if raw else "")):  # quoting hides nothing
        return "deny", _DENY_TOKEN
    # Gated verbs on the raw text too: inside a quoted `$(...)` the parser
    # sees one word (`out="$(bin/game prod invite create ...)"`; security
    # WARN 2026-09-29).
    for segment in re.split(r"[;&|\n]+", _RAW_REDIRECTION.sub(" ", raw)):
        words = _raw_words(segment)
        for i, w in enumerate(words):
            if os.path.normpath(w).endswith("bin/game"):
                why = _gated(words[i:])
                if why and ask is None:
                    ask = _ASK_GATED.format(why)
    hit = _protected_write(raw, cred if raw else "")
    if hit and ask is None:
        ask = f"{hit} guards this session's permissions; the operator confirms a change"
    # Every directory a command may run in: a cd that never takes effect (a
    # subshell, a failed cd before `;`) leaves the line where it was, so each
    # is a candidate and relative words are judged from all of them
    # (codereview 2026-09-30b).
    cwds = [payload.get("cwd") or os.getcwd()]
    for argv in (c for part in _split_commands(run) for c in _unwrap(part)):
        if argv is _TOO_DEEP:  # unread; a deny in another part still wins
            ask = ask or f"a command nested past {MAX_NESTING} levels of eval or a shell is " \
                         "more than the guard reads; the operator confirms it"
            continue
        if not argv:
            continue
        p = _names_credentials(argv)
        if p:
            return "deny", _DENY_CREDENTIALS.format(p)
        for w in argv[1:]:
            if _looks_like_path(w):
                for path in dict.fromkeys(_resolve(w, c) for c in cwds):
                    loc = _inside_credentials(path)
                    if loc:
                        return "deny", _DENY_CREDENTIALS.format(loc)
        base = os.path.basename(argv[0])
        if base in ("cd", "pushd"):
            # The rest of the line may run there (`cd ~ && grep -r token .`);
            # `cd -` returns to a directory already counted.
            dirs = [a for a in argv[1:] if not a.startswith("-")]
            if not dirs and "-" not in argv[1:]:
                dirs = [_HOME]
            for new in [_resolve(d, c) for d in dirs for c in cwds]:
                if new in cwds:
                    continue
                loc = _inside_credentials(new)
                if loc:  # every bare file name after this is a credential's
                    return "deny", _DENY_CREDENTIALS.format(loc)
                if len(cwds) < MAX_CWDS:
                    cwds.append(new)
                elif ask is None:
                    ask = "the guard cannot follow this many directory changes; the " \
                          "operator confirms it"
            continue
        if base == "gh" and (argv[1:3] == ["auth", "token"] or (
                argv[1:2] == ["auth"] and any(
                    a == "--show-token" or re.fullmatch(r"-[A-Za-z]*t[A-Za-z]*", a)
                    for a in argv[2:]))):
            return "deny", _DENY_TOKEN
        if ask is not None:
            continue  # keep reading for a deny
        lists_only = base == "find" and not _FIND_ACTS & set(argv) and _finds_list_only(run)
        if base in SEARCHERS and not lists_only and any(a in BROAD_ROOTS for a in argv[1:]):
            ask = f"a {base} over your home or a system directory can print credentials"
        elif base in TREE_READERS and not lists_only and any(  # above a credential, or in it
                _credential_relation(_resolve(w, c)) for w in _tree_roots(argv) for c in cwds):
            ask = f"a {base} over a folder that holds this box's credentials can print or " \
                  "copy them; the operator confirms it"
        elif base == "gh" and argv[1:2] in (["gist"], ["ssh-key"], ["secret"]):
            ask = f"gh {argv[1]} can publish or grant access; the operator decides"
        else:
            why = _gated(argv)
            if why:
                ask = _ASK_GATED.format(why)
    return ("ask", ask) if ask else None


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except ValueError:
        return 0
    try:
        got = decide(payload)
    except Exception as e:  # a crash would let the command run with no decision
        got = ("ask", f"the guard failed on this command ({type(e).__name__}); the operator "
                      "confirms it")
    if got:
        decision, reason = got
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse", "permissionDecision": decision,
            "permissionDecisionReason": reason}}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
