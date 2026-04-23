-- 006_first_npc: add Rook, the forge-keeper, to r-forge.
--
-- The first hand-authored NPC in the world. Sits at r-forge, fitting
-- the existing narrative hint carried by skills/forge.json's
-- prompt_template ("someone has stepped away from the anvil") — this
-- is that someone, drifted back for a visit. The SPA's toons-in-room
-- rendering picks the row up through the existing toons panel; no
-- schema change required.
--
-- Slot convention: human-playable toons use slots 1-5 (per the v1
-- toon-slot-management BACKLOG entry). NPCs use slots 100+ to stay out
-- of the way of future slot management. Rook is slot 100.
--
-- Idempotency: INSERT OR IGNORE on the PK leaves an existing row
-- unchanged, so re-running this migration (or later migrations that
-- touch the same row) does not clobber manual edits or drift the
-- seed text once it's landed.

INSERT OR IGNORE INTO toons
    (id, world_id, slot, name, seed, appearance_seed, current_room_id,
     is_human_controlled, inventory_json, mood)
VALUES
    ('t-rook', 'w-bunny', 100, 'Rook',
     'the forge-keeper; slow-moving and quiet; hums old songs while working the bellows, sleeves always a little sooty',
     'a stocky person in a soot-smudged apron, kind eyes behind round spectacles, sleeves rolled past the elbows, hair wound up in a wool kerchief',
     'r-forge', 0, '[]', 'content');
