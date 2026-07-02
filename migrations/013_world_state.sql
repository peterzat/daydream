-- 013_world_state: per-world KV for the world clock, flags, counters, score,
-- and authored definition blocks.
--
-- One row per (world_id, key); value_json holds any JSON value. Two key
-- families share the table:
--
--   Authored definitions, written once by the world loader and read-only at
--   runtime: def:verbs, def:rules, def:flags, def:fuses, def:daemons,
--   def:scoring, config, voice.
--
--   Runtime state, mutated by effects and the world clock: turn, score,
--   rng_seed, flag:<NAME>, counter:<name>, fuse:<name>, daemon:<name>.
--
-- Additive only: an existing world simply has no rows and every read falls
-- back to its documented default (turn 0, score 0, flags false, counters 0).
-- daydream/worldstate.py is the single read/write surface; no other module
-- issues SQL against this table.

CREATE TABLE IF NOT EXISTS world_state (
    world_id    TEXT NOT NULL REFERENCES worlds(id),
    key         TEXT NOT NULL,
    value_json  TEXT NOT NULL,
    updated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (world_id, key)
);
