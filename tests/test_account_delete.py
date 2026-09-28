"""`bin/game account delete` (2026-09-28): the end of a person's lifecycle
(docs/DATA-LIFECYCLE.md). Early prod sessions test the admin systems too, and
`disable` left an account and its records behind. Delete removes the account,
its sessions, invites and throttle counters, its dreamers in the live world
and what they typed; the shared event history stays."""

from __future__ import annotations

import pytest

from daydream import accounts, accounts_cli, db, events, inputs, toons

pytestmark = pytest.mark.tier_short

PW = "correct horse battery"


@pytest.fixture(autouse=True)
def fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("DAYDREAM_DATA_DIR", str(tmp_path))
    db.close_db()
    accounts.init()
    db.init_live()
    yield
    db.close_db()


def _a_friend_who_played():
    slug, inv = accounts.create_invite("Robin Ash")
    row = accounts.redeem_join(slug, "robin", PW)
    token, _ = accounts.create_session(row["id"], "a browser")
    t = toons.create_toon_in_slot(2, "Robin", "a small wren", "s-robin", owner_account=row["id"])
    inputs.record(t.id, "text", text="i whisper my secret to the jars")
    events.append("toon", t.id, "narrate", {"text": "Robin waves."}, room_id=t.current_room_id)
    accounts.record_failure("login-user:robin", accounts.LOGIN_PER_USERNAME)
    return row, inv, token, t


def test_without_yes_nothing_is_deleted(capsys):
    row, inv, token, t = _a_friend_who_played()
    assert accounts_cli.main(["account", "delete", "robin"]) == 2
    accounts.init()  # the CLI closes its connection on the way out
    out = capsys.readouterr()
    assert "Robin (" in out.out and "--yes" in out.err
    assert accounts.get_account("robin") is not None
    assert toons.get_toon(t.id) is not None
    assert accounts.resolve(token) is not None


def test_delete_removes_the_person_and_keeps_the_shared_history(capsys):
    row, inv, token, t = _a_friend_who_played()
    other = accounts.create_account("wren", PW)
    before = [e.seq for e in events.fetch_since(0)]

    assert [i.toon_id for i in inputs.fetch()].count(t.id) == 1
    assert accounts_cli.main(["account", "delete", "robin", "--yes"]) == 0
    accounts.init()
    assert "deleted account robin" in capsys.readouterr().out

    assert accounts.get_account("robin") is None
    assert accounts.resolve(token) is None
    conn = accounts.get_conn()
    assert conn.execute("SELECT count(*) FROM sessions WHERE account_id = ?",
                        (row["id"],)).fetchone()[0] == 0
    assert conn.execute("SELECT count(*) FROM invites WHERE id = ?", (inv["id"],)).fetchone()[0] == 0
    assert not accounts.throttled("login-user:robin", (1, 3600))
    assert toons.get_toon(t.id) is None
    assert [i for i in inputs.fetch() if i.toon_id == t.id] == []
    assert [e.seq for e in events.fetch_since(0)][:len(before)] == before  # history stays
    assert accounts.get_account("wren")["id"] == other["id"]  # nobody else touched


def test_an_unknown_account_is_an_error(capsys):
    assert accounts_cli.main(["account", "delete", "nobody", "--yes"]) == 1
    assert "no account 'nobody'" in capsys.readouterr().err
