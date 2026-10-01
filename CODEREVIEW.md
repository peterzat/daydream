## Review — 2026-10-01c (commit: adc00ff)

**Summary:** Refresh review of `origin/main..adc00ff` (all files in focus): the second and third playthroughs' fixes (rail wheel, one-line margin band, keepsake shapes, the guide's letter example; the parser's clause-in-a-list and vocative talk; the Ledger's planted places; the prologue's gear trail and setting the gear in; answers kept in view through a re-render, one-row verb bar, the plant's text note, a refusal naming its word, threads counted once read, grown rooms painted from `art_seed`, unwritten notes read as a dream's words; WORLD_VERSION 1.15). Tests before: short+medium 2783 passed; after one /codefix cycle: 2785 passed. Security (/security, paths): 0 BLOCK / 1 WARN / 8 NOTE; the WARN is the first finding below, fixed.

**External reviewers:**
None configured.

### Findings

[WARN] daydream/growth.py:364 — `art_seed` puts the planter's raw phrase first, at weight 1.4, so the painting no longer follows what the dream-gardener kept: the gardener leaves unsafe content out of its `room_seed` (no people, no violence, no darkness; the validator checks it), and `art_seed` puts the player's original words back at the front of the image prompt. Only the 120-character cap and a three-word content banlist stand between a phrase and a painting every visitor sees, kept in the art keep. (security, measured with six text-only probes: an unclothed bather, a helmet with a bullet hole and a grave all passed the gates, the gardener dropped or softened them, and `art_seed` restored the original words)
  Evidence: `parts = [f"({words}:1.4)"] if words else []` over the whole cleaned phrase; colours are taken from the phrase, not from `room_seed`.
  Suggested fix: weight only the phrase's words that the gardener kept in `room_seed` (in order, colours included: a colour the composition dropped is not emphasised either); add a test where the composition drops a word of the phrase and `art_seed` leaves it out.

[WARN] worlds/lost-hours/arcs/00-prologue.json:51 — Tace now hands the gear back with the key, but the gear's home is still the well-court (`properties.home: r-well`), so a player who rests between the handover and opening the case wakes with the key gone home to the loft and the gear gone back into the moss across the village. Before this change the gear stayed with Tace. (`toons.send_home_things` moves every carried thing with a home on rest; `config.rest_returns_things` is on.)
  Evidence: the give rule spawns the key with `home: r-loft` and leaves the gear's `home: r-well` from 02-square.json.
  Suggested fix: in the give rule, set the gear's home to the loft (`{"kind": "set_property", "target_id": "o-escapement-gear", "key": "home", "value": "r-loft"}`), so after the handover both go home to Tace's bench; a walkthrough step that rests (or a unit test of `toons.home_of`) holding the gear after the handover.

[NOTE] daydream/parser.py — the vocative fast path runs before the verb fast paths, so a line that opens with a person's name and a comma is always speech to them ("<name>, take the lamp" asks them rather than taking it). Intended; noted.

### Fixes Applied

- [WARN] daydream/growth.py:364 — `art_seed` weights only the phrase's words the composition kept (in the phrase's order; a colour only when all its words are in `room_seed`), so the painting never restores what the gardener left out. New test `test_a_grown_rooms_painting_weights_only_what_the_composition_kept`; the two older art-seed tests updated to the rule.
- [WARN] worlds/lost-hours/arcs/00-prologue.json:51 — the handover sets the gear's home to the loft beside the key. New test `test_the_gear_tace_hands_back_goes_home_to_the_loft` (fails on the old world file).

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-10-01b, refresh, `6a934d1`): the playthrough fixes and the harness's honesty gates; 2 WARN fixed in one /codefix cycle (the "ask <name>" tab finds its row at click time, the reading index lets clicks through), 0 BLOCK.*

<!-- REVIEW_META: {"date":"2026-10-01","commit":"adc00ff","reviewed_up_to":"adc00ff8048126413ce1f4a8cee46d145188d75e","base":"origin/main","tier":"refresh","block":0,"warn":2,"note":1} -->
