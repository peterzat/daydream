"""The admin console for who may play: `bin/game account ...` and
`bin/game invite ...` (SPEC 2026-09-27 criteria 2 and 4).

The shell is the admin console (docs/GOING-LIVE.md section 4): roles,
invites, disabling and session revocation live here and nowhere on the web.
Against prod, run through `bin/game prod account|invite ...`, which executes
the prod release's code with prod's environment.
"""

from __future__ import annotations

import argparse
import getpass
import json
import os
import secrets
import sys
from pathlib import Path

from daydream import accounts, config


def _fmt_when(s: str | None) -> str:
    return (s or "-").replace("T", " ").replace("Z", "")


def _read_password(args) -> tuple[str, bool]:
    """(password, generated?) from --password-stdin, --generate, or a prompt."""
    if args.generate:
        return secrets.token_urlsafe(15), True
    if args.password_stdin:
        return sys.stdin.readline().rstrip("\n"), False
    if not sys.stdin.isatty():
        raise accounts.AccountError("no terminal to prompt on: use --password-stdin or --generate")
    pw = getpass.getpass("password: ")
    if pw != getpass.getpass("again: "):
        raise accounts.AccountError("the two passwords differ")
    return pw, False


def invite_message(for_name: str, link: str, expires_at: str, kind: str = "join") -> str:
    """A plain message the operator can paste into a text."""
    first = (for_name.split() or ["there"])[0]
    day = _fmt_when(expires_at)[:10]
    if kind == "reset":
        return (f"Hi {first}, here's a link to set a new daydream password: {link} "
                f"(it works once, until {day}).")
    from daydream import instance

    blurb = instance.load()["invite_blurb"]
    return (f"Hi {first}! You're invited to daydream, {blurb} (I'm {config.operator_name()}). "
            f"Your invitation: {link} (it works once, until {day}). Open it, pick a "
            f"username and password, and you're in.")


def cmd_account(args) -> int:
    if args.acmd == "create":
        pw, generated = _read_password(args)
        row = accounts.create_account(args.username, pw, display_name=args.name,
                                      role="admin" if args.admin else "player")
        print(f"created {row['username']} ({row['role']}, {row['id']})")
        if generated:
            print(f"password: {pw}   (shown once; change it after signing in)")
        return 0
    if args.acmd == "list":
        rows = accounts.list_accounts()
        if not rows:
            print("no accounts")
        for r in rows:
            state = "DISABLED" if r["disabled_at"] else "active"
            print(f"{r['username']:<24} {r['role']:<7} {state:<8} {r['display_name']:<24} "
                  f"last login {_fmt_when(r['last_login_at'])}  ({r['id']})")
        return 0
    if args.acmd == "role":
        row = accounts.set_role(args.username, args.role)
        print(f"{row['username']} is now {row['role']}")
        return 0
    if args.acmd in ("disable", "enable"):
        row = accounts.set_disabled(args.username, args.acmd == "disable")
        print(f"{row['username']} {'disabled (sessions revoked)' if row['disabled_at'] else 'enabled'}")
        return 0
    if args.acmd == "delete":
        return _delete_account(args.username, confirmed=args.yes)
    if args.acmd == "rename":
        row = accounts.set_display_name(args.username, args.display_name)
        print(f"{row['username']} is shown as {row['display_name']!r}")
        return 0
    if args.acmd == "sessions":
        if args.revoke:
            n = accounts.revoke_sessions(args.username)
            print(f"revoked {n} session(s) for {args.username}")
            return 0
        rows = accounts.list_sessions(args.username)
        if not rows:
            print("no sessions")
        for r in rows:
            print(f"{r['id']}  seen {_fmt_when(r['last_seen_at'])}  expires "
                  f"{_fmt_when(r['expires_at'])}  {'left ' if r['left_at'] else ''}{r['user_agent']}")
        return 0
    if args.acmd == "cli-cookie":
        print(cli_cookie(Path(args.cache) if args.cache else None))
        return 0
    raise AssertionError(args.acmd)


def _delete_account(key: str, *, confirmed: bool) -> int:
    """Remove a person for good: their dreamers in the live world (carried
    things left in the room, as `world delete-toon` does), everything those
    dreamers typed (the private input log), the lines addressed only to
    them and the Jev decisions about their words, then the account, its sessions, invites and throttle counters. What
    stays: the shared event history, and each dreamer's portrait in the art
    keep with its provenance (retired, not erased: docs/DATA-LIFECYCLE.md).
    Without --yes it only says what would go."""
    from daydream import db, events, inputs, toons

    row = accounts._require_account(key)
    world = config.live_db_path()
    dreamers = []
    if world.exists():
        db.init_live()
        dreamers = toons.owned_toons(row["id"])
    sessions = len(accounts.list_sessions(row["id"]))
    names = ", ".join(f"{t.name} ({t.id})" for t in dreamers) or "none in the live world"
    print(f"account {row['username']} ({row['id']}, {row['role']}): {sessions} session(s); "
          f"dreamers: {names}")
    if not confirmed:
        print("nothing deleted; re-run with --yes to delete it for good", file=sys.stderr)
        return 2
    from daydream.jev import ledger as jev_ledger

    for t in dreamers:
        typed = inputs.forget_toon(t.id)
        toons.delete_slot(t.slot)
        private = events.forget_private(t.id)
        forgot = _forget_dreamer_state(t.world_id, t.id)
        # What Jev decided about their words (daydream/jev/ledger.py).
        judged = jev_ledger.purge_toons([t.id])
        print(f"deleted dreamer {t.name} ({t.id}), {typed} input line(s), {private} private "
              f"line(s), {forgot} story record(s) and {judged} Jev decision(s)")
    accounts.delete_account(row["id"])
    print(f"deleted account {row['username']} ({row['id']})")
    return 0


def _forget_dreamer_state(world_id: str, toon_id: str) -> int:
    """What the world keeps under a dreamer's id (the key shapes in story.py,
    collect.py and api/ws.py): its Book, flags and counters (`pq:<id>:*`),
    and every key ending in `:<id>`: what it said to each resident
    (`talk:<npc>:<id>`), relationships (`rel:`, `relday:`), greetings and
    bystander notes. Then its private finds (`private_to`). Returns how many
    went."""
    from daydream import objects, worldstate

    n = 0
    for key in worldstate.keys(world_id):
        if key.startswith(f"pq:{toon_id}:") or key.endswith(f":{toon_id}"):
            worldstate.delete(world_id, key)
            n += 1
    for thing in objects.things_where_property(world_id, "private_to", toon_id):
        objects.delete(thing.id)
        n += 1
    return n


def cli_cookie(cache: Path | None = None) -> str:
    """A Cookie header value for the CLI's own admin account, so `bin/game
    status` can read the admin-only /status endpoints like any admin. With
    `cache`, the token is kept in that owner-only file and reused while it
    still resolves, so repeated status calls do not pile up sessions."""
    name = config.cookie_name()
    if cache is not None and cache.exists():
        token = cache.read_text().strip()
        if accounts.resolve(token) is not None:
            return f"{name}={token}"
    token, _ = accounts.mint_session("cli-operator", role="admin",
                                     display_name="the command line")
    if cache is not None:
        cache.parent.mkdir(parents=True, exist_ok=True)
        fd = os.open(cache, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(token + "\n")
        os.chmod(cache, 0o600)
    return f"{name}={token}"


def cmd_invite(args) -> int:
    if args.icmd in ("create", "reset"):
        if args.icmd == "create":
            slug, row = accounts.create_invite(args.for_name, days=args.days, note=args.note or "")
        else:
            slug, row = accounts.create_invite(args.name or "", kind="reset",
                                               account=args.username, days=args.days)
        link = config.public_url(f"invite/{slug}")
        msg = invite_message(row["for_name"], link, row["expires_at"], row["kind"])
        if args.json:
            print(json.dumps({"id": row["id"], "kind": row["kind"], "for": row["for_name"],
                              "slug": slug, "link": link, "expires_at": row["expires_at"],
                              "message": msg}))
        else:
            print(f"invite {row['id']} for {row['for_name']} ({row['kind']})")
            print(f"  slug:    {slug}")
            print(f"  link:    {link}")
            print(f"  expires: {_fmt_when(row['expires_at'])} UTC")
            print(f"  message: {msg}")
        return 0
    if args.icmd == "list":
        rows = accounts.list_invites(include_closed=args.all)
        if not rows:
            print("no open invites" if not args.all else "no invites")
        for r in rows:
            state = ("redeemed " + _fmt_when(r["redeemed_at"]) if r["redeemed_at"]
                     else "revoked" if r["revoked_at"] else "expires " + _fmt_when(r["expires_at"]))
            print(f"{r['id']}  {r['kind']:<5} {r['for_name']:<24} {state}")
        return 0
    if args.icmd == "unblock":
        n = accounts.clear_redeem_throttles()
        print(f"invitations reopened ({n} throttle counter(s) cleared)")
        return 0
    if args.icmd == "revoke":
        row = accounts.revoke_invite(args.key)
        print(f"revoked {row['id']} ({row['for_name']})")
        return 0
    raise AssertionError(args.icmd)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="bin/game", description=__doc__.split("\n")[0])
    top = p.add_subparsers(dest="top", required=True)

    pa = top.add_parser("account", help="accounts: create, list, role, disable, sessions")
    a = pa.add_subparsers(dest="acmd", required=True)
    c = a.add_parser("create", help="create an account (the operator's own; friends use invites)")
    c.add_argument("username")
    c.add_argument("--name", help="display name (default: the username)")
    c.add_argument("--admin", action="store_true", help="make it an admin account")
    g = c.add_mutually_exclusive_group()
    g.add_argument("--password-stdin", action="store_true", help="read the password from stdin")
    g.add_argument("--generate", action="store_true", help="generate a password and print it once")
    a.add_parser("list", help="list accounts")
    r = a.add_parser("role", help="set an account's role")
    r.add_argument("username")
    r.add_argument("role", choices=accounts.ROLES)
    for name in ("disable", "enable"):
        d = a.add_parser(name, help=f"{name} an account (disable also revokes its sessions)")
        d.add_argument("username")
    de = a.add_parser("delete", help="delete an account for good, with its dreamers "
                                     "(lists what would go without --yes)")
    de.add_argument("username")
    de.add_argument("--yes", action="store_true", help="really delete")
    rn = a.add_parser("rename", help="change an account's display name")
    rn.add_argument("username")
    rn.add_argument("display_name")
    ck = a.add_parser("cli-cookie", help="print a Cookie value for the CLI's admin account")
    ck.add_argument("--cache", help="owner-only file to keep and reuse the token in")
    s = a.add_parser("sessions", help="list (or --revoke) an account's sessions")
    s.add_argument("username")
    s.add_argument("--revoke", action="store_true")

    pi = top.add_parser("invite", help="invites: create, reset, list, revoke")
    i = pi.add_subparsers(dest="icmd", required=True)
    ic = i.add_parser("create", help="mint a single-use join invite")
    ic.add_argument("--for", dest="for_name", required=True, help='who it is for ("Robin Ash")')
    ic.add_argument("--days", type=int, default=accounts.INVITE_DAYS)
    ic.add_argument("--note", default="")
    ic.add_argument("--json", action="store_true")
    ir = i.add_parser("reset", help="mint a password-reset invite for an existing account")
    ir.add_argument("username")
    ir.add_argument("--name", help="who it is for (default: the account's display name)")
    ir.add_argument("--days", type=int, default=3)
    ir.add_argument("--json", action="store_true")
    il = i.add_parser("list", help="list open invites (--all includes used/expired/revoked)")
    il.add_argument("--all", action="store_true")
    i.add_parser("unblock", help="reopen invitations after strangers' guesses paused them")
    iv = i.add_parser("revoke", help="revoke an invite by id (i-...) or slug")
    iv.add_argument("key")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    config.data_dir().mkdir(parents=True, exist_ok=True)
    accounts.init()
    try:
        return cmd_account(args) if args.top == "account" else cmd_invite(args)
    except accounts.AccountError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    finally:
        accounts.close()


if __name__ == "__main__":
    sys.exit(main())
