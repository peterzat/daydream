-- 008_second_npc: add Iris, the attic archivist, to r-attic.
--
-- Second hand-authored NPC in the world. Sits at r-attic, contrasting
-- with Rook's forge in role (archivist vs craftsperson), mood (thoughtful
-- vs content), and register (slightly more bookish + curious vs Rook's
-- "say less than they mean" laconic). The attic was already seeded with
-- a "someone-keeps-things-here" feeling (trunks, round window, cedar
-- smell, dust); Iris is who keeps them.
--
-- Slot convention: human-playable toons use slots 1-5 (per the v1
-- toon-slot-management BACKLOG entry). NPCs use slots 100+. Rook is
-- slot 100 (migration 006); Iris is slot 101.
--
-- presence_text fires once when the controlled toon enters the room
-- (per migration 007's broadcast-loop mechanism). Mirrors Rook's pattern.
--
-- Idempotency: INSERT OR IGNORE on the PK leaves an existing row
-- unchanged, and the UPDATE sets presence_text to the same string each
-- run, so re-running the migration converges without clobber or drift.

INSERT OR IGNORE INTO toons
    (id, world_id, slot, name, seed, appearance_seed, current_room_id,
     is_human_controlled, inventory_json, mood)
VALUES
    ('t-iris', 'w-bunny', 101, 'Iris',
     'the attic archivist; older, soft-voiced, curious; sorts old letters and small objects with patient attention; sometimes reads passages aloud to no one in particular',
     'an older person with reading glasses on a beaded cord, ink-stained fingertips, a soft cardigan with patched elbows, hair gone silver at the temples',
     'r-attic', 0, '[]', 'thoughtful');

UPDATE toons
SET presence_text = 'Iris glances up from a sheaf of old letters, marks her place with a strip of ribbon, and offers a small nod before returning to her sorting.'
WHERE id = 't-iris';
