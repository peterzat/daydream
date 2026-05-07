-- 009_memories: per-world NPC memory store for the dialogue path.
--
-- Each row is one captured memory tied to a specific NPC (npc_id) within a
-- specific world (world_id). The text column carries the human-readable
-- snippet ("the visitor said: ...", "Rook said: ..."); the embedding column
-- holds the raw float32 bytes from the CPU embedder (BGE-small produces
-- 384 dims = 1536 bytes), used for cosine-similarity ranking at retrieval.
--
-- Why no FK on npc_id (or on world_id beyond the existing pattern):
-- mirrors the events table — the memory log is append-only history that
-- must outlive a deleted toon. world_id stays FK to worlds(id) since
-- per-world scoping is load-bearing for the retrieve contract; an NPC
-- removed via future tooling would still want their old memories
-- queryable for forensics, just not reachable via the live dialogue
-- path. source_event_seq is a soft pointer to the events row that
-- triggered capture, useful for tracing memories back to their origin
-- but not enforced as a FK because events themselves carry no FK.
--
-- Index supports the v0 retrieval query: SELECT all rows for a given
-- (npc_id, world_id), ordered DESC by created_at — the in-Python
-- ranker walks them once and returns the top-K. Index covers the
-- WHERE-and-ORDER-BY shape so even thousands of memories don't trigger
-- a sort.
--
-- Idempotency: CREATE TABLE IF NOT EXISTS + CREATE INDEX IF NOT EXISTS
-- so re-running the migration converges without error.

CREATE TABLE IF NOT EXISTS memories (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    world_id          TEXT NOT NULL REFERENCES worlds(id),
    npc_id            TEXT NOT NULL,
    text              TEXT NOT NULL,
    embedding         BLOB NOT NULL,
    created_at        TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source_event_seq  INTEGER
);

CREATE INDEX IF NOT EXISTS idx_memories_npc_world_recent
    ON memories(npc_id, world_id, created_at DESC);
