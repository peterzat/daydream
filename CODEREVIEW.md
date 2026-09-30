## Review — 2026-09-30e (commit: 1768691)

**Summary:** Light review of `origin/main..1768691`, one docs commit: docs/EXTERNAL.md records that the operator's acceptance covers the judge's exact list (other dreamers' names, whereabouts and deeds), and docs/REFLEXES.md renames "The honest risk" to "Limitations". No links point at the old heading; no secrets or instance data in the prose.

**External reviewers:**
Skipped (light review).

### Findings

No issues found.

### Fixes Applied

None.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-09-30d, full, `d09493d`): the Jev and egress turn; 2 BLOCK (guard heredocs hiding gated verbs, model-eval's judge wrapper) and 7 WARN fixed in one /codefix cycle; eleven NOTEs left open (the full list: `git show a3ce0ef:CODEREVIEW.md`).*

<!-- REVIEW_META: {"date":"2026-09-30","commit":"1768691","reviewed_up_to":"1768691e89c356c0f8ae52da42ce9c446109a1ee","base":"origin/main","tier":"light","block":0,"warn":0,"note":0} -->
