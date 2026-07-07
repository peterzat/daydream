"""Dream journal: the book remembers your story (SPEC 2026-07-07 criterion 3).

Leaving the dream (`POST /api/session/leave`) fires `write_entry` as a
background task for the released toon: ONE local-LLM call recaps the toon's
own recent events into a 2-3 sentence past-tense second-person entry,
validated (refusal parse, length window, WHIMSY banlist) and appended to a
FIFO-capped per-toon journal in `properties.journal`. Everything about it is
fail-closed and silent:

- `DAYDREAM_JOURNAL_ENABLED` is the kill switch (default on; tests force it
  off in conftest so the deterministic suite stays zero-LLM).
- Sequence idempotency: `properties.journal_last_seq` records the newest
  event a successful entry covered; leaving again with no newer events
  writes nothing and makes no LLM call. A failed/skipped write does NOT
  advance the marker, so the next leave retries with more to tell.
- LLM-down, refusal, or validation failure skips the entry silently; the
  leave endpoint never blocks on or fails from any of this.

Writes go through `objects.set_property` directly — journals are per-player
and invisible to others, so no event is broadcast. The snapshot carries the
controlled toon's own journal (never a co-located player's), and
`append_authored` lets authored beats (the loft's first-planting chapter
close) write a line with no LLM at all.

Per the generation policy this runs ONLY against the local model; there is
no cloud fallback."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from daydream import config, events, objects
from daydream.llm import client, safety

logger = logging.getLogger(__name__)

# FIFO cap on stored entries; the snapshot sends the last SNAPSHOT_ENTRIES.
MAX_ENTRIES = 10
SNAPSHOT_ENTRIES = 8

# How many of the toon's own most-recent events feed one recap.
RECAP_EVENT_WINDOW = 30

# Validation window for the LLM's entry (2-3 soft sentences).
MIN_ENTRY_CHARS = 60
MAX_ENTRY_CHARS = 500

JOURNAL_SYSTEM = (
    "You are the quiet keeper of a dream journal in a cozy watercolor world. "
    "A dreamer has just woken; you write ONE short entry recalling what they "
    "did, addressed to them.\n"
    'Return STRICT JSON only: {"entry": "..."}\n'
    "- 2-3 soft sentences, past tense, second person (\"you\").\n"
    "- Ground every sentence in the events given; never invent people, "
    "places, or deeds that are not there.\n"
    "- \"You\" is ONLY the dreamer. Other characters are named in the "
    "events; keep their deeds theirs, by name — never fold what a named "
    "character did into \"you\".\n"
    "- Tone: gentle, warm, a little wistful. Spiritfarer, A Short Hike. No "
    "urgency, no modern tech, no violence, no judgment.\n"
    "- 60-500 characters total.\n"
    "If the events are too thin to recall anything, refuse with "
    '{"refused": true, "reason": "<one soft in-character sentence>"}.\n'
    "Output ONLY the JSON object."
)


def entries_for_snapshot(toon_id: str) -> list[dict]:
    """The last few journal entries for the snapshot's `journal` field —
    the CONTROLLED toon only (the WS layer passes its own toon id; entries
    never ride toon cards, so a co-located player's journal is unreadable)."""
    stored = objects.get_property(toon_id, "journal")
    if not isinstance(stored, list):
        return []
    return [e for e in stored if isinstance(e, dict)][-SNAPSHOT_ENTRIES:]


def append_authored(toon_id: str, text: str) -> None:
    """Append an authored (no-LLM) entry — the first-planting chapter-close
    beat writes through here. Does not advance journal_last_seq: the marker
    tracks what the RECAP has covered, and an authored beat is not a recap."""
    line = (text or "").strip()
    if not line or objects.get(toon_id) is None:
        return
    _append(toon_id, {"text": line, "at": _now(), "authored": True})


async def write_entry(toon_id: str) -> None:
    """Recap the toon's recent events into one journal entry. Fire-and-forget
    safe: every failure path logs and returns; nothing raises out of here."""
    try:
        await _write_entry_inner(toon_id)
    except Exception:  # broad by contract: this runs as a background task
        logger.exception("journal: unexpected error for %s (entry skipped)", toon_id)


async def _write_entry_inner(toon_id: str) -> None:
    if not config.journal_enabled():
        return
    toon = objects.get(toon_id)
    if toon is None or toon.kind != "toon":
        return
    last_seq = toon.properties.get("journal_last_seq")
    if not isinstance(last_seq, int) or isinstance(last_seq, bool):
        last_seq = 0
    recent = events.fetch_for_toon(
        toon_id, since=last_seq, limit=RECAP_EVENT_WINDOW
    )
    lines = _event_lines(recent, toon_id)
    if not lines:
        return  # nothing new since the last entry: write nothing (idempotent)
    newest_seq = max(e.seq for e in recent)

    try:
        result = await client.acompletion_json(
            system=JOURNAL_SYSTEM,
            user=_user_prompt(toon.name, lines),
            max_tokens=220,
            timeout=20.0,
            purpose="journal",
        )
    except client.LLMUnavailable as e:
        logger.info("journal: LLM unavailable for %s (entry skipped): %s", toon_id, e)
        return

    if safety.parse_refusal(result) is not None:
        logger.info("journal: model refused recap for %s (entry skipped)", toon_id)
        return
    entry = result.get("entry") if isinstance(result, dict) else None
    if not isinstance(entry, str):
        return
    entry = entry.strip()
    if not (MIN_ENTRY_CHARS <= len(entry) <= MAX_ENTRY_CHARS):
        logger.info("journal: entry length %d out of window (skipped)", len(entry))
        return
    if safety.first_banned(entry) is not None:
        logger.info("journal: entry hit the banlist (skipped)")
        return

    _append(toon_id, {"text": entry, "at": _now()})
    # Advance the idempotency marker only on SUCCESS, so a skipped entry's
    # events stay tellable on the next leave.
    objects.set_property(toon_id, "journal_last_seq", newest_seq)


# ---- internals ------------------------------------------------------------


def _now() -> str:
    return datetime.now(tz=timezone.utc).isoformat(timespec="seconds")


def _append(toon_id: str, entry: dict) -> None:
    stored = objects.get_property(toon_id, "journal")
    entries = [e for e in stored if isinstance(e, dict)] if isinstance(stored, list) else []
    entries.append(entry)
    objects.set_property(toon_id, "journal", entries[-MAX_ENTRIES:])


def _event_lines(recent: list[events.Event], toon_id: str) -> list[str]:
    """Compact text lines for the recap prompt. Only kinds that carry
    player-meaningful text; ids never appear (names/text only)."""
    lines: list[str] = []
    for e in recent:
        p = e.payload
        if e.kind == "say":
            who = "you" if e.actor_id == toon_id else (p.get("name") or "someone")
            text = (p.get("text") or "").strip()
            if text:
                lines.append(f'{who} said: "{text}"')
        elif e.kind == "narrate":
            text = (p.get("text") or "").strip()
            if text:
                # Frame narration as WITNESSED: the room's prose describes
                # other characters' deeds, and without this frame the 7B
                # folds a named character's actions into "you" (journal
                # probe, 2026-07-07 — the a-quiet-sweep misattribution).
                lines.append(f"you saw: {text}")
        elif e.kind == "move" and e.actor_id == toon_id:
            direction = p.get("direction")
            if isinstance(direction, str) and direction:
                lines.append(f"you went {direction}")
    return lines


def _user_prompt(toon_name: str, lines: list[str]) -> str:
    body = "\n".join(f"- {ln}" for ln in lines)
    return (
        f"The dreamer is called {toon_name}. What happened in their dream, "
        f"oldest first:\n{body}\n\nWrite the JSON entry now."
    )
