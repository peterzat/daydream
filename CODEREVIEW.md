## Review — 2026-10-01e (commit: 2a8d93b)

**Summary:** Refresh review of `origin/main..2a8d93b` (all files in focus): teardown re-encodes the committed screenshots at 960 px, quality 55 (`share_shot`), `bin/game playthrough purge` deletes finished sessions' villages, the skill commits each run as its own step, the folder README notes the first run's text aid; nudity words join the content banlist (`safety.py`), with tests on the banlist, a composition that keeps them, shrinking and purge. Tests: short+medium 2785 before, 2787 after (two new tests). Security (/security, paths): 0 BLOCK / 0 WARN / 9 NOTE; the teardown NOTE is closed, the painting-content NOTE narrowed.

**External reviewers:**
None configured.

### Findings

[NOTE] daydream/playthrough.py:691 — `purge_finished` reads each landed session's `session.json` with `json.loads`; a corrupt one stops the whole purge with a traceback instead of skipping it. (low)

[NOTE] daydream/llm/safety.py:58 — "naked" is whole-word but not only sexual: "naked branches", "the naked eye" in a letter, a dreamseed phrase or a local line are now refused (a letter or plant with a gentle refusal, a local line with its fallback). No authored text uses the word; accepted as the price of the portrait and painting gate. (medium)

[NOTE] (security) daydream/llm/safety.py:57 — the content banlist is whole-word and short (sexy, nakedness, lingerie, blood pass); neither image workflow's negative prompt names content; `art_seed` can still stitch scattered kept words into one weighted run. Batch negative-prompt content terms with the next workflow change (it repaints every cached image).

### Fixes Applied

None (no BLOCK or WARN).

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-10-01d, refresh, `d57fbe3`): the playthrough reports committed behind a spoiler README; 1 WARN fixed in one /codefix cycle (teardown scrubs the made-up password and the session's home path from every text file it lands), 0 BLOCK.*

<!-- REVIEW_META: {"date":"2026-10-01","commit":"2a8d93b","reviewed_up_to":"2a8d93babc2eca7c4235b9684e97c7a83d8bddf7","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":3} -->
