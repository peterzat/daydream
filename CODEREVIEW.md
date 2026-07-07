## Review — 2026-07-07c (commit: 6c73a8f) — light

**Summary:** Light (docs-only) review of the v1.0 release-bow commit against
origin/main (352375e): README restructured to lead with What-works-today plus
the local-GPU framing, the long-form per-release narratives moved to a new
docs/RELEASES.md (newest first, pre-semver milestones grouped at the end) with
a short Release-history pointer section left behind, CHANGELOG's narrative
pointer updated, MOO linked to Wikipedia, release badge pointed at GitHub
releases. Verified: all relative links in README/CHANGELOG/docs/RELEASES.md/
docs/ROADMAP.md resolve on disk; the three intra-README anchors
(#the-local-gpu-is-a-deliberate-limit, #two-dreamers, #tests) match live
headings; zero repo-wide references remain to the removed #release-notes or
renamed #status anchors; content conservation of the move checked line-by-line
(40 body lines; 3 diffs are the deliberately rewritten preamble and two
relative-link adjustments, nothing lost); no secrets in the diff (pattern hits
are game prose). Short and medium test tiers were green at commit (829/1213),
though a docs-only diff does not require them.

**Review scope:** 3 files, +147/−131, all Markdown. No code or configuration
touched; Steps 3/5/5.5/6.5/7 skipped per light-review tier.

**External reviewers:** Skipped (light review).

### Findings

```
[NOTE] README.md (Release history) / docs/RELEASES.md:7 — "tagged releases
       carry their notes on GitHub" slightly overstates today
  Evidence: the releases page currently holds only v0.1.0; the v1.0.0 release
  is created later this same turn (SPEC c16 prescribes exactly one new
  release), and v0.2.0–v0.6.0 are annotated tags without GitHub release
  entries. The badge's releases/latest link resolves to v0.1.0 until the
  v1.0.0 release lands.
  Suggested fix: none required once the v1.0.0 release exists (it becomes
  Latest and the sentence reads true for the releases shown); optionally
  soften to "releases are tagged on GitHub" in a future docs pass.
```

### Fixes Applied

None.

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
no `onerror` unveil; arbiter `stats()` observability skew; journal write task
held by no reference (fail-open by contract); cached_portrait_url re-parses the
workflow JSON per card (ROADMAP snapshot-perf umbrella); CI actions pinned by
mutable tag, no permissions: block.

---
*Prior review (2026-07-07b, commit 8e74665): refresh review of the CI-parity
test fix (conftest guard pointing non-vllm tests at a dead LLM port), clean.
Before that (2026-07-07, 21fed3f): full-depth review of the whole v1.0 release
turn — 18 commits, 100 files — 0 BLOCK / 2 WARN (both fixed: appearance_seed
gate + tracked ratification evidence) / 5 NOTE, /security over the 42-path
surface, medium tier 1213 green.*

<!-- REVIEW_META: {"date":"2026-07-07","commit":"6c73a8f","reviewed_up_to":"6c73a8ff8a4b6925ca6fbda8f2231aad5d4735d2","base":"origin/main","tier":"light","block":0,"warn":0,"note":1} -->
