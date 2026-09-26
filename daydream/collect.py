"""Collectibles: the daily find and the per-player book (SPEC 2026-09-26
criterion 12).

Authored data:

- `collectibles` (worldstate `def:collectibles`): a list of
  `{"id", "name", "text", "page"}`. `name` is what the book lists; `text`
  is the one-line story revealed when it is found.
- `pages` (worldstate `def:pages`): `{"<page>": {"title", "reward"?:
  {"text"?, "do"?: [effects]}}}`. A page is complete when its player has
  found every collectible on it; its reward applies once per player.
- `config.collect`: `{"per_day": 2, "rooms": [room ids], "name": "stray
  minute", "aliases": [...], "seed": "...", "found_text": "...",
  "book_title": "...", "requires_time": true}`.

The daily find is PER PLAYER: each player's finds for a local date are
private things (`properties.private_to`) placed by a stable roll keyed on
(date, toon), so what one player collects never takes anything from
another. Yesterday's unfound glints fade overnight and return to the pool.
Taking one catalogues it in the player's book (`pq:<toon>:collected`) and
removes the object; the book lives in the satchel.
"""

from __future__ import annotations

import logging

from daydream import events, objects, worldclock, worldstate

logger = logging.getLogger(__name__)


def cfg(world_id: str) -> dict:
    c = worldstate.get(world_id, "config")
    d = c.get("collect") if isinstance(c, dict) else None
    return d if isinstance(d, dict) else {}


def items(world_id: str) -> dict[str, dict]:
    d = worldstate.get(world_id, "def:collectibles")
    out: dict[str, dict] = {}
    for it in d if isinstance(d, list) else []:
        if isinstance(it, dict) and isinstance(it.get("id"), str):
            out[it["id"]] = it
    return out


def pages(world_id: str) -> dict[str, dict]:
    d = worldstate.get(world_id, "def:pages")
    return {k: v for k, v in d.items() if isinstance(v, dict)} if isinstance(d, dict) else {}


def found(world_id: str, toon_id: str) -> list[dict]:
    from daydream import story

    v = story.pget(world_id, toon_id, "collected")
    return [e for e in v if isinstance(e, dict)] if isinstance(v, list) else []


def found_ids(world_id: str, toon_id: str) -> set[str]:
    return {e.get("id") for e in found(world_id, toon_id)}


def count(world_id: str, toon_id: str, page: str | None = None) -> int:
    ids = found_ids(world_id, toon_id)
    if page is None:
        return len(ids)
    all_items = items(world_id)
    return sum(1 for i in ids if (all_items.get(i) or {}).get("page") == page)


def _record(world_id: str, toon_id: str, item_id: str) -> bool:
    from daydream import story, village

    log = found(world_id, toon_id)
    if any(e.get("id") == item_id for e in log):
        return False
    log.append({"id": item_id, "day": village.day(world_id), "at": worldclock.iso()})
    story.pset(world_id, toon_id, "collected", log)
    return True


def _check_pages(world_id: str, toon_id: str, room_id: str | None) -> None:
    """Apply each newly completed page's authored reward, once per player."""
    from daydream import rules, story
    from daydream.skills import effects

    have = found_ids(world_id, toon_id)
    all_items = items(world_id)
    for pid, page in pages(world_id).items():
        members = {i for i, it in all_items.items() if it.get("page") == pid}
        if not members or not members <= have:
            continue
        if story.pget(world_id, toon_id, f"page:{pid}"):
            continue
        story.pset(world_id, toon_id, f"page:{pid}", worldclock.iso())
        reward = page.get("reward") if isinstance(page.get("reward"), dict) else {}
        events.append("system", None, "page_completed",
                      {"page": pid, "title": page.get("title")},
                      room_id=room_id, recipient_id=toon_id)
        text = reward.get("text")
        if isinstance(text, str) and text.strip():
            events.append("system", None, "narrate", {"text": text.strip()},
                          room_id=room_id, recipient_id=toon_id)
        if isinstance(reward.get("do"), list) and reward["do"]:
            actor = objects.get(toon_id)
            if actor is not None:
                ctx = rules._build_ctx(actor, None, None, room_id or "", None,
                                       f"page:{pid}")
                effects.dispatch_effects(
                    rules.resolve_sigils(reward["do"], ctx), actor_id=toon_id,
                    room_id=room_id or "", world_id=world_id,
                    allowed=effects.RULE_KINDS,
                )


def grant(world_id: str, toon_id: str, item_id: str | None = None,
          room_id: str | None = None) -> events.Event | None:
    """Catalogue one collectible straight into a player's book (an authored
    reward). No id = a stable pick among the ones they have not found."""
    all_items = items(world_id)
    if item_id is None:
        pool = sorted(set(all_items) - found_ids(world_id, toon_id))
        if not pool:
            return None
        rng = worldstate.rng_stable(world_id, f"grant:{toon_id}:{len(pool)}")
        item_id = rng.choice(pool)
    it = all_items.get(item_id)
    if it is None or not _record(world_id, toon_id, item_id):
        return None
    ev = events.append("system", None, "collected",
                       {"id": item_id, "name": it.get("name")},
                       room_id=room_id, recipient_id=toon_id)
    _announce(world_id, toon_id, it, room_id)
    _check_pages(world_id, toon_id, room_id)
    return ev


def _announce(world_id: str, toon_id: str, it: dict, room_id: str | None) -> None:
    template = cfg(world_id).get("found_text") or "You find {name}: {text}"
    line = template.replace("{name}", str(it.get("name", ""))).replace(
        "{text}", str(it.get("text", "")))
    events.append("system", None, "narrate", {"text": line.strip()},
                  room_id=room_id, recipient_id=toon_id)


def is_collectible(thing: objects.Object) -> bool:
    return isinstance(thing.properties.get("collectible"), str)


def collect(actor: objects.Object, thing: objects.Object, room_id: str) -> bool:
    """A player takes a collectible: catalogue it, remove the glint, tell its
    story (privately). Only its owner can (it is private to them anyway)."""
    owner = thing.properties.get("private_to")
    if owner and owner != actor.id:
        return False
    item_id = thing.properties["collectible"]
    it = items(actor.world_id).get(item_id)
    objects.delete(thing.id)
    events.append("system", None, "object_moved",
                  {"object_id": thing.id, "dest_id": None}, room_id=room_id,
                  recipient_id=actor.id)
    if it is None or not _record(actor.world_id, actor.id, item_id):
        return True
    events.append("system", None, "collected",
                  {"id": item_id, "name": it.get("name")},
                  room_id=room_id, recipient_id=actor.id)
    _announce(actor.world_id, actor.id, it, room_id)
    _check_pages(actor.world_id, actor.id, room_id)
    return True


def ensure_daily(toon_id: str) -> list[str]:
    """Place today's finds for one player (idempotent per local date).
    Returns the ids of things spawned now ([] when already placed)."""
    from daydream import story, village

    toon = objects.get(toon_id)
    if toon is None or toon.kind != "toon" or not toon.is_human_controlled:
        return []
    world_id = toon.world_id
    c = cfg(world_id)
    if not c or not items(world_id):
        return []
    if c.get("requires_time", True) and not village.running(world_id):
        return []
    today = village.local_date(world_id)
    if story.pget(world_id, toon_id, "collect_day") == today:
        return []
    # Yesterday's unfound glints fade (they return to the pool).
    for oid in story.pget(world_id, toon_id, "collect_spawned") or []:
        o = objects.get(oid) if isinstance(oid, str) else None
        if o is not None and o.properties.get("private_to") == toon_id \
                and o.location_id != toon_id:
            objects.delete(oid)
    story.pset(world_id, toon_id, "collect_day", today)
    pool = sorted(set(items(world_id)) - found_ids(world_id, toon_id))
    rooms = [r for r in (c.get("rooms") or []) if isinstance(r, str) and objects.get(r)]
    per_day = c.get("per_day", 1)
    n = min(per_day if isinstance(per_day, int) else 1, len(pool), len(rooms))
    if n <= 0:
        story.pset(world_id, toon_id, "collect_spawned", [])
        return []
    rng = worldstate.rng_stable(world_id, f"collect:{today}:{toon_id}")
    picks = rng.sample(pool, n)
    where = rng.sample(rooms, n)
    spawned = []
    name = c.get("name") or "keepsake"
    aliases = [a for a in c.get("aliases") or [] if isinstance(a, str)]
    for item_id, room in zip(picks, where, strict=True):
        o = objects.spawn(
            world_id, "thing", name, room, prototype_id=objects.PROTO_THING,
            aliases=aliases,
            properties={"seed": c.get("seed") or "", "collectible": item_id,
                        "private_to": toon_id, "is_unique": 1},
        )
        spawned.append(o.id)
    story.pset(world_id, toon_id, "collect_spawned", spawned)
    return spawned


def book(world_id: str, toon_id: str) -> dict | None:
    """The snapshot `book` block for the controlled player: every page with
    its entries (found ones carry their story; unfound ones only a blank),
    completion, and the reward line once earned."""
    c = cfg(world_id)
    all_items = items(world_id)
    if not all_items:
        return None
    have = {e.get("id"): e for e in found(world_id, toon_id)}
    from daydream import story

    out_pages = []
    for pid, page in pages(world_id).items():
        members = [i for i, it in all_items.items() if it.get("page") == pid]
        entries = []
        for i in members:
            it = all_items[i]
            if i in have:
                entries.append({"id": i, "found": True, "name": it.get("name"),
                                "text": it.get("text"), "day": have[i].get("day")})
            else:
                entries.append({"id": i, "found": False})
        done = bool(story.pget(world_id, toon_id, f"page:{pid}"))
        reward = page.get("reward") if isinstance(page.get("reward"), dict) else {}
        out_pages.append({
            "id": pid, "title": page.get("title") or pid,
            "found": sum(1 for e in entries if e["found"]), "total": len(entries),
            "complete": done,
            "reward_text": reward.get("text") if done else None,
            "entries": entries,
        })
    return {"title": c.get("book_title") or "Book", "found": len(have),
            "total": len(all_items), "pages": out_pages}
