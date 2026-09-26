## Review — 2026-09-26b (commit: 6b1af0f) — refresh

**Summary:** Refresh review of the pre-pivot cleanup commits since e765561:
the non-string appearance_seed crash fix (d6772dd), the CI lint fix
(2a1adaf), the default-model revision pin + vllm-down engine wait (51b64d7),
and the TESTING.md refresh (e613cef). Claude's own review of these found
nothing; /security over the 8 changed paths found one WARN that widens the
appearance_seed NOTE this pass fixed.

**Review scope:** Refresh review of 9 changed files since e765561; /security
over the 8 changed code paths. Tests after the fix loop: ruff clean, short 845,
medium 1234, long 1273 (real vLLM + ComfyUI; refusal probe 0/21 on the real
talk path with the new effect list; all ratified goldens hold).

**External reviewers:** None configured.

### Findings

```
[WARN] daydream/verbs.py:116, daydream/skills/effects.py:93 — talk (and every
       standalone data skill via DEFAULT_KINDS) lets the dialogue LLM write ANY
       property on ANY object with ANY JSON value (from /security)
  Evidence: talk's allowed_effects = {narrate, set_property, set_mood,
  spawn_object}; DEFAULT_KINDS = ALLOWED_KINDS - RESTRICTED_KINDS still
  contains set_property. /security reproduced on a real server (loft world,
  mocked model output, production code after it): a non-string seed on the
  starting room crashes every room snapshot, a persistent game-wide lockout
  that survives restart; a non-string presence_text disconnects everyone who
  enters that room; writing a room's exits/title bypasses the restricted
  link_exit/rename_object kinds; string values skip the output banlist. With
  the live Qwen3.5 9B on the real talk path, a player injection got the model
  to emit a non-string presence_text 9/9 and an integer room seed 3/9. No
  authored dialogue or room skill emits set_property (verified: set_mood has
  its own string-validated applier; engine verbs like open/use/examine/plant
  grant set_property through their own explicit allowlists, and no VerbSpec
  falls back to DEFAULT_KINDS).
  Suggested fix: add "set_property" to RESTRICTED_KINDS (per-verb opt-in, like
  rename_object; DEFAULT_KINDS then drops it automatically) and remove it from
  talk's allowed_effects. Keep the engine verbs' explicit grants unchanged.
  Update tests/security/test_appearance_seed_gate.py so the read-normalization
  test writes the bad value with objects.set_property directly, and add a
  regression test that a talk-dispatched set_property (and a DEFAULT_KINDS
  data-skill one) is rejected with no mutation. Update the docstring at
  daydream/skills/data.py:316 and the effects.py comments that describe the
  kind sets.
```

```
[WARN] CLAUDE.md:94 — the "World-mutation effect API" bullet no longer matches
       the effect kind sets after the cycle-1 fix (re-review, cycle 2)
  Evidence: it says the RESTRICTED kinds are "spawn_room/link_exit
  world-shaping + rename_object housekeeping", that `allowed=None` excludes
  "them", and that "plant is their sole consumer". set_property is now also
  restricted (effects.py RESTRICTED_KINDS), is off talk's allowlist, and is
  granted explicitly by several engine verbs (examine, use, open, close,
  plant, attack, board, disembark) plus RULE_KINDS. CLAUDE.md is the agent's
  operating contract; a future session would believe NPC dialogue can still
  set properties.
  Suggested fix: edit that bullet only: add set_property to the restricted
  list as the per-verb opt-in "arbitrary property write" kind (off talk and
  the data-skill default; engine verbs and authored rules declare it; dialogue
  mood uses the string-validated set_mood), and scope "plant is their sole
  consumer" to the world-shaping kinds.
```

### Fixes Applied

- Cycle 1 (WARN, effects.py/verbs.py): set_property added to RESTRICTED_KINDS
  (DEFAULT_KINDS drops it) and removed from talk's allowed_effects; engine-verb
  grants and RULE_KINDS unchanged. New tier_short tests
  (tests/security/test_set_property_gate.py) drive the real talk and data-skill
  paths with a hostile mocked model and assert no mutation; they fail on the
  old kind sets. Handler tests in test_effects.py now opt in explicitly.

- Cycle 2 (WARN, CLAUDE.md:94): the effect-API bullet now lists set_property
  among the restricted per-verb opt-in kinds and scopes "plant is the sole
  consumer" to the world-shaping kinds and rename_object.

Both landed in 6b1af0f.

```
[NOTE] daydream/verbs.py:173 — the comment above plant's allowlist calls plant
       "the first (and sole) consumer of the restricted effect kinds"
  Evidence: pre-existing inaccuracy (attack grants destroy_object/kill_actor,
  take/put grant adjust_score), now further off since several engine verbs
  grant set_property. Comment only; no behavior. Suggested fix: scope it to
  the world-shaping kinds in a future touch of that file.
```

### Accepted Risks

Carried forward from the prior entry (unchanged; the standing register lives
in SECURITY.md):

- **LLM-emitted effects take an unscoped, LLM-chosen target id** within each
  verb's allowed subset; rule-only kinds unreachable from LLM-facing dispatch.
- Friend-scope posture: CSRF-gated slot/session endpoints, Origin-checked /ws,
  liveness-gated claim takeover, AccessMiddleware-gated /status + /cache,
  cookie https_only=False, CGNAT hardcoding, tailscale is_authed bypass,
  stored prompt-injection via captured memory, bootstrap $MODEL heredoc,
  cmd_logs path component, qpeek clone, world-reset rm -rf operator trust,
  slot-create body size unbounded (FastAPI default caps apply).

---
*Prior review (2026-09-26, e765561): refresh of the LLM re-evaluation turn
(model-eval harness + Qwen3.5 9B on vLLM 0.30), 0 BLOCK / 1 WARN fixed (label
merge mixing models) / 2 NOTE (both closed in this pass: revision pin,
appearance_seed crash).*

<!-- REVIEW_META: {"date":"2026-09-26","commit":"6b1af0f","reviewed_up_to":"6b1af0fffaa0a4dc2ca803d297b4893f5fffd496","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":1} -->
