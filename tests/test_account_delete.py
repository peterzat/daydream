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


def test_delete_removes_what_the_world_kept_under_the_dreamers_id(capsys):
    """Codereview WARN 2026-09-28e: the talk log (the player's own typed
    sentences), the Book, relationships, greetings, bystander notes, private
    finds and the dreamer-create counter outlived the delete."""
    from daydream import objects, story, worldstate

    row, inv, token, t = _a_friend_who_played()
    other = toons.create_toon_in_slot(3, "Wren", "a heron", "s-wren")
    w = t.world_id
    story.remember_exchange(w, "t-rook", t.id, "my real name is Robin Ash", "a lovely name")
    story.remember_exchange(w, "t-rook", other.id, "hello", "hello, heron")
    story.pset(w, t.id, "collected", ["m-dawn"])
    story.pset(w, other.id, "collected", ["m-dusk"])
    story.adjust_rel(w, "t-rook", t.id, 2)
    for key in (f"relday:t-rook:{t.id}", f"greeted:{t.id}", f"bystander:t-rook:{t.id}"):
        worldstate.set(w, key, "2026-09-28")
    find = objects.spawn(w, "thing", "stray minute", t.current_room_id,
                         properties={"private_to": t.id})
    theirs = objects.spawn(w, "thing", "stray minute", t.current_room_id,
                           properties={"private_to": other.id})
    accounts.record_failure("dreamer-create:" + row["id"], (6, 86400))

    assert accounts_cli.main(["account", "delete", "robin", "--yes"]) == 0
    accounts.init()
    db.init_live()
    assert not [k for k in worldstate.keys(w) if t.id in k]
    assert story.recent_exchanges(w, "t-rook", other.id)  # nobody else's
    assert story.pget(w, other.id, "collected") == ["m-dusk"]
    assert objects.get(find.id) is None and objects.get(theirs.id) is not None
    assert accounts.get_conn().execute(
        "SELECT count(*) FROM throttle WHERE key = ?", ("dreamer-create:" + row["id"],)
    ).fetchone()[0] == 0
    assert "story record(s)" in capsys.readouterr().out


def test_an_unknown_account_is_an_error(capsys):
    assert accounts_cli.main(["account", "delete", "nobody", "--yes"]) == 1
    assert "no account 'nobody'" in capsys.readouterr().err
