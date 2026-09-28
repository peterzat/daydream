"""Accounts, sessions, invites and throttles (SPEC 2026-09-27 criteria 2-4):
the daydream/accounts.py surface and the `bin/game account|invite` CLI."""

import json
import subprocess
import sys
from datetime import timedelta
from pathlib import Path

import pytest

from daydream import accounts, config

pytestmark = pytest.mark.tier_short

ROOT = Path(__file__).resolve().parent.parent
PW = "correct horse battery"


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    # A small deterministic wordlist so invite tests never depend on the
    # shipped lists (which have their own test below).
    monkeypatch.setattr(accounts, "_words_cache", {
        "adjectives": [f"adj{i:03d}" for i in range(300)],
        "nouns": [f"noun{i:03d}" for i in range(300)],
    })
    accounts.init()
    yield


_REAL_NOW = accounts._now


def _shift(monkeypatch, **delta):
    """Pin the accounts clock to real-now + delta (deltas are absolute, from
    the moment of the call's first use in a test, not cumulative)."""
    base = _REAL_NOW()
    monkeypatch.setattr(accounts, "_now", lambda: base + timedelta(**delta))


# ---- accounts + passwords ---------------------------------------------------


def test_accounts_live_in_their_own_db_beside_the_worlds(tmp_path):
    assert config.accounts_db_path() == tmp_path / "accounts-dev.db"
    assert config.accounts_db_path().exists()


def test_create_and_authenticate():
    row = accounts.create_account("Wren", PW, display_name="Wren Ashby")
    assert row["username"] == "wren" and row["role"] == "player"
    assert row["display_name"] == "Wren Ashby"
    assert row["password_hash"].startswith("$argon2id$")
    assert PW not in row["password_hash"]
    assert accounts.authenticate("WREN", PW)["id"] == row["id"]
    assert accounts.authenticate("wren", "not the password") is None


def test_unknown_username_and_wrong_password_look_the_same():
    accounts.create_account("wren", PW)
    assert accounts.authenticate("nobody", PW) is None
    assert accounts.authenticate("wren", "wrong password!") is None
    assert accounts.authenticate("", PW) is None


@pytest.mark.parametrize("username", ["ab", "x" * 25, "has space", "Émile", "-dash", "bad!"])
def test_username_rules(username):
    with pytest.raises(accounts.AccountError):
        accounts.create_account(username, PW)


def test_short_password_refused():
    with pytest.raises(accounts.AccountError, match="10"):
        accounts.create_account("wren", "short")


def test_duplicate_username_refused_case_insensitively():
    accounts.create_account("wren", PW)
    with pytest.raises(accounts.AccountError, match="taken"):
        accounts.create_account("WREN", PW)


def test_disabled_account_cannot_log_in_and_loses_sessions():
    row = accounts.create_account("wren", PW)
    token, _ = accounts.create_session(row["id"])
    assert accounts.resolve(token) is not None
    accounts.set_disabled("wren", True)
    assert accounts.resolve(token) is None
    assert accounts.authenticate("wren", PW) is None
    accounts.set_disabled("wren", False)
    assert accounts.authenticate("wren", PW) is not None


def test_roles_are_player_or_admin():
    accounts.create_account("wren", PW)
    assert accounts.set_role("wren", "admin")["role"] == "admin"
    with pytest.raises(accounts.AccountError):
        accounts.set_role("wren", "root")


def test_change_password_ends_other_sessions():
    row = accounts.create_account("wren", PW)
    keep, keep_id = accounts.create_session(row["id"])
    other, _ = accounts.create_session(row["id"])
    with pytest.raises(accounts.AccountError):
        accounts.change_password(row["id"], "not it at all", "a brand new password")
    accounts.change_password(row["id"], PW, "a brand new password", keep_session_id=keep_id)
    assert accounts.resolve(keep) is not None
    assert accounts.resolve(other) is None
    assert accounts.authenticate("wren", "a brand new password") is not None


def test_a_password_change_never_overwrites_one_made_meanwhile():
    """codereview WARN 2026-09-28b: the change is split around an await; a
    reset redeemed in that window must not be overwritten by the change."""
    row = accounts.create_account("wren", PW)
    _, sid = accounts.create_session(row["id"])
    new_hash, verified = accounts.prepare_password_change(row["id"], PW, "a brand new password")
    # A reset lands between the halves: a new password (and, for a real
    # reset, every session ended; the second case below).
    accounts.get_conn().execute("UPDATE accounts SET password_hash = ? WHERE id = ?",
                                (accounts._hash_password("the reset password"), row["id"]))
    with pytest.raises(accounts.AccountError, match="meanwhile"):
        accounts.commit_password_change(row["id"], new_hash, verified, keep_session_id=sid)
    assert accounts.authenticate("wren", "the reset password") is not None
    new_hash, verified = accounts.prepare_password_change(row["id"], "the reset password",
                                                          "a brand new password")
    accounts.revoke_sessions("wren")
    with pytest.raises(accounts.AccountError, match="meanwhile"):
        accounts.commit_password_change(row["id"], new_hash, verified, keep_session_id=sid)
    assert accounts.authenticate("wren", "the reset password") is not None


# ---- sessions -----------------------------------------------------------------


def test_session_tokens_are_stored_only_as_hashes():
    row = accounts.create_account("wren", PW)
    token, sid = accounts.create_session(row["id"], "Firefox")
    stored = accounts.get_conn().execute("SELECT * FROM sessions WHERE id = ?", (sid,)).fetchone()
    assert token not in dict(stored).values()
    assert stored["token_hash"] == accounts._sha(token)
    p = accounts.resolve(token)
    assert (p.username, p.session_id, p.role, p.left) == ("wren", sid, "player", False)


def test_session_expires_after_thirty_idle_days(monkeypatch):
    row = accounts.create_account("wren", PW)
    token, _ = accounts.create_session(row["id"])
    _shift(monkeypatch, days=29)
    assert accounts.resolve(token) is not None  # use slides the expiry
    _shift(monkeypatch, days=29 + 29)
    assert accounts.resolve(token) is not None
    _shift(monkeypatch, days=29 + 29 + 31)
    assert accounts.resolve(token) is None


def test_logout_and_revoke():
    row = accounts.create_account("wren", PW)
    a, _ = accounts.create_session(row["id"])
    b, _ = accounts.create_session(row["id"])
    accounts.end_session(a)
    assert accounts.resolve(a) is None and accounts.resolve(b) is not None
    assert accounts.revoke_sessions("wren") == 1
    assert accounts.resolve(b) is None


def test_resolve_ignores_garbage():
    assert accounts.resolve(None) is None
    assert accounts.resolve("") is None
    assert accounts.resolve("x" * 500) is None
    assert accounts.resolve("not-a-token") is None


def test_left_flag_round_trips():
    row = accounts.create_account("wren", PW)
    token, sid = accounts.create_session(row["id"])
    accounts.set_left(sid, True)
    assert accounts.resolve(token).left is True
    accounts.set_left(sid, False)
    assert accounts.resolve(token).left is False


def test_live_passes_skip_disabled_and_expired(monkeypatch):
    a = accounts.create_account("wren", PW)
    b = accounts.create_account("juniper", PW)
    ta, _ = accounts.create_session(a["id"])
    accounts.create_session(b["id"])
    accounts.set_disabled("juniper", True)
    passes = accounts.live_passes()
    assert [p["token_hash"] for p in passes] == [accounts._sha(ta)]
    _shift(monkeypatch, days=31)
    assert accounts.live_passes() == []


def test_live_passes_honor_the_absolute_session_cap(monkeypatch):
    """codereview NOTE 2026-09-28: a session kept alive by use past 180 days is
    refused by resolve(); the edge's pass list must drop it too."""
    a = accounts.create_account("wren", PW)
    token, _ = accounts.create_session(a["id"])
    # Keep it in use: its sliding expiry follows, its created_at does not.
    accounts.get_conn().execute(
        "UPDATE sessions SET expires_at = ?",
        (accounts._iso(accounts._now() + timedelta(days=accounts.SESSION_MAX_DAYS + 20)),))
    _shift(monkeypatch, days=accounts.SESSION_MAX_DAYS + 1)
    assert accounts.resolve(token) is None
    assert accounts.live_passes() == []


def test_a_pass_expires_at_the_absolute_cap_when_that_comes_first():
    """codereview WARN 2026-09-28b: the edge trusts the published expiry, so a
    session crossing 180 days while the box sleeps kept its pass until the
    30-day sliding expiry."""
    a = accounts.create_account("wren", PW)
    accounts.create_session(a["id"])
    now = accounts._now()
    accounts.get_conn().execute("UPDATE sessions SET created_at = ?, expires_at = ?",
                                (accounts._iso(now - timedelta(days=170)),
                                 accounts._iso(now + timedelta(days=accounts.SESSION_DAYS))))
    [p] = accounts.live_passes()
    assert p["expires_at"] == accounts._iso(now + timedelta(days=10))
    accounts.get_conn().execute("UPDATE sessions SET created_at = ?",
                                (accounts._iso(now - timedelta(days=1)),))
    assert accounts.live_passes()[0]["expires_at"] == accounts._iso(
        now + timedelta(days=accounts.SESSION_DAYS))


def test_login_takes_a_username_not_an_account_id():
    """codereview NOTE 2026-09-28: an account id was a second name to guess."""
    a = accounts.create_account("wren", PW)
    assert accounts.authenticate("wren", PW)["id"] == a["id"]
    assert accounts.authenticate(a["id"], PW) is None


def test_mint_session_creates_the_account_once():
    t1, p1 = accounts.mint_session("agent-one")
    t2, p2 = accounts.mint_session("agent-one")
    assert p1.account_id == p2.account_id and t1 != t2
    _, admin = accounts.mint_session("keeper", role="admin")
    assert admin.is_admin


# ---- invites ------------------------------------------------------------------


def test_join_invite_creates_an_account_named_for_the_invitee():
    slug, inv = accounts.create_invite("Robin Ash")
    assert slug.count("-") == 1
    stored = dict(inv)
    assert slug not in stored.values() and stored["slug_hash"] == accounts._sha(slug)
    assert accounts.peek_invite(slug)["for_name"] == "Robin Ash"
    row = accounts.redeem_join(slug, "robin", PW)
    assert row["display_name"] == "Robin Ash" and row["role"] == "player"
    assert row["invite_id"] == inv["id"]
    assert accounts.authenticate("robin", PW) is not None


def test_a_slug_works_once():
    slug, _ = accounts.create_invite("Robin Ash")
    accounts.redeem_join(slug, "robin", PW)
    with pytest.raises(accounts.AccountError) as e:
        accounts.redeem_join(slug, "robin2", PW)
    assert str(e.value) == accounts.invite_refused()
    assert accounts.peek_invite(slug) is None


def test_used_expired_revoked_and_unknown_slugs_look_the_same(monkeypatch):
    used, _ = accounts.create_invite("A")
    accounts.redeem_join(used, "aaa", PW)
    revoked, inv = accounts.create_invite("B")
    accounts.revoke_invite(inv["id"])
    expiring, _ = accounts.create_invite("C", days=1)
    _shift(monkeypatch, days=2)
    messages = set()
    for slug in (used, revoked, expiring, "never-issued"):
        assert accounts.peek_invite(slug) is None
        with pytest.raises(accounts.AccountError) as e:
            accounts.redeem_join(slug, "zzz", PW)
        messages.add(str(e.value))
    assert len(messages) == 1


def test_a_bad_username_does_not_burn_the_invite():
    slug, _ = accounts.create_invite("Robin Ash")
    with pytest.raises(accounts.AccountError, match="username"):
        accounts.redeem_join(slug, "no", PW)
    assert accounts.peek_invite(slug) is not None
    accounts.redeem_join(slug, "robin", PW)


def test_slug_normalization_is_forgiving():
    slug, _ = accounts.create_invite("Robin Ash")
    assert accounts.peek_invite("  " + slug.upper() + " ") is not None


def test_reset_invite_sets_a_new_password_and_ends_sessions():
    row = accounts.create_account("wren", PW)
    token, _ = accounts.create_session(row["id"])
    slug, inv = accounts.create_invite("", kind="reset", account="wren")
    assert inv["for_name"] == "wren" and inv["account_id"] == row["id"]
    with pytest.raises(accounts.AccountError):  # a reset slug cannot make an account
        accounts.redeem_join(slug, "sneaky", PW)
    accounts.redeem_reset(slug, "an entirely new password")
    assert accounts.resolve(token) is None
    assert accounts.authenticate("wren", "an entirely new password") is not None
    with pytest.raises(accounts.AccountError):
        accounts.redeem_reset(slug, "yet another password")


def test_invite_list_and_revoke_by_slug():
    slug, inv = accounts.create_invite("Robin Ash")
    assert [r["id"] for r in accounts.list_invites()] == [inv["id"]]
    accounts.revoke_invite(slug)
    assert accounts.list_invites() == []
    assert len(accounts.list_invites(include_closed=True)) == 1


def test_concurrent_redemption_of_one_slug_succeeds_once(tmp_path):
    """Two separate processes race to redeem the same slug against the same
    DB file; the IMMEDIATE transaction lets exactly one win."""
    slug, _ = accounts.create_invite("Robin Ash")
    accounts.close()
    script = (
        f"import os, sys; sys.path.insert(0, {str(ROOT)!r})\n"
        "from daydream import accounts\n"
        "accounts.init()\n"
        "try:\n"
        f"    accounts.redeem_join({slug!r}, sys.argv[1], {PW!r}); print('ok')\n"
        "except accounts.AccountError as e: print('refused')\n"
    )
    env = {"DAYDREAM_DATA_DIR": str(tmp_path), "DAYDREAM_PASSWORD_HASH_PROFILE": "test",
           "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)}
    procs = [subprocess.Popen([sys.executable, "-c", script, name], env=env,
                              stdout=subprocess.PIPE, text=True)
             for name in ("racer-one", "racer-two", "racer-three")]
    results = sorted(p.communicate(timeout=60)[0].strip() for p in procs)
    assert results == ["ok", "refused", "refused"]


# ---- throttles ------------------------------------------------------------------


def test_throttle_counts_failures_within_a_window(monkeypatch):
    budget = (3, 60)
    for _ in range(3):
        assert not accounts.throttled("k", budget)
        accounts.record_failure("k", budget)
    assert accounts.throttled("k", budget)
    _shift(monkeypatch, seconds=61)
    assert not accounts.throttled("k", budget)
    accounts.record_failure("k", budget)
    accounts.clear_failures("k")
    assert not accounts.throttled("k", budget)


# ---- the shipped wordlists --------------------------------------------------------


def test_the_shipped_wordlists_give_a_big_enough_space(monkeypatch):
    monkeypatch.setattr(accounts, "_words_cache", {})
    adj, nouns = accounts._words("adjectives"), accounts._words("nouns")
    assert len(adj) == len(set(adj)) >= 768
    assert len(nouns) == len(set(nouns)) >= 1280
    assert not set(adj) & set(nouns)
    for w in adj + nouns:
        assert w.isascii() and w.isalpha() and w.islower() and 3 <= len(w) <= 8, w
    # The guessing budget (accounts.create_invite): at the global daily cap,
    # three open 14-day invites stay under 0.2% worst-case odds.
    daily = accounts.REDEEM_GLOBAL_DAY[0]
    assert daily * accounts.INVITE_DAYS * 3 / accounts.invite_space() < 0.002


# ---- the CLI ------------------------------------------------------------------------


def test_cli_account_lifecycle(capsys):
    from daydream import accounts_cli

    assert accounts_cli.main(["account", "create", "peter", "--admin", "--generate"]) == 0
    out = capsys.readouterr().out
    assert "created peter (admin" in out and "password: " in out
    assert accounts_cli.main(["account", "list"]) == 0
    assert "peter" in capsys.readouterr().out
    assert accounts_cli.main(["account", "role", "peter", "player"]) == 0
    assert accounts_cli.main(["account", "disable", "peter"]) == 0
    assert "disabled" in capsys.readouterr().out
    assert accounts_cli.main(["account", "role", "nobody", "admin"]) == 1
    assert "no account" in capsys.readouterr().err


def test_cli_invite_json_carries_link_and_message(capsys, monkeypatch):
    from daydream import accounts_cli

    monkeypatch.setenv("DAYDREAM_PUBLIC_ORIGIN", "https://www.eidolon.com")
    monkeypatch.setenv("DAYDREAM_PUBLIC_BASE", "/daydream/")
    assert accounts_cli.main(["invite", "create", "--for", "Robin Ash", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert data["for"] == "Robin Ash" and data["kind"] == "join"
    assert data["link"] == f"https://www.eidolon.com/daydream/invite/{data['slug']}"
    assert data["link"] in data["message"] and data["message"].startswith("Hi Robin!")
    accounts.init()
    assert accounts.peek_invite(data["slug"]) is not None


def test_cli_password_stdin(monkeypatch, capsys):
    import io

    from daydream import accounts_cli

    monkeypatch.setattr("sys.stdin", io.StringIO(PW + "\n"))
    assert accounts_cli.main(["account", "create", "wren", "--password-stdin"]) == 0
    accounts.init()
    assert accounts.authenticate("wren", PW) is not None


def test_a_session_ends_after_180_days_however_often_it_is_used(monkeypatch):
    row = accounts.create_account("wren", PW)
    token, _ = accounts.create_session(row["id"])
    for day in range(29, 179, 29):          # used every 29 days
        _shift(monkeypatch, days=day)
        assert accounts.resolve(token) is not None
    _shift(monkeypatch, days=181)
    assert accounts.resolve(token) is None
