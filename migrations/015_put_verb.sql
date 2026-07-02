-- 015_put_verb: every takeable thing is puttable.
--
-- Real containers land with the Zork turn (SPEC 2026-07-02 criterion 4);
-- `put` is the engine verb that moves a carried thing into/onto one. Like
-- take/drop it belongs on the thing archetypes' default verb sets, so append
-- it to the seeded prototypes. json '$.verbs[#]' appends to the array;
-- worlds built by `world load` get 'put' from the loader's _PROTOTYPES
-- table instead. The correlated-subquery guard keeps the append idempotent
-- for any DB whose prototypes already carry it.

UPDATE objects
SET properties_json = json_set(properties_json, '$.verbs[#]', 'put')
WHERE kind = 'prototype'
  AND name IN ('thing', 'readable')
  AND NOT EXISTS (
      SELECT 1 FROM json_each(objects.properties_json, '$.verbs')
      WHERE json_each.value = 'put'
  );
