-- 007_npc_presence: add `presence_text` column to the toons table and
-- set Rook's greeting.
--
-- When the controlled toon moves into a room containing an NPC, the
-- WS broadcast loop (after sending the post-move snapshot) emits one
-- `narrate` event per co-located NPC whose `presence_text` is a
-- non-empty string. This gives the NPC a felt "they're here" line
-- without committing to a dialogue protocol yet.
--
-- Nullable (default NULL) so existing rows survive the ADD COLUMN and
-- toons without an authored greeting remain silently present — the
-- emitter treats NULL / empty / whitespace-only as "no greeting,
-- skip." Wren (the player's toon) stays NULL: the controlled toon is
-- filtered out of the greeting iteration anyway, so the column value
-- there is moot.

ALTER TABLE toons ADD COLUMN presence_text TEXT;

UPDATE toons
SET presence_text = 'Rook is at the bellows, sleeves a little sooty, humming something slow under their breath.'
WHERE id = 't-rook';
