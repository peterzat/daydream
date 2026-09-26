"""The raw input log: every word a player types is kept (SPEC 2026-09-26
criterion 16, migration 016).

One row per inbound command. Free text is recorded verbatim BEFORE parsing
(so an input the LLM could not ground, or typed during an outage, is still
kept) and its resolved commands are attached after. A click records the
structured command. Rows are private: this is not the event log, nothing
here is broadcast, and only the dream digest and the export read it.

`export_walkthrough` turns a recorded session into a walkthrough dataset
(the `daydream.walkthrough` format), so a real player's session becomes a
replayable regression (docs/PIVOT.md section 9).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass

from daydream import db, events, objects, worldclock

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Input:
    seq: int
    created_at: str
    world_id: str | None
    toon_id: str
    room_id: str | None
    source: str
    text: str | None
    verb: str | None
    dobj_id: str | None
    iobj_id: str | None
    args: str | None
    resolved: list | None
    event_seq: int | None

    @classmethod
    def from_row(cls, row) -> Input:
        try:
            resolved = json.loads(row["resolved_json"]) if row["resolved_json"] else None
        except (json.JSONDecodeError, TypeError):
            resolved = None
        return cls(
            seq=row["seq"], created_at=row["created_at"], world_id=row["world_id"],
            toon_id=row["toon_id"], room_id=row["room_id"], source=row["source"],
            text=row["text"], verb=row["verb"], dobj_id=row["dobj_id"],
            iobj_id=row["iobj_id"], args=row["args"], resolved=resolved,
            event_seq=row["event_seq"],
        )

    def to_dict(self) -> dict:
        return {
            "seq": self.seq, "created_at": self.created_at, "toon_id": self.toon_id,
            "room_id": self.room_id, "source": self.source, "text": self.text,
            "verb": self.verb, "dobj_id": self.dobj_id, "iobj_id": self.iobj_id,
            "args": self.args, "resolved": self.resolved,
        }


def record(
    toon_id: str,
    source: str,
    *,
    text: str | None = None,
    verb: str | None = None,
    dobj_id: str | None = None,
    iobj_id: str | None = None,
    args: str | None = None,
    resolved: list | None = None,
) -> int | None:
    """Append one input row; returns its seq. Fail-soft: a logging failure
    must never break play, so any error is logged and None returned."""
    try:
        actor = objects.get(toon_id)
        cur = db.get_conn().execute(
            "INSERT INTO inputs (created_at, world_id, toon_id, room_id, source, "
            "text, verb, dobj_id, iobj_id, args, resolved_json, event_seq) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                worldclock.iso(),
                actor.world_id if actor else None,
                toon_id,
                actor.location_id if actor else None,
                source, text, verb, dobj_id, iobj_id, args,
                json.dumps(resolved) if resolved is not None else None,
                events.max_seq(),
            ),
        )
        return cur.lastrowid
    except Exception:
        logger.warning("input log write failed", exc_info=True)
        return None


def set_resolved(seq: int | None, resolved: list) -> None:
    """Attach the resolved commands to a free-text row after parsing."""
    if seq is None:
        return
    try:
        db.get_conn().execute(
            "UPDATE inputs SET resolved_json = ? WHERE seq = ?",
            (json.dumps(resolved), seq),
        )
    except Exception:
        logger.warning("input log resolve write failed", exc_info=True)


def fetch(
    since: int = 0, toon_id: str | None = None, until: int | None = None
) -> list[Input]:
    sql = "SELECT * FROM inputs WHERE seq > ?"
    params: list = [since]
    if toon_id is not None:
        sql += " AND toon_id = ?"
        params.append(toon_id)
    if until is not None:
        sql += " AND seq <= ?"
        params.append(until)
    sql += " ORDER BY seq"
    return [Input.from_row(r) for r in db.get_conn().execute(sql, tuple(params))]


def max_seq() -> int:
    row = db.get_conn().execute("SELECT MAX(seq) FROM inputs").fetchone()
    return row[0] or 0


def export_walkthrough(
    toon_id: str, since: int = 0, until: int | None = None, name: str = "recorded"
) -> dict:
    """A recorded session as a walkthrough dataset: typed lines replay as
    `cmd` steps (through the parser, like the player typed them); clicks
    replay as structured `command` steps (straight to the executor, like the
    player clicked them). Each step keeps its original timestamp so a
    replayer can pin the fake clock to it."""
    steps: list[dict] = []
    for row in fetch(since=since, toon_id=toon_id, until=until):
        if row.source == "text" and row.text:
            steps.append({"cmd": row.text, "at": row.created_at})
        elif row.source == "command" and row.verb:
            cmd = {"verb": row.verb}
            for k in ("dobj_id", "iobj_id", "args"):
                v = getattr(row, k)
                if v:
                    cmd[k] = v
            steps.append({"command": cmd, "at": row.created_at})
    return {
        "comment": f"Exported from the raw input log for {toon_id}.",
        "actor": toon_id,
        "segments": [{"name": name, "commands": steps}],
    }
