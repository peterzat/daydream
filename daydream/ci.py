"""GitHub Actions, read from the shell (2026-09-29: CI had failed on every
push for a day and nobody saw it, since the operator rarely opens
github.com).

    bin/game ci               the latest runs on main
    bin/game ci watch [ref]   wait for the run of a commit (HEAD by default);
                              exit 1 if it fails, so a red run is never silent
    bin/game ci --line        one line for `bin/game status`

`bin/game prod plan` says when main is red, `bin/game prod check` carries a
CI line, and a publish watches its own push's run before it deploys
(docs/runbooks/publish.md). It reads through the `gh` CLI, already
authenticated on the box; without `gh` (or a repo without Actions) it says so
and passes.
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
_CONTROL = re.compile(r"[\x00-\x1f\x7f-\x9f]")


def _gh(*args: str, timeout: float = 30.0) -> str | None:
    try:
        r = subprocess.run(["gh", *args], cwd=REPO, capture_output=True, text=True,
                           timeout=timeout)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def runs(branch: str = "main", limit: int = 5, sha: str | None = None) -> list[dict] | None:
    """The newest runs on a branch (optionally only one commit's), newest
    first, or None when GitHub cannot be asked. Through the REST API (`gh
    api`), which any `gh` version speaks: older `gh run list` has no branch
    or commit filter."""
    # Pushes only: a pull request from any fork's `main` is also listed under
    # branch=main, which would put a stranger's title in this output and let a
    # newer fork run hide a red main (security WARN 2026-09-29).
    # (Filtered here, not with the API's `event=` parameter, which is served
    # from a lagging index and returned hours-old runs as the newest.)
    query = f"branch={branch}&per_page={limit * 4}" + (f"&head_sha={sha}" if sha else "")
    out = _gh("api", f"repos/{{owner}}/{{repo}}/actions/runs?{query}")
    if out is None:
        return None
    try:
        got = json.loads(out or "{}")
    except ValueError:
        return None
    if isinstance(got, list):  # already in our shape (the tests' fakes)
        return got
    shaped = [_shape(r) for r in (got.get("workflow_runs") or [])
              if isinstance(r, dict) and r.get("event", "push") == "push" and _ours(r)]
    return sorted(shaped, key=lambda r: r["createdAt"], reverse=True)[:limit]  # newest first


def _ours(r: dict) -> bool:
    """A run of this repository's own commits (never a fork's)."""
    head, base = r.get("head_repository") or {}, r.get("repository") or {}
    return not head or not base or head.get("full_name") == base.get("full_name")


def _subject(sha: str) -> str:
    """The commit's subject from local git: the title printed is ours,
    never text GitHub relays."""
    r = subprocess.run(["git", "-C", str(REPO), "log", "-1", "--format=%s", sha],
                       capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else "(a commit not in this checkout)"


def _shape(r: dict) -> dict:
    sha = str(r.get("head_sha", ""))
    return {"databaseId": r.get("id"), "status": r.get("status"),
            "conclusion": r.get("conclusion"), "headSha": sha,
            "displayTitle": _CONTROL.sub("", _subject(sha)) if sha else "",
            "createdAt": r.get("created_at", ""), "url": r.get("html_url", "")}


def state(run: dict) -> str:
    """"passed", "failed", "running", or the conclusion as GitHub gives it."""
    if run.get("status") != "completed":
        return "running"
    c = run.get("conclusion") or ""
    return {"success": "passed", "failure": "failed", "timed_out": "failed",
            "startup_failure": "failed"}.get(c, c or "unknown")


def describe(run: dict) -> str:
    return (f"{state(run)} at {str(run.get('headSha', ''))[:7]} "
            f"({str(run.get('displayTitle', ''))[:70]})")


_SHA = re.compile(r"^[0-9a-f]{40}$")


def branch_head(branch: str = "main") -> str | None:
    """The branch's tip as GitHub has it, or None when it cannot be read."""
    out = _gh("api", f"repos/{{owner}}/{{repo}}/git/ref/heads/{branch}")
    try:
        got = json.loads(out or "null")
    except ValueError:
        return None
    sha = (got.get("object") or {}).get("sha") if isinstance(got, dict) else None
    return sha if isinstance(sha, str) and _SHA.match(sha) else None


def main_status(branch: str = "main") -> tuple[str, str]:
    """(verdict, words) for the branch: verdict is "passed", "failed",
    "running" or "unknown". A run in progress on top of a failed one says
    both, so a red main is never hidden behind a new push. The verdict is
    the branch tip's own run: GitHub's list of runs can lag (2026-10-03 it
    named a July run as main's newest), so when its newest is not for the
    tip, the tip's runs are asked for by commit, and with none listed the
    verdict is "unknown", never an older commit's "passed"."""
    got = runs(branch, limit=5)
    if got is None:
        return "unknown", "GitHub not reachable (is `gh` installed and signed in?)"
    if not got:
        return "unknown", f"no runs on {branch}"
    head = branch_head(branch)
    if head and got[0].get("headSha") != head:
        tip = runs(branch, limit=5, sha=head)
        if not tip:
            return "unknown", (f"no run listed for {branch}'s tip {head[:7]} (just pushed, or "
                               f"GitHub's list is stale); the newest listed is {describe(got[0])}")
        got = tip + [r for r in got if r.get("headSha") != head]
    newest = got[0]
    if state(newest) != "running":
        return state(newest), describe(newest)
    done = next((r for r in got if state(r) != "running"), None)
    words = describe(newest)
    if done is not None and state(done) == "failed":
        words += f"; the last finished run {describe(done)}"
    return "running", words


def _head(ref: str) -> str:
    return subprocess.run(["git", "-C", str(REPO), "rev-parse", ref], capture_output=True,
                          text=True, check=True).stdout.strip()


def watch(ref: str = "HEAD", branch: str = "main", appear_s: float = 180.0,
          finish_s: float = 1200.0, poll_s: float = 15.0, say=print,
          sleep=time.sleep) -> int:
    """Wait for the run of `ref` on `branch` and report it: 0 passed, 1 failed
    or timed out, 2 GitHub unreachable."""
    sha = _head(ref)
    waited = 0.0
    run = None
    while True:
        got = runs(branch, limit=5, sha=sha)
        if got is None:
            say("ci: GitHub not reachable (is `gh` installed and signed in?)")
            return 2
        run = got[0] if got else None
        if run is not None and state(run) != "running":
            break
        limit = appear_s if run is None else finish_s
        if waited >= limit:
            say(f"ci: no finished run for {sha[:7]} after {int(waited)} s"
                + (f" ({run.get('url')})" if run else " (was it pushed?)"))
            return 1
        sleep(poll_s)
        waited += poll_s
    say(f"ci: {describe(run)}")
    if state(run) != "passed":
        say(f"ci: RED. See {run.get('url')} (`gh run view {run.get('databaseId')} --log-failed`); "
            "fix it before publishing.")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="bin/game ci", description=__doc__.split("\n")[0])
    p.add_argument("--line", action="store_true", help="one line, for bin/game status")
    sub = p.add_subparsers(dest="cmd")
    w = sub.add_parser("watch", help="wait for a commit's run; exit 1 if it fails")
    w.add_argument("ref", nargs="?", default="HEAD")
    args = p.parse_args(argv)
    if args.cmd == "watch":
        return watch(args.ref)
    verdict, words = main_status()
    if args.line:
        print(f"ci: {'RED: ' if verdict == 'failed' else ''}{words}")
        return 0
    got = runs(limit=8) or []
    print(f"main: {verdict}: {words}")
    for r in got:
        print(f"  {describe(r)}  {r.get('createdAt', '')}")
    return 1 if verdict == "failed" else 0


if __name__ == "__main__":
    sys.exit(main())
