## Review — 2026-07-07 (commit: 21fed3f)

**Summary:** Full-depth review of the v1.0 release turn: 18 commits, 100 files,
+4372/−1200 against origin/main (the deferred review gate for the whole turn).
Covers the pre-spec groundwork (dead-code cleanup, hardening trio, tests+CI,
oracle harness + walkthrough re-derivation, two zork fidelity data fixes —
sources re-assembled and byte-matched) and the spec's implementation
(endings, onboarding, propagation, portraits, journal+keepsakes, loft batch,
refusal probe, GPU ratification, release engineering). Test baseline: medium
tier 1210 green before and after review, 1213 after the fix loop (the 3 new
gate tests); ruff clean; /security ran over the 42-path changed surface
(0 BLOCK / 1 WARN / 3 NOTE, SECURITY.md updated). Both WARNs fixed and
verified in the fix loop; 0 BLOCK remain.

**Review scope:** Refresh conditions held (prior clean review a78590c is an
ancestor, base origin/main) but the focus set equals the full set — every
changed file is unreviewed since the prior entry, so this is a full-depth
pass on all 100 files.

**External reviewers:** None configured.

### Findings

```
[WARN] daydream/api/slots.py:153 — appearance_seed is an unmoderated, unbounded
       SDXL prompt rendered into shared-visible portraits (from /security)
  Evidence: create_slot validates only non-empty string; portraits (new this
  turn) render the seed through ComfyUI and show the result to co-located
  players and every picker viewer. Asymmetric with this turn's own hardening:
  the growth phrase gets a 120-char cap + input banlist; room repaint got a
  kill switch; this new player-text-to-image surface got neither.
  Suggested fix: in create_slot, cap appearance_seed length (300 chars) and
  reject on safety.first_banned with a 400, mirroring the growth gates.
  Loader-authored NPC seeds are design-time and unaffected. Tests in
  tests/security/.

[WARN] BACKLOG.md:22 / tests/baselines — the criterion-8 and criterion-12
       ratification evidence points at gitignored files
  Evidence: BACKLOG's dialogue-refusal closure cites
  tests/baselines/dialogue_refusal_probe.latest.json as recorded evidence, and
  the journal probe's 5/5 graded run lives in journal_probe.latest.json — but
  .gitignore excludes tests/baselines/*.latest.json (git check-ignore
  confirms; zero latest files tracked). The "recorded evidence" exists only on
  this box.
  Suggested fix: copy both ratification runs to tracked names outside the
  ignore glob (tests/baselines/dialogue_refusal_probe.ratified.json,
  tests/baselines/journal_probe.ratified.json) and point BACKLOG.md's closure
  text at the ratified copies.

[NOTE] daydream/api/slots.py:216 — asyncio.create_task(journal.write_entry(...))
  holds no reference; the docs warn a referenced-nowhere task can be GC'd
  mid-flight. Failure mode is a silently skipped journal entry (fail-open by
  contract) and the pre-existing image-gen enqueue shares the pattern, so this
  is a post-1.0 tidy (a module-level task set), not a fix-now.

[NOTE] daydream/images/client.py:cached_portrait_url — loads and json-parses
  the workflow file per toon card per snapshot (and per slot row). Matches the
  pre-existing per-snapshot room-art pattern but multiplies by co-located toon
  count; ~50µs each, negligible at friend scale. Belongs to ROADMAP's snapshot
  perf umbrella (an mtime-keyed workflow cache).

[NOTE] .github/workflows/test.yml — CI has never run (the plan's interim push
  didn't happen; the release push is its first execution) and python3.12 is
  not installable locally for a pre-check. Watch Actions after the push;
  criterion 16 requires green on the pushed commit. Also from /security:
  actions pinned by mutable tag, no permissions: block — harden opportunistically.

[NOTE] carried from /security: session_secret written before chmod (brief
  first-boot window); parser per-frame command-expansion still uncapped
  (pre-existing, accepted); both in SECURITY.md.
```

### Fixes Applied

- [WARN] daydream/api/slots.py — appearance_seed now capped at 300 chars and
  rejected on the WHIMSY input banlist (400 before any toon is created),
  mirroring the growth-phrase gates; verified by
  tests/security/test_appearance_seed_gate.py (over-cap rejected, banned-word
  rejected, at-cap benign accepted). (from /security)
- [WARN] BACKLOG.md / tests/baselines — both ratification runs committed as
  tracked copies (dialogue_refusal_probe.ratified.json: 0/21 fallbacks;
  journal_probe.ratified.json: the 5/5 graded recaps); BACKLOG's closure text
  cites the tracked copies. git check-ignore confirms both are tracked.

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

### Carried-forward open NOTEs (pre-existing)

Growth refusal `reason` narrated without an output banlist pass; parser raw
input not role-separated; parser per-line command-expansion uncapped; toon-view
N+1 inventory query; admin.py/bootstrap.py `_write_db` non-transactional; no
CSP/`X-Content-Type-Options` on the SPA shell; `main.js:setRoomBackground` has
no `onerror` unveil; arbiter `stats()` observability skew. (The dead
`interpreter.py` NOTE closed this turn — the module was removed.)

---
*Prior review (2026-07-03, commit a78590c): docs-only refresh of
FIRST-FABLE.md; clean. Before that (2026-07-03, 7ca0194): full review of the
GPU headroom + multiplayer hardening + prompt audit + regen-UI turn — 0 BLOCK
/ 0 WARN / 5 NOTE (3 fixed, 2 backlogged).*

<!-- REVIEW_META: {"date":"2026-07-07","commit":"21fed3f","reviewed_up_to":"21fed3f5758dc299f1f4a8508b16609e765bb389","base":"origin/main","tier":"full","block":0,"warn":2,"note":5} -->
