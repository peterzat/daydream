-- A per-world "world_version" (MAJOR.MINOR string), stamped at `world load`
-- time and compared against the code's WORLD_VERSION at boot
-- (daydream/version.py:check_world_compat): a MAJOR mismatch refuses boot (the
-- live world can't be carried forward and the operator must
-- `bin/game world reset`); a MINOR or NULL mismatch only warns.
--
-- Distinct from the unused integer `schema_version` (001_initial.sql), which
-- this deliberately does NOT touch. NULL for any pre-012 world; back-filled to
-- '1.0' (the launch version) so an existing live world boots without a block.
ALTER TABLE worlds ADD COLUMN world_version TEXT;

UPDATE worlds SET world_version = '1.0' WHERE world_version IS NULL;
