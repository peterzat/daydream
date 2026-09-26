## Review — 2026-09-26c (commit: c726315) — light

**Summary:** Light review of the three pivot-planning commits (c340a60, 09c61fe,
c726315): the new design record `docs/PIVOT.md`, a supersession banner on
`docs/ROADMAP.md`, and a pointer to PIVOT.md in CLAUDE.md (SPEC.md changes are
excluded from the review scope by convention). Docs only; no code or config.
Checked links, code references, factual claims, and secrets.

**Review scope:** Light review (docs-only diff against origin/main). Every code
reference in PIVOT.md was verified against the tree: the `spawn_object`
properties passthrough (`daydream/skills/effects.py:309-311`), talk's effect
allowlist including `spawn_object` (`daydream/verbs.py:118`), `effects_schema`
as documentation only (`daydream/skills/data.py:17-20`), the four dialogue
template variables (`daydream/skills/data.py:360-365`), rules dispatching before
engine handlers (`daydream/verbs.py:429`), and the cited files and archive exist.
Measured figures (engine/test line counts, ~1,270 tests, model-eval scores,
forensic repeat counts) match their sources. Relative links resolve.

**External reviewers:** Skipped (light review).

### Findings

No issues found.

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

---
*Prior review (2026-09-26b, 6b1af0f): refresh of the pre-pivot cleanup commits;
0 BLOCK / 2 WARN fixed (set_property made per-verb opt-in and removed from talk;
the CLAUDE.md effect-API contract updated to match) / 1 NOTE.*

<!-- REVIEW_META: {"date":"2026-09-26","commit":"c726315","reviewed_up_to":"c726315314e59c7f7c0083a1b75c2f62ed26c44b","base":"origin/main","tier":"light","block":0,"warn":0,"note":0} -->
