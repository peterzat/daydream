-- 003_assets_world_and_pin: hardening pass on the v1 provenance system.
--
-- Three additions to generated_assets:
--   world_id      — single-DB-multi-world is on the roadmap (see
--                   world-bootstrap-opus in BACKLOG.md). The v1 schema
--                   assumed per-world DB and elided the column; that
--                   assumption breaks the moment Opus bootstraps a second
--                   world into the same DB. Add now while there's exactly
--                   one row to backfill.
--   pinned        — "do not GC" flag for hero images, README screenshots,
--                   anchor samples (see voice-and-aesthetic-audit-trail in
--                   BACKLOG.md). Used by zero code today; the future GC
--                   pass needs the column to already exist so it doesn't
--                   require its own migration.
--   workflow_hash — sha256-16 of the canonical workflow JSON used at gen
--                   time. The cache key now folds in this hash so workflow
--                   edits actually bust the cache; this column lets us
--                   query "which assets came from which workflow version"
--                   for diagnostics.
--
-- One destructive change:
--   ALTER TABLE rooms DROP COLUMN image_cache_key — dead since v1 (the
--   column was a v0 placeholder; v1 superseded it with the cache layout
--   keyed off room.seed and now generated_assets is the durable index).
--   Requires SQLite 3.35+ for DROP COLUMN; this box is on 3.37 and the
--   migration runner is local-only, so this is a hard requirement.
--
-- Backfill: single-world today, so world_id can be filled by selecting
-- the only world row. Multi-world worlds at this point would need a
-- per-asset join through rooms.world_id; that's not us yet.
ALTER TABLE generated_assets ADD COLUMN world_id TEXT;

ALTER TABLE generated_assets ADD COLUMN pinned INTEGER NOT NULL DEFAULT 0;

ALTER TABLE generated_assets ADD COLUMN workflow_hash TEXT;

UPDATE generated_assets
SET    world_id = (SELECT id FROM worlds LIMIT 1)
WHERE  world_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_generated_assets_world
    ON generated_assets(world_id);

ALTER TABLE rooms DROP COLUMN image_cache_key;
