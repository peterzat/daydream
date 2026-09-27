"""Accounts, sessions, invites and throttles: who may play (SPEC 2026-09-27
criteria 2-4; docs/GOING-LIVE.md section 4).

The single read/write surface for the per-env accounts database
(`config.accounts_db_path()`, migrations in `migrations_accounts/`). It is a
separate database from the world on purpose: a world reset, swap or refresh
never touches who may play.

- **Passwords** are argon2id hashes. An unknown username still pays one
  verification, so response time does not reveal which usernames exist.
- **Sessions** are random 256-bit tokens. Only their sha256 is stored, and
  they are read fresh on every request, so disabling an account or revoking
  its sessions bites on the next request. Each session also has a public id
  (`s-...`), which is what the world DB's `controller_session` holds; the
  token never leaves this module and the cookie.
- **Invites** are two-word slugs (`amber-thimble`), stored as sha256,
  single use, and expiring. A `join` invite creates an account; a `reset`
  invite sets a new password on an existing one.
- **Throttles** are fixed-window failure counters keyed by purpose.

Roles are `player` and `admin`. Nothing here is reachable from the web
except through `daydream/api/auth.py`; role changes are CLI-only
(`daydream/accounts_cli.py`).
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from daydream import config, db

MIGRATIONS_DIR = config.PROJECT_ROOT / "migrations_accounts"
WORDS_DIR = Path(__file__).resolve().parent / "invite_words"

SESSION_DAYS = 30
INVITE_DAYS = 14
MIN_PASSWORD = 10
MAX_PASSWORD = 256
ROLES = ("player", "admin")
USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{2,23}$")
# How stale last_seen_at may get before a request refreshes it (and slides
# the expiry): one write per session per ten minutes, not one per request.
SLIDE_EVERY = timedelta(minutes=10)

# Throttle budgets: (limit of failures, window in seconds).
LOGIN_PER_ADDRESS = (10, 15 * 60)
LOGIN_PER_USERNAME = (5, 15 * 60)
REDEEM_PER_ADDRESS = (5, 10 * 60)
REDEEM_GLOBAL_HOUR = (20, 60 * 60)
REDEEM_GLOBAL_DAY = (40, 24 * 60 * 60)

_conn: sqlite3.Connection | None = None


class AccountError(ValueError):
    """A refused account operation, with a message safe to show the person."""


@dataclass(frozen=True)
class Principal:
    """The signed-in person behind a request."""

    account_id: str
    username: str
    display_name: str
    role: str
    session_id: str
    left: bool

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


# ---- time + connection ----------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(s: str) -> datetime:
    return datetime.strptime(s, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def init(path: Path | None = None) -> sqlite3.Connection:
    """Open the accounts DB and apply pending migrations. Idempotent."""
    global _conn
    if _conn is not None:
        return _conn
    _conn = db.open_db(path or config.accounts_db_path())
    db.init_schema(_conn, MIGRATIONS_DIR)
    return _conn


def get_conn() -> sqlite3.Connection:
    return _conn if _conn is not None else init()


def close() -> None:
    global _conn
    if _conn is not None:
        _conn.close()
        _conn = None


@contextmanager
def _tx():
    """An IMMEDIATE transaction: the write lock is taken up front, so a
    check-then-write (redeeming a single-use invite) is atomic even against
    the CLI writing from another process."""
    conn = get_conn()
    conn.execute("BEGIN IMMEDIATE")
    try:
        yield conn
    except BaseException:
        conn.execute("ROLLBACK")
        raise
    conn.execute("COMMIT")


def _sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ---- passwords ------------------------------------------------------------


_hasher_cache: dict[str, object] = {}


def _hasher():
    """argon2id with the library's RFC 9106 defaults (64 MiB, t=3, p=4). The
    test suite sets DAYDREAM_PASSWORD_HASH_PROFILE=test for a cheap profile;
    hashes encode their parameters, so either verifies either."""
    from argon2 import PasswordHasher

    profile = os.environ.get("DAYDREAM_PASSWORD_HASH_PROFILE", "")
    if profile not in _hasher_cache:
        if profile == "test":
            _hasher_cache[profile] = PasswordHasher(time_cost=1, memory_cost=256, parallelism=1)
        else:
            _hasher_cache[profile] = PasswordHasher()
    return _hasher_cache[profile]


_dummy_hash: str | None = None


def _hash_password(pw: str) -> str:
    return _hasher().hash(pw)


def _verify_password(stored: str, pw: str) -> bool:
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

    try:
        return bool(_hasher().verify(stored, pw))
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def _burn_a_verification(pw: str) -> None:
    """Spend one verification's worth of time on an unknown username."""
    global _dummy_hash
    if _dummy_hash is None:
        _dummy_hash = _hash_password(secrets.token_urlsafe(16))
    _verify_password(_dummy_hash, pw)


def normalize_username(name: str) -> str:
    return (name or "").strip().lower()


def username_problem(username: str) -> str | None:
    if not USERNAME_RE.match(username):
        return ("a username is 3 to 24 characters: lowercase letters, digits, '-' or '_', "
                "starting with a letter or digit")
    return None


def password_problem(pw: str) -> str | None:
    if len(pw or "") < MIN_PASSWORD:
        return f"a password needs at least {MIN_PASSWORD} characters"
    if len(pw) > MAX_PASSWORD:
        return f"a password can be at most {MAX_PASSWORD} characters"
    return None


# ---- accounts -------------------------------------------------------------


def get_account(key: str) -> sqlite3.Row | None:
    """By id (a-...) or username (case-insensitive)."""
    conn = get_conn()
    if key.startswith("a-"):
        row = conn.execute("SELECT * FROM accounts WHERE id = ?", (key,)).fetchone()
        if row is not None:
            return row
    return conn.execute("SELECT * FROM accounts WHERE username = ?",
                        (normalize_username(key),)).fetchone()


def _require_account(key: str) -> sqlite3.Row:
    row = get_account(key)
    if row is None:
        raise AccountError(f"no account {key!r}")
    return row


def list_accounts() -> list[sqlite3.Row]:
    return get_conn().execute("SELECT * FROM accounts ORDER BY created_at, username").fetchall()


def _insert_account(conn, username: str, password: str, display_name: str, role: str,
                    invite_id: str | None) -> str:
    username = normalize_username(username)
    problem = username_problem(username) or password_problem(password)
    if problem:
        raise AccountError(problem)
    if role not in ROLES:
        raise AccountError(f"role must be one of {', '.join(ROLES)}")
    if conn.execute("SELECT 1 FROM accounts WHERE username = ?", (username,)).fetchone():
        raise AccountError("that username is taken")
    account_id = "a-" + secrets.token_hex(6)
    conn.execute(
        "INSERT INTO accounts(id, username, display_name, password_hash, role, created_at,"
        " invite_id) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (account_id, username, (display_name or username).strip()[:80], _hash_password(password),
         role, _iso(_now()), invite_id),
    )
    return account_id


def create_account(username: str, password: str, *, display_name: str | None = None,
                   role: str = "player") -> sqlite3.Row:
    """CLI-side account creation (the operator's own account, test fixtures)."""
    with _tx() as conn:
        account_id = _insert_account(conn, username, password, display_name or username,
                                     role, None)
    return get_account(account_id)


def set_role(key: str, role: str) -> sqlite3.Row:
    if role not in ROLES:
        raise AccountError(f"role must be one of {', '.join(ROLES)}")
    row = _require_account(key)
    get_conn().execute("UPDATE accounts SET role = ? WHERE id = ?", (role, row["id"]))
    return get_account(row["id"])


def set_disabled(key: str, disabled: bool) -> sqlite3.Row:
    """Disabling also revokes every session, so access ends on the next request."""
    row = _require_account(key)
    with _tx() as conn:
        conn.execute("UPDATE accounts SET disabled_at = ? WHERE id = ?",
                     (_iso(_now()) if disabled else None, row["id"]))
        if disabled:
            conn.execute("DELETE FROM sessions WHERE account_id = ?", (row["id"],))
    return get_account(row["id"])


def set_display_name(key: str, display_name: str) -> sqlite3.Row:
    row = _require_account(key)
    name = (display_name or "").strip()[:80]
    if not name:
        raise AccountError("a display name cannot be empty")
    get_conn().execute("UPDATE accounts SET display_name = ? WHERE id = ?", (name, row["id"]))
    return get_account(row["id"])


def change_password(account_id: str, old: str, new: str, *,
                    keep_session_id: str | None = None) -> None:
    """A signed-in person changing their own password. Every other session of
    theirs ends; the one making the change can be kept."""
    row = _require_account(account_id)
    if not _verify_password(row["password_hash"], old or ""):
        raise AccountError("that is not your current password")
    problem = password_problem(new)
    if problem:
        raise AccountError(problem)
    with _tx() as conn:
        conn.execute("UPDATE accounts SET password_hash = ? WHERE id = ?",
                     (_hash_password(new), row["id"]))
        conn.execute("DELETE FROM sessions WHERE account_id = ? AND id IS NOT ?",
                     (row["id"], keep_session_id))


def authenticate(username: str, password: str) -> sqlite3.Row | None:
    """The account for a correct username + password, else None. A disabled
    account never authenticates. Constant-shape: an unknown username still
    pays one argon2 verification."""
    row = get_account(normalize_username(username)) if username else None
    if row is None:
        _burn_a_verification(password or "")
        return None
    if not _verify_password(row["password_hash"], password or ""):
        return None
    if row["disabled_at"]:
        return None
    try:
        if _hasher().check_needs_rehash(row["password_hash"]):
            get_conn().execute("UPDATE accounts SET password_hash = ? WHERE id = ?",
                               (_hash_password(password), row["id"]))
    except Exception:  # a rehash is housekeeping; never fail a login on it
        pass
    return row


# ---- sessions -------------------------------------------------------------


def create_session(account_id: str, user_agent: str = "") -> tuple[str, str]:
    """Mint a session; returns (token, session_id). The token goes only into
    the cookie; the DB keeps its sha256."""
    token = secrets.token_urlsafe(32)
    session_id = "s-" + secrets.token_hex(8)
    now = _now()
    conn = get_conn()
    conn.execute(
        "INSERT INTO sessions(id, token_hash, account_id, created_at, last_seen_at, expires_at,"
        " user_agent) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (session_id, _sha(token), account_id, _iso(now), _iso(now),
         _iso(now + timedelta(days=SESSION_DAYS)), (user_agent or "")[:200]),
    )
    conn.execute("UPDATE accounts SET last_login_at = ? WHERE id = ?", (_iso(now), account_id))
    return token, session_id


def mint_session(username: str, *, role: str = "player", password: str | None = None,
                 display_name: str | None = None) -> tuple[str, Principal]:
    """For tests and agent play (`bin/game play`): make sure the account
    exists, then mint a session in-process with no HTTP login. The shell is
    the admin console, so this is only reachable from the shell."""
    row = get_account(username)
    if row is None:
        row = create_account(username, password or secrets.token_urlsafe(18),
                             display_name=display_name or username, role=role)
    token, _ = create_session(row["id"], "cli")
    principal = resolve(token)
    assert principal is not None
    return token, principal


def resolve(token: str | None) -> Principal | None:
    """The person a session token belongs to, or None (unknown, expired,
    revoked, or a disabled account). Slides the 30-day expiry on use."""
    if not token or len(token) > 200:
        return None
    conn = get_conn()
    row = conn.execute(
        "SELECT s.id AS sid, s.expires_at, s.last_seen_at, s.left_at, a.id AS aid, a.username,"
        " a.display_name, a.role, a.disabled_at FROM sessions s JOIN accounts a"
        " ON a.id = s.account_id WHERE s.token_hash = ?",
        (_sha(token),),
    ).fetchone()
    if row is None or row["disabled_at"]:
        return None
    now = _now()
    if _parse(row["expires_at"]) <= now:
        conn.execute("DELETE FROM sessions WHERE id = ?", (row["sid"],))
        return None
    if now - _parse(row["last_seen_at"]) >= SLIDE_EVERY:
        conn.execute("UPDATE sessions SET last_seen_at = ?, expires_at = ? WHERE id = ?",
                     (_iso(now), _iso(now + timedelta(days=SESSION_DAYS)), row["sid"]))
    return Principal(account_id=row["aid"], username=row["username"],
                     display_name=row["display_name"], role=row["role"],
                     session_id=row["sid"], left=bool(row["left_at"]))


def end_session(token: str | None) -> None:
    """Log out: forget this one session."""
    if token:
        get_conn().execute("DELETE FROM sessions WHERE token_hash = ?", (_sha(token),))


def revoke_sessions(key: str, *, keep_session_id: str | None = None) -> int:
    row = _require_account(key)
    cur = get_conn().execute(
        "DELETE FROM sessions WHERE account_id = ? AND id IS NOT ?",
        (row["id"], keep_session_id),
    )
    return cur.rowcount


def list_sessions(key: str) -> list[sqlite3.Row]:
    row = _require_account(key)
    return get_conn().execute(
        "SELECT id, created_at, last_seen_at, expires_at, left_at, user_agent FROM sessions"
        " WHERE account_id = ? ORDER BY last_seen_at DESC", (row["id"],)).fetchall()


def set_left(session_id: str, left: bool) -> None:
    """Record that this session left the dream (or re-entered it)."""
    get_conn().execute("UPDATE sessions SET left_at = ? WHERE id = ?",
                       (_iso(_now()) if left else None, session_id))


def live_passes() -> list[sqlite3.Row]:
    """Unexpired sessions of enabled accounts: (token_hash, account_id,
    expires_at). The keepsakes sync publishes these hashes so the edge can
    recognize a friend while the box is asleep (criterion 16)."""
    return get_conn().execute(
        "SELECT s.token_hash, s.account_id, s.expires_at FROM sessions s JOIN accounts a"
        " ON a.id = s.account_id WHERE a.disabled_at IS NULL AND s.expires_at > ?",
        (_iso(_now()),)).fetchall()


# ---- invites --------------------------------------------------------------


_words_cache: dict[str, list[str]] = {}


def _words(kind: str) -> list[str]:
    if kind not in _words_cache:
        path = WORDS_DIR / f"{kind}.txt"
        try:
            words = [w.strip() for w in path.read_text().splitlines() if w.strip()]
        except FileNotFoundError:
            raise AccountError(f"the invite wordlist {path} is missing from this install") from None
        if len(set(words)) < 256:
            raise RuntimeError(f"invite wordlist {path} is too small")
        _words_cache[kind] = words
    return _words_cache[kind]


def invite_space() -> int:
    return len(_words("adjectives")) * len(_words("nouns"))


def normalize_slug(slug: str) -> str:
    return "-".join((slug or "").strip().lower().replace("_", "-").split())


def create_invite(for_name: str, *, kind: str = "join", account: str | None = None,
                  days: int = INVITE_DAYS, note: str = "", created_by: str = "cli"
                  ) -> tuple[str, sqlite3.Row]:
    """Mint a single-use invite; returns (slug, row). The slug is shown once;
    only its hash is kept. `reset` invites name the account they reset.

    Guessing budget: 768 x 1280 phrases (about 983k) against a global cap of
    40 failed redemptions a day means, over a 14-day invite with three open at
    once, worst-case odds of 40 * 14 * 3 / 983k, about 0.17%."""
    if kind not in ("join", "reset"):
        raise AccountError("an invite is either 'join' or 'reset'")
    for_name = (for_name or "").strip()[:80]
    account_id = None
    if kind == "reset":
        target = _require_account(account or "")
        account_id = target["id"]
        for_name = for_name or target["display_name"]
    if not for_name:
        raise AccountError("say who the invite is for")
    if not 1 <= days <= 60:
        raise AccountError("an invite lasts 1 to 60 days")
    conn = get_conn()
    for _ in range(50):
        slug = f"{secrets.choice(_words('adjectives'))}-{secrets.choice(_words('nouns'))}"
        if not conn.execute("SELECT 1 FROM invites WHERE slug_hash = ?", (_sha(slug),)).fetchone():
            break
    else:  # pragma: no cover - 50 collisions in a 2M space
        raise AccountError("could not find an unused invite phrase; try again")
    invite_id = "i-" + secrets.token_hex(4)
    now = _now()
    conn.execute(
        "INSERT INTO invites(id, slug_hash, kind, for_name, account_id, created_at, created_by,"
        " expires_at, note) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (invite_id, _sha(slug), kind, for_name, account_id, _iso(now), created_by,
         _iso(now + timedelta(days=days)), note[:200]),
    )
    return slug, conn.execute("SELECT * FROM invites WHERE id = ?", (invite_id,)).fetchone()


def _open_invite(conn, slug: str) -> sqlite3.Row | None:
    row = conn.execute("SELECT * FROM invites WHERE slug_hash = ?",
                       (_sha(normalize_slug(slug)),)).fetchone()
    if row is None or row["redeemed_at"] or row["revoked_at"]:
        return None
    if _parse(row["expires_at"]) <= _now():
        return None
    return row


def peek_invite(slug: str) -> sqlite3.Row | None:
    """The open invite for a slug (to greet the invitee by name), or None for
    a used, expired, revoked or unknown slug: all four look the same."""
    return _open_invite(get_conn(), slug)


def redeem_join(slug: str, username: str, password: str) -> sqlite3.Row:
    """Create the account a join invite promises. Atomic and single-use: two
    concurrent redemptions of one slug cannot both succeed."""
    with _tx() as conn:
        inv = _open_invite(conn, slug)
        if inv is None or inv["kind"] != "join":
            raise AccountError(invite_refused())
        account_id = _insert_account(conn, username, password, inv["for_name"], "player",
                                     inv["id"])
        conn.execute("UPDATE invites SET redeemed_at = ?, account_id = ? WHERE id = ?",
                     (_iso(_now()), account_id, inv["id"]))
    return get_account(account_id)


def redeem_reset(slug: str, password: str) -> sqlite3.Row:
    """Set a new password from a reset invite. Every existing session ends."""
    problem = password_problem(password)
    if problem:
        raise AccountError(problem)
    with _tx() as conn:
        inv = _open_invite(conn, slug)
        if inv is None or inv["kind"] != "reset" or not inv["account_id"]:
            raise AccountError(invite_refused())
        conn.execute("UPDATE accounts SET password_hash = ? WHERE id = ?",
                     (_hash_password(password), inv["account_id"]))
        conn.execute("DELETE FROM sessions WHERE account_id = ?", (inv["account_id"],))
        conn.execute("UPDATE invites SET redeemed_at = ? WHERE id = ?", (_iso(_now()), inv["id"]))
    return get_account(inv["account_id"])


def invite_refused() -> str:
    return f"that invitation can't be used; ask {config.operator_name()} for a fresh one"


def list_invites(include_closed: bool = False) -> list[sqlite3.Row]:
    sql = "SELECT * FROM invites"
    if not include_closed:
        sql += " WHERE redeemed_at IS NULL AND revoked_at IS NULL AND expires_at > ?"
        return get_conn().execute(sql + " ORDER BY created_at", (_iso(_now()),)).fetchall()
    return get_conn().execute(sql + " ORDER BY created_at").fetchall()


def revoke_invite(key: str) -> sqlite3.Row:
    """Revoke by invite id (i-...) or by the slug itself."""
    conn = get_conn()
    row = conn.execute("SELECT * FROM invites WHERE id = ?", (key,)).fetchone()
    if row is None:
        row = conn.execute("SELECT * FROM invites WHERE slug_hash = ?",
                           (_sha(normalize_slug(key)),)).fetchone()
    if row is None:
        raise AccountError(f"no invite {key!r}")
    conn.execute("UPDATE invites SET revoked_at = COALESCE(revoked_at, ?) WHERE id = ?",
                 (_iso(_now()), row["id"]))
    return conn.execute("SELECT * FROM invites WHERE id = ?", (row["id"],)).fetchone()


# ---- throttles ------------------------------------------------------------


def _window(conn, key: str, window_s: int) -> tuple[str, int]:
    row = conn.execute("SELECT window_start, count FROM throttle WHERE key = ?", (key,)).fetchone()
    now = _now()
    if row is None or (now - _parse(row["window_start"])).total_seconds() >= window_s:
        return _iso(now), 0
    return row["window_start"], int(row["count"])


def throttled(key: str, budget: tuple[int, int]) -> bool:
    """True when `key` has used up its failure budget for the current window."""
    limit, window_s = budget
    _, count = _window(get_conn(), key, window_s)
    return count >= limit


def record_failure(key: str, budget: tuple[int, int]) -> None:
    _, window_s = budget
    conn = get_conn()
    start, count = _window(conn, key, window_s)
    conn.execute(
        "INSERT INTO throttle(key, window_start, count) VALUES (?, ?, ?)"
        " ON CONFLICT(key) DO UPDATE SET window_start = excluded.window_start,"
        " count = excluded.count",
        (key, start, count + 1),
    )


def clear_failures(key: str) -> None:
    get_conn().execute("DELETE FROM throttle WHERE key = ?", (key,))
