## Review — 2026-09-30f (commit: 068a34c)

**Summary:** Refresh review of `origin/main..068a34c`: Bell's "who came through today" speaks to the asker (`trace.dreamers_today_clause` takes a listener; `story._tell` and `effects._apply_narrate` pass the actor when the line is theirs alone; a clause opening a sentence or quote is capitalized), `jev report`'s p95 by nearest rank, and REFLEXES.md's verbatim note of Jev's first prod decision. Tests before: short 2055, medium 2747 passed; after one /codefix cycle: short 2056, medium 2748 passed. Security (/security, paths): 0 BLOCK / 0 WARN / 9 NOTE (one new, raised to a WARN below and fixed).

**External reviewers:**
None configured.

### Findings

[WARN] daydream/story.py:234 — `_tell` fills `{dreamers_today}` before its second-person routing, so a line opening "You ..." (a beat, arrival or storylet with no explicit recipient) reaches the actor alone yet names them in the third person.
  Evidence: `expand_placeholders(... listener=actor_id if recipient is not None and recipient == actor_id else None)` runs while `recipient` is still None for such a line; `effects.second_person_recipient(line, actor_id)` sets it only afterwards. `effects._apply_narrate` routes first and fills after, and commit e5863f9's message promises the second-person case.
  Suggested fix: in `_tell`, compute the second-person recipient on the unfilled line first (as `_apply_narrate` does), then fill with the listener; add a test with a "You ..." line in a topic or beat without `to`.

[WARN] daydream/trace.py:173 — `dreamers_today()` is left with no callers: the clause now reads `_dreamers_today()` directly, and nothing else in daydream/, tests/ or tools/ calls the list form.
  Evidence: `git grep "dreamers_today("` finds only the definition and `_dreamers_today` uses.
  Suggested fix: drop the wrapper (or rename `_dreamers_today` to `dreamers_today` returning the pairs).

[WARN] daydream/model_eval.py:1281 — `main()` pops the Jev key so a model-eval run measures the local path, but the run's first `import litellm` (in `_install_recorders`, and `daydream/llm/client.py`) happens later with `LITELLM_MODE` unset, and litellm then runs `load_dotenv()` (litellm/__init__.py:19), putting the key back from the repo's `.env`: Jev is on for the whole run (spend, and a local comparison partly scored on Jev's answers). Found by /security 2026-09-30f as a NOTE; raised here because the code states the opposite.
  Evidence: `import daydream.model_eval` leaves `litellm` out of `sys.modules` (checked), so no earlier import already consumed `.env`. `tests/test_model_eval.py:204` cannot see it: it stubs the run and conftest sets `LITELLM_MODE=PRODUCTION`.
  Suggested fix: `os.environ["LITELLM_MODE"] = "PRODUCTION"` in `main()` before the pops (bin/game already loads `.env` into the environment, so nothing else is lost); in the test, unset `LITELLM_MODE` (monkeypatch.delenv) and assert main() sets it, or import litellm in a subprocess and assert the key stays absent.

[NOTE] daydream/trace.py:219 — a clause that opens a sentence is capitalized as a whole, so a dreamer whose name is lowercase ("moss") reads "Moss" there. The page links names case-insensitively (`linkifyEntities`), so only the typography changes.

### Fixes Applied

- [WARN] daydream/story.py:234 — `_tell` routes the line (second person) on the unfilled text, then fills with the listener, as `_apply_narrate` does; test `test_a_you_line_told_to_the_actor_alone_says_you`.
- [WARN] daydream/trace.py:173 — the caller-less `dreamers_today()` wrapper removed.
- [WARN] daydream/model_eval.py:1281 — `main()` sets `LITELLM_MODE=PRODUCTION` before dropping the Jev keys; the test clears `LITELLM_MODE` and asserts main() sets it.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-09-30e, light, `1768691`): one docs commit (EXTERNAL.md's accepted judge list, REFLEXES "Limitations"); no findings.*

<!-- REVIEW_META: {"date":"2026-09-30","commit":"068a34c","reviewed_up_to":"068a34ca19c7","base":"origin/main","tier":"refresh","block":0,"warn":3,"note":1} -->
