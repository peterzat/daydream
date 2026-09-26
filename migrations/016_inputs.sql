-- 016_inputs: every word a player types is kept (SPEC 2026-09-26 criterion 16).
--
-- The event log records what HAPPENED (effects, narration); it never recorded
-- what the player TYPED, so the one real playtest had to be reconstructed by
-- inference. This table is the raw input log: one row per inbound command,
-- free text (`source='text'`, the typed line verbatim) or a structured click
-- (`source='command'`, the verb + ids). `resolved_json` holds what the
-- command resolved to (the parser's grounded commands for free text; the
-- click itself for a command). `event_seq` is the event-log high-water mark
-- when the input arrived, so a digest can line inputs up with their effects.
--
-- Private by construction: nothing here is ever broadcast (it is not the
-- event log). The dream digest reads it; `bin/game dream export` turns a
-- recorded session into a walkthrough dataset. `created_at` is written by the
-- application clock (daydream.worldclock), so tests can pin it.

CREATE TABLE IF NOT EXISTS inputs (
    seq           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at    TEXT NOT NULL,
    world_id      TEXT,
    toon_id       TEXT NOT NULL,
    room_id       TEXT,
    source        TEXT NOT NULL CHECK (source IN ('text', 'command')),
    text          TEXT,
    verb          TEXT,
    dobj_id       TEXT,
    iobj_id       TEXT,
    args          TEXT,
    resolved_json TEXT,
    event_seq     INTEGER
);

CREATE INDEX IF NOT EXISTS idx_inputs_toon_seq ON inputs(toon_id, seq);
