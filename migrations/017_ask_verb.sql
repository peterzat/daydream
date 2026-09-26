-- 017_ask_verb: every NPC can be asked about a topic (SPEC 2026-09-26
-- criterion 6).
--
-- `ask` is the deterministic producer for talk beats and authored topic
-- answers ("ask bell about the lanterns", or a clickable topic chip). Like
-- `talk` it belongs on the NPC archetype's default verb set, so append it to
-- the seeded npc prototype; worlds built by `world load` get it from the
-- loaders' _PROTOTYPES tables instead. Idempotent (the guard skips a
-- prototype that already carries it).

UPDATE objects
SET properties_json = json_set(properties_json, '$.verbs[#]', 'ask')
WHERE kind = 'prototype'
  AND name = 'npc'
  AND NOT EXISTS (
      SELECT 1 FROM json_each(objects.properties_json, '$.verbs')
      WHERE json_each.value = 'ask'
  );
