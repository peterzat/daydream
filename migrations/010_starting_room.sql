-- A per-world "starting room": where a toon wakes after any rest (re-claim),
-- and where a freshly created toon spawns. Plain TEXT (no FK -- like
-- events.room_id, it tags a room that may later be edited/removed); the
-- daydream.rooms.starting_room_id helper falls back to the world's first room
-- when this is unset or points at a since-deleted room, so every world always
-- resolves to SOME room. Seeded for the canonical w-bunny world to its meadow.
ALTER TABLE worlds ADD COLUMN starting_room_id TEXT;

UPDATE worlds SET starting_room_id = 'r-meadow' WHERE id = 'w-bunny';
