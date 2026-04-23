-- 002_generated_assets: provenance for generated assets (images first; the
-- schema is asset-kind-agnostic so future kinds — audio, regenerated text —
-- land here without another migration).
--
-- Why per-world: the DB is per-world (worlds-{env}/live.db), so world_id is
-- implicit. file_relpath is stored relative to data_dir() (e.g.
-- 'images/cache/{world}/{room}/{hash}.png'); that keeps `bin/game world
-- archive` a one-line tar against data_dir() and `bin/game world delete`
-- a one-line rm of `images/cache/{world}/`.
--
-- Why this column set:
--   asset_kind   — extensibility hook ('image' for v1; 'audio'/'text' later).
--   target_kind  — what in-world entity owns the asset ('room', 'toon', 'item').
--   target_id    — the entity row id (e.g. 'r-meadow').
--   target_seed  — the seed text the asset was generated from. Stored so
--                  re-derivation never requires re-reading the entity row,
--                  and so the seed is captured even if the entity is later
--                  edited or deleted.
--   seed_hash    — 16-char hex of SHA-256(seed); same as cache.seed_hash().
--                  The (target_kind, target_id, seed_hash) triple is the
--                  natural unique key.
--   file_relpath — path on disk relative to data_dir(). Decouples DB from
--                  the absolute path so DAYDREAM_DATA_DIR moves don't break
--                  rows.
--   model, lora  — the actual model + LoRA the workflow used at gen time.
--                  Captured from the workflow JSON post-build so the recorded
--                  values match what was sent to ComfyUI, not the workflow
--                  defaults. Optional because future asset kinds (e.g. text)
--                  may not have a LoRA.
--   prompt_text  — the full prompt string that was sent. Captured so changing
--                  WHIMSY_PROMPT_SUFFIX later doesn't lose what produced the
--                  existing image.
--   generated_at — wall clock for ordering / retention queries.
--   file_bytes   — size on disk at generation time. Lets list-assets show
--                  cache footprint without statting every file.
--
-- The CREATE TABLE IF NOT EXISTS keeps the migration idempotent under the
-- migration runner's filename-not-yet-applied check; it's belt-and-suspenders
-- for any operator who replays SQL by hand.
CREATE TABLE IF NOT EXISTS generated_assets (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    asset_kind    TEXT NOT NULL,
    target_kind   TEXT NOT NULL,
    target_id     TEXT NOT NULL,
    target_seed   TEXT NOT NULL,
    seed_hash     TEXT NOT NULL,
    file_relpath  TEXT NOT NULL,
    model         TEXT,
    lora          TEXT,
    prompt_text   TEXT,
    generated_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    file_bytes    INTEGER,
    UNIQUE (target_kind, target_id, seed_hash)
);

CREATE INDEX IF NOT EXISTS idx_generated_assets_target
    ON generated_assets(target_kind, target_id);
