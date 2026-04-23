-- 004_multi_room: extend the v0 meadow into a 5-room connected world for
-- the multi-room-navigation spec. Adds 4 rooms and populates
-- bidirectional exits_json on all of them. The meadow is preserved
-- (UPDATE by id, not DELETE + re-insert).
--
-- Room graph:
--
--        r-attic
--          |  up / down
--        r-forge   r-hollow
--          |  n/s    |  w/e
--        r-meadow --- r-bridge
--               e / w
--
-- Seeds match the WHIMSY anchor (cozy, soft, painterly, Spiritfarer-
-- adjacent). Each seed is what image-gen (SDXL + watercolor LoRA) and
-- narration receive, so be specific-sensory rather than grand.
--
-- Idempotency:
--   * INSERT OR IGNORE on the new rooms' primary-key IDs: re-running
--     leaves existing rows unchanged (no duplicates, no clobber).
--   * UPDATE on exits_json converges to the same JSON each time; so
--     editing this migration and re-running it does NOT accumulate,
--     and an operator-made in-place exit tweak is reverted to the
--     canonical shape on next boot (by design — `exits_json` is the
--     single source of truth per SPEC criterion 2, and this migration
--     IS that truth).

INSERT OR IGNORE INTO rooms (id, world_id, slug, title, seed, description_cached) VALUES
    ('r-forge', 'w-bunny', 'forge', 'The Quiet Forge',
     'the quiet forge with embers drifting like sleepy fireflies, soft watercolor edges',
     'The forge glows with banked embers. Someone has stepped away; their tools rest in neat rows, warm to the touch.'),
    ('r-bridge', 'w-bunny', 'bridge', 'A Wooden Bridge',
     'a wooden bridge over a slow stream, dragonflies and warm afternoon light, painterly',
     'A wooden bridge arches gently over a slow stream. Dragonflies drift. The boards creak in a friendly way.'),
    ('r-attic', 'w-bunny', 'attic', 'A Dusty Attic',
     'an attic with afternoon dust in slanting light, old trunks and a small round window',
     'The attic smells like old paper and cedar. A round window throws a warm spotlight on stacks of forgotten trunks.'),
    ('r-hollow', 'w-bunny', 'hollow', 'The Birch Hollow',
     'a hollow between birches, moss-draped stones, a soft hush at the edge of dusk',
     'A small clearing in the birches. Moss softens everything. A breeze moves through without disturbing it.');

-- Bidirectional exits. UPDATE-by-id is idempotent: re-runs re-write the
-- same JSON, and every mapping is mirrored by the reverse direction on
-- its target room.
UPDATE rooms SET exits_json = '{"north":"r-forge","east":"r-bridge"}' WHERE id = 'r-meadow';
UPDATE rooms SET exits_json = '{"south":"r-meadow","up":"r-attic"}'   WHERE id = 'r-forge';
UPDATE rooms SET exits_json = '{"west":"r-meadow","east":"r-hollow"}' WHERE id = 'r-bridge';
UPDATE rooms SET exits_json = '{"down":"r-forge"}'                    WHERE id = 'r-attic';
UPDATE rooms SET exits_json = '{"west":"r-bridge"}'                   WHERE id = 'r-hollow';
