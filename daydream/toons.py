"""Toon read + write helpers: a thin typed view over the unified `objects`
table (`daydream.objects`). A toon is an object with `kind='toon'`. Its
auth/slot fields (slot, controller_session, is_human_controlled, kicked_at)
are promoted columns; seed / appearance_seed / mood / presence_text live in
the object's `properties` bag; its current room is the object's `location_id`;
its inventory is the things located on it."""

import uuid
from dataclasses import dataclass

from daydream import db, objects

# A player's name reaches other players' NPC prompts (gossip facts, scope
# lists), so it is short and one line: checked at create (api/slots.py) and
# truncated wherever it is baked into stored text (knowledge.py).
MAX_NAME_CHARS = 24


@dataclass(frozen=True)
class Toon:
    id: str
    world_id: str
    slot: int
    name: str
    seed: str
    appearance_seed: str
    current_room_id: str | None
    is_human_controlled: bool
    controller_session: str | None
    inventory: list
    mood: str
    kicked_at: str | None
    # One-line greeting fired by the WS broadcast loop when the controlled
    # toon walks into this toon's room. NULL / empty / whitespace = silent.
    presence_text: str | None = None
    # The account this human toon belongs to (migration 018); None = unowned.
    owner_account: str | None = None

    @classmethod
    def from_object(cls, obj: "objects.Object", inventory: list | None = None) -> "Toon":
        p = obj.properties
        # A raw set_property (e.g. an authored rule) can store any JSON value here;
        # a non-string must read as "no portrait", not crash every picker and
        # snapshot that calls .strip() on it (security NOTE 2026-09-26).
        appearance = p.get("appearance_seed", "")
        return cls(
            id=obj.id,
            world_id=obj.world_id,
            slot=obj.slot,
            name=obj.name,
            seed=p.get("seed", ""),
            appearance_seed=appearance if isinstance(appearance, str) else "",
            current_room_id=obj.location_id,
            is_human_controlled=obj.is_human_controlled,
            controller_session=obj.controller_session,
            inventory=inventory if inventory is not None else [],
            mood=p.get("mood", "curious"),
            kicked_at=obj.kicked_at,
            presence_text=p.get("presence_text"),
            owner_account=obj.owner_account,
        )


def _toon(obj: "objects.Object | None") -> Toon | None:
    """Build a Toon (with its inventory filled) from an object, or None."""
    if obj is None or obj.kind != "toon":
        return None
    return Toon.from_object(obj, inventory=objects.content_ids(obj.id, "thing"))


def _query(where: str, params: tuple) -> list[Toon]:
    rows = db.get_conn().execute(
        f"SELECT * FROM objects WHERE kind = 'toon' AND {where}", params
    ).fetchall()
    return [_toon(objects.Object.from_row(r)) for r in rows]  # type: ignore[misc]


def get_toon(toon_id: str) -> Toon | None:
    return _toon(objects.get(toon_id))


def get_toons_in_room(room_id: str) -> list[Toon]:
    return _query(
        "location_id = ? AND kicked_at IS NULL ORDER BY slot", (room_id,)
    )


def find_toon_in_room_by_name(room_id: str, name: str) -> Toon | None:
    """Case-insensitive exact-name match within a room. Kicked toons are
    excluded (mirrors `get_toons_in_room`)."""
    needle = name.strip().lower()
    if not needle:
        return None
    for t in get_toons_in_room(room_id):
        if t.name.lower() == needle:
            return t
    return None


def get_players_awake() -> list[Toon]:
    """The live world's players who have not left the dream (controlled
    now; a dozing page still counts, the caller decides), in slot order."""
    return _query(
        "world_id = ? AND is_human_controlled = 1 AND kicked_at IS NULL ORDER BY slot",
        (live_world_id(),))


def announce_wake(t: "Toon") -> None:
    """A dreamer comes back into the dream: the room sees them arrive (a
    waking player appeared in nobody's margin until the next refresh; beta
    rehearsal 2026-09-28), and the margins follow at once."""
    if not t.current_room_id:
        return
    from daydream import events

    events.append("system", None, "narrate",
                  {"text": f"{t.name} drifts back into the dream.", "except": t.id},
                  room_id=t.current_room_id)
    events.append("system", None, "presence_changed", {"toon_id": t.id},
                  room_id=t.current_room_id)


def get_npcs() -> list[Toon]:
    """All NPCs (non-human-controlled, not kicked), ordered by slot. The drift
    loop's source of truth for who can speak."""
    return _query(
        "is_human_controlled = 0 AND kicked_at IS NULL ORDER BY slot", ()
    )


def set_current_room(toon_id: str, room_id: str) -> None:
    """Move a toon into `room_id` (updates the object's location_id)."""
    objects.move(toon_id, room_id)


def set_mood(toon_id: str, mood: str) -> None:
    """Update a toon's mood (a key in its properties bag). An unknown toon_id
    is a no-op (set_property returns False)."""
    objects.set_property(toon_id, "mood", mood)


# ---- slot-picker helpers ----------------------------------------------
#
# Human-controllable toons live in slots 1-99; hand-authored NPCs in slots
# 100+ are excluded from every slot query so they are never claimed or
# kicked. Since accounts (SPEC 2026-09-27 criterion 5) the slot number is
# internal bookkeeping: a toon belongs to an account (`owner_account`), and a
# player sees "your dreamer", not a row of slots.

HUMAN_SLOT_RANGE = range(1, 100)  # slots 1..99 inclusive
# The v1 world loader stamps every world it builds with this id (one world
# per DB file), so it doubles as the safe fallback when the worlds table is
# empty or unreadable. It is loader-canonical, not a leftover of the old
# bunny world.
DEFAULT_HUMAN_WORLD_ID = "w-bunny"


def live_world_id() -> str:
    """The id of THE world in the live DB (one world per DB file is the
    invariant; `world swap` changes which file is live). Falls back to the
    legacy default when the worlds table is empty or unreadable, so nothing
    that worked before a swap can break for want of a row."""
    try:
        row = db.get_conn().execute("SELECT id FROM worlds LIMIT 1").fetchone()
    except Exception:
        return DEFAULT_HUMAN_WORLD_ID
    return row["id"] if row else DEFAULT_HUMAN_WORLD_ID


def get_toon_by_session(session_id: str) -> Toon | None:
    """The toon currently controlled by `session_id` (controller match AND not
    kicked AND human-controlled), or None. Empty session returns None."""
    if not session_id:
        return None
    rows = _query(
        "controller_session = ? AND kicked_at IS NULL AND is_human_controlled = 1 "
        "LIMIT 1",
        (session_id,),
    )
    return rows[0] if rows else None


def toon_card(t: Toon, session_id: str | None = None) -> dict:
    """The JSON shape the slot and dreamer endpoints share."""
    return {
        "id": t.id,
        "slot": t.slot,
        "name": t.name,
        "appearance_seed": t.appearance_seed,
        "current_room_id": t.current_room_id,
        "is_human_controlled": t.is_human_controlled,
        "kicked_at": t.kicked_at,
        "mood": t.mood,
        "owner_account": t.owner_account,
        "claimed_by_me": (
            bool(session_id)
            and t.controller_session == session_id
            and t.kicked_at is None
            and t.is_human_controlled
        ),
    }


def get_human_slots(session_id: str | None = None) -> list[dict]:
    """Every populated human slot (1..99) of the live world, in slot order:
    `{"slot": N, "toon": <card>}`. The admin's view of who exists; a player
    sees only their own toons (`owned_toons`). Slot 100+ NPCs are excluded."""
    lo, hi = HUMAN_SLOT_RANGE.start, HUMAN_SLOT_RANGE.stop - 1
    found = _query(
        "slot BETWEEN ? AND ? AND world_id = ? ORDER BY slot, id",
        (lo, hi, live_world_id()),
    )
    seen: set[int] = set()
    out: list[dict] = []
    for t in found:
        if t.slot in seen:
            continue
        seen.add(t.slot)
        out.append({"slot": t.slot, "toon": toon_card(t, session_id)})
    return out


def playing() -> list[Toon]:
    """Human toons someone is playing right now (controlled, not resting) in
    the live world."""
    lo, hi = HUMAN_SLOT_RANGE.start, HUMAN_SLOT_RANGE.stop - 1
    return _query("world_id = ? AND is_human_controlled = 1 AND kicked_at IS NULL "
                  "AND slot BETWEEN ? AND ? ORDER BY slot", (live_world_id(), lo, hi))


def owned_toons(account_id: str) -> list[Toon]:
    """The live world's toons that belong to `account_id`, in slot order."""
    return _query("world_id = ? AND owner_account = ? ORDER BY slot, id",
                  (live_world_id(), account_id))


def next_free_slot() -> int | None:
    """The lowest unoccupied human slot in the live world, or None if full."""
    taken = {r["slot"] for r in db.get_conn().execute(
        "SELECT slot FROM objects WHERE kind = 'toon' AND world_id = ? AND slot IS NOT NULL",
        (live_world_id(),))}
    return next((n for n in HUMAN_SLOT_RANGE if n not in taken), None)


def adopt(toon_id: str, account_id: str) -> None:
    """Give an unowned toon (a seeded or pre-accounts human toon) to an
    account. Never takes a toon from its owner."""
    db.get_conn().execute(
        "UPDATE objects SET owner_account = ? WHERE id = ? AND kind = 'toon' "
        "AND owner_account IS NULL", (account_id, toon_id))


def _slot_occupied(slot: int) -> Toon | None:
    """The toon (if any) currently in `slot` for the default world."""
    rows = _query(
        "slot = ? AND world_id = ? ORDER BY id LIMIT 1",
        (slot, live_world_id()),
    )
    return rows[0] if rows else None


def get_toon_in_slot(slot: int) -> Toon | None:
    """Public read of the toon currently in `slot` (default world), or None
    if empty. The slot API's ownership guard reads controller_session /
    liveness off this before deciding whether a kick/delete is allowed."""
    return _slot_occupied(slot)


def create_toon_in_slot(
    slot: int, name: str, appearance_seed: str, session_id: str,
    owner_account: str | None = None,
) -> Toon | None:
    """Create a new human-controlled toon in `slot` claimed by `session_id`
    and owned by `owner_account`. Returns the new Toon, or None if the slot is
    already occupied. Spawns in the world's starting room. Caller range-checks
    `slot` first."""
    if _slot_occupied(slot) is not None:
        return None
    from daydream import rooms

    world_id = live_world_id()
    spawn = rooms.starting_room_id(world_id)
    if spawn is None:
        # A world with no rooms cannot host a toon; fail loudly rather
        # than spawn into a phantom room id (the old "r-meadow" fallback
        # pointed at a room no loaded world even has).
        raise ValueError(f"world {world_id!r} has no starting room")
    toon_id = f"t-slot{slot}-{uuid.uuid4().hex[:8]}"
    db.get_conn().execute(
        "INSERT INTO objects (id, world_id, kind, name, aliases_json, "
        "location_id, prototype_id, properties_json, slot, controller_session, "
        "is_human_controlled, kicked_at, owner_account) "
        "VALUES (?, ?, 'toon', ?, '[]', ?, ?, ?, ?, ?, 1, NULL, ?)",
        (
            toon_id,
            world_id,
            name,
            spawn,
            objects.PROTO_NPC,
            _toon_properties(appearance_seed=appearance_seed),
            slot,
            session_id,
            owner_account,
        ),
    )
    _release_others(session_id, toon_id)
    return get_toon(toon_id)


def _release_others(session_id: str, keep_id: str) -> None:
    """A session plays one toon at a time: taking one lets go of any other it
    held (a release, not a rest: they keep their room and things, and any
    session of their account may claim them again)."""
    db.get_conn().execute(
        "UPDATE objects SET controller_session = NULL WHERE kind = 'toon' "
        "AND controller_session = ? AND id != ?", (session_id, keep_id))


def _toon_properties(*, appearance_seed: str, mood: str = "curious") -> str:
    import json

    return json.dumps(
        {"seed": "", "appearance_seed": appearance_seed, "mood": mood,
         "presence_text": None}
    )


def claim_slot(
    slot: int, session_id: str, *, can_take_over=None
) -> tuple[Toon | None, str | None]:
    """Adopt a kicked-NPC toon as the human player. Returns `(toon, None)` on
    success, `(None, reason)` on failure where reason is 'empty' or
    'controlled'. A resting toon wakes in the world's starting room; one that
    never rested stays where it is.

    `can_take_over(controller_session) -> bool` (optional): when the slot is
    controlled by ANOTHER session, adopt it anyway if this returns True -- used
    to reclaim a toon whose controlling session has no live WS connection (an
    abandoned claim). Default refuses any controlled toon."""
    t = _slot_occupied(slot)
    if t is None:
        return (None, "empty")
    controller = t.controller_session
    if t.is_human_controlled and t.kicked_at is None and controller:
        # (No controller: released by a session that took another toon.)
        takeover = bool(can_take_over and can_take_over(controller))
        if not takeover:
            return (None, "controlled")
    from daydream import rooms

    # Waking from rest starts at the world's start room; re-claiming a toon
    # that never rested (the same player reconnecting, or taking back an
    # abandoned claim) keeps it where it stands (playtest 2026-09-26: a
    # reconnect moved a player out of the cellar).
    resting = t.kicked_at is not None or not t.is_human_controlled
    spawn = ((rooms.starting_room_id(t.world_id) or t.current_room_id) if resting
             else t.current_room_id)
    db.get_conn().execute(
        "UPDATE objects SET controller_session = ?, is_human_controlled = 1, "
        "kicked_at = NULL, location_id = ? WHERE id = ?",
        (session_id, spawn, t.id),
    )
    _release_others(session_id, t.id)
    return (get_toon(t.id), None)


# ---- comings and goings ------------------------------------------------------
#
# A player's move is presence, not story (first prod evening, 2026-09-28: the
# old bare "you go down." lines piled up in every room a player had left and
# replayed there on return). The mover reads one line in the room they reach;
# whoever is in the room left, or the room reached, reads a line naming the
# other place, live. Arrival replays skip both kinds (ws._state_snapshot).

PRESENCE_KINDS = ("move", "arrive")
_COMPASS = frozenset({"north", "south", "east", "west",
                      "northeast", "northwest", "southeast", "southwest"})


def in_sentence(title: str | None) -> str:
    """A room title mid-sentence: "The Old Mill" -> "the Old Mill"."""
    if not title:
        return "somewhere"
    return "the " + title[4:] if title.startswith("The ") else title


_place = in_sentence


def move_texts(name: str, direction: str | None, from_title: str | None,
               to_title: str | None, *, teleport: bool = False) -> dict:
    """The three tellings of one move: `you` (the mover, in the room reached),
    `leave` (those in the room left) and `arrive` (those in the room reached)."""
    to, frm = _place(to_title), _place(from_title)
    if teleport or not direction:
        return {"you": f"You find yourself in {to}.",
                "leave": f"{name} is suddenly elsewhere.",
                "arrive": f"{name} is suddenly here."}
    if direction == "up":
        return {"you": f"You climb up to {to}.", "leave": f"{name} climbs up to {to}.",
                "arrive": f"{name} comes up from {frm}."}
    if direction == "down":
        return {"you": f"You go down to {to}.", "leave": f"{name} goes down to {to}.",
                "arrive": f"{name} comes down from {frm}."}
    verb = ("head", "heads") if direction in _COMPASS else ("go", "goes")
    return {"you": f"You {verb[0]} {direction} to {to}.",
            "leave": f"{name} {verb[1]} {direction} to {to}.",
            "arrive": f"{name} comes in from {frm}."}


def _title(room) -> str | None:
    return room.properties.get("title", room.name) if room is not None else None


def announce_move(toon_id: str, from_room: str | None, to_room: str,
                  direction: str | None = None, *, teleport: bool = False):
    """Record a toon's move as two events: `move` keyed to the room it left
    (the WS layer's controlled-move trigger; its payload carries the mover's
    own line) and `arrive` keyed to the room it reached. Returns the move."""
    from daydream import events

    toon = objects.get(toon_id)
    frm = objects.get(from_room) if from_room else None
    dest = objects.get(to_room)
    name = toon.name if toon is not None else "someone"
    texts = move_texts(name, direction, _title(frm), _title(dest), teleport=teleport)
    base = {"from_room": from_room, "to_room": to_room, "name": name}
    if direction:
        base["direction"] = direction
    if teleport:
        base["teleport"] = True
    ev = events.append("toon", toon_id, "move",
                       {**base, "you": texts["you"], "text": texts["leave"]},
                       room_id=from_room)
    events.append("toon", toon_id, "arrive", {**base, "text": texts["arrive"]},
                  room_id=to_room)
    return ev


def send_home_things(toon_id: str) -> list[str]:
    """World objects a resting player carries go back to their authored home
    room (`properties.home`, recorded at load for worlds that opt in, or set
    on an authored spawn): the shared world's quest items never strand in an
    absent pocket. Keepsakes and finds have no home and stay. Returns the ids
    moved."""
    from daydream import events

    moved = []
    told = []
    for thing in objects.contents(toon_id, "thing"):
        room = home_of(thing)
        if room is None:
            continue
        objects.move(thing.id, room.id)
        events.append("system", None, "object_moved",
                      {"object_id": thing.id, "to": room.id, "reason": "home"},
                      room_id=room.id)
        moved.append(thing.id)
        told.append({"name": thing.name, "room": _title(room) or room.name})
    if told:
        # Said on the player's return, once (playtest 2026-09-28b: a thing
        # given for a quest was gone from their hands with no word).
        before = objects.get_property(toon_id, "went_home")
        before = [x for x in before if isinstance(x, dict)] if isinstance(before, list) else []
        objects.set_property(toon_id, "went_home", (before + told)[-10:])
    return moved


def home_of(thing: "objects.Object") -> "objects.Object | None":
    """The room a world thing goes back to when its carrier rests, or None for
    a keepsake or find, which stays with you."""
    home = thing.properties.get("home")
    room = objects.get(home) if isinstance(home, str) else None
    return room if room is not None and room.kind == "room" else None


def take_went_home(toon_id: str) -> list[dict]:
    """What went home while this player rested, told once: read and cleared."""
    got = objects.get_property(toon_id, "went_home")
    if not got:
        return []
    objects.set_property(toon_id, "went_home", [])
    return [x for x in got if isinstance(x, dict) and x.get("name")] if isinstance(got, list) else []


def kick_slot(slot: int) -> Toon | None:
    """Release `slot` to a non-drifting NPC (controller_session NULL,
    is_human_controlled 0, kicked_at <UTC ISO>). The toon keeps its room,
    inventory, mood, and memories. Returns the kicked Toon, or None if empty."""
    t = _slot_occupied(slot)
    if t is None:
        return None
    send_home_things(t.id)
    # When they rested, by the world's clock (so a faked clock still reads
    # right): the first connection after this composes "while you were
    # away" from it (daydream/absence.py).
    from daydream import worldclock

    objects.set_property(t.id, "away_since", worldclock.iso())
    db.get_conn().execute(
        "UPDATE objects SET controller_session = NULL, is_human_controlled = 0, "
        "kicked_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now') WHERE id = ?",
        (t.id,),
    )
    return get_toon(t.id)


def release_session_toon(session_id: str) -> Toon | None:
    """Rest (kick) every toon controlled by `session_id` (one, since taking a
    toon releases the others; more only in a world from before that). 'Leave
    the dream' calls this. Returns the first released toon, or None."""
    if not session_id:
        return None
    held = _query("controller_session = ? AND kicked_at IS NULL AND is_human_controlled = 1 "
                  "ORDER BY slot", (session_id,))
    rested = [kick_slot(t.slot) for t in held]
    return next((t for t in rested if t is not None), None)


def delete_slot(slot: int) -> Toon | None:
    """Permanently delete the human toon in `slot`, freeing it. The toon's
    carried things are DROPPED into its current room so a deleted character's
    belongings persist in the world to be found, rather than vanishing with the
    toon; its memories are removed and its events stay as append-only history.
    Returns the deleted toon, or None if the slot is empty."""
    t = _slot_occupied(slot)
    if t is None:
        return None
    # Carried things FK the toon via location_id. Reparent them to the toon's
    # room (drop on the ground) before deleting the toon, so no child references
    # the gone row. If the toon somehow has no room, remove them rather than
    # leave unreachable top-level rows.
    send_home_things(t.id)
    for thing_id in objects.content_ids(t.id, "thing"):
        if t.current_room_id is None:
            objects.delete(thing_id)
        else:
            objects.move(thing_id, t.current_room_id)
    db.get_conn().execute("DELETE FROM memories WHERE npc_id = ?", (t.id,))
    objects.delete(t.id)
    return t
