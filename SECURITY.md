## Security Review — 2026-07-02 (scope: paths)

**Summary:** Path-scoped audit of `tests/test_growth.py` (596 lines, the
Dreamseeds per-rule unit suite) at commit `60001de`. The file is pytest-only
code with no runtime surface: the fixture isolates all state to a per-test
tmp DB (`db.init_live(path=tmp_path / "test.db")` with `close_db` +
`reset_subscribers` teardown; `monkeypatch.setenv` auto-reverts), the single
raw SQL statement (`_grown_rooms`, lines 94-98) is a static string with no
interpolation, the LLM is `AsyncMock`ed so no key and no network is touched
(consistent with the no-API-key policy), and the full git history of the file
(4 commits, per-commit patch scan) contains no secret-like strings. No PII;
all names are fictional world entities. Substantively the suite is itself the
regression guard for the growth pipeline's security posture: it pins
no-ids-or-directions-in-prompt (line 202), role-separator wrapping of the
player phrase (line 212), phrase cap and input banlist, output schema
reject-not-truncate windows, output banlist, anti-copy, the refusal hatch,
cap gates both pre-LLM and at commit, mid-await race re-checks, and the
universal seed-preserved / nothing-mutated postcondition
(`_assert_nothing_grew`). Net: **0 BLOCK / 0 WARN / 0 NOTE.**

### Findings

No security issues identified in the reviewed scope.

Traced and cleared this run (not findings):

- **The test-local `PLANT_ALLOWED` mirror (lines 23-27) cannot mask an
  allowlist regression.** It is currently byte-identical to the production
  `verbs.VERBS["plant"].allowed_effects` (`daydream/verbs.py:132-134`), and
  the load-bearing contract (restricted kinds `spawn_room`/`link_exit`/
  `rename_object` reachable via `plant` only, intersecting no other verb's
  allowlist) is independently pinned against the real `verbs.VERBS` in
  `tests/test_verbs.py:73-76`. A drifted mirror would weaken only this
  suite's isolation fidelity, not the runtime gate.
- **Tests weaken no production control.** `DAYDREAM_GROWTH_MAX_ROOMS`
  overrides are per-test monkeypatch scope; world mutations land on the
  throwaway tmp DB; nothing touches `~/data/daydream/` or a live server.

### Accepted Risks

Durable register carried forward; not re-flagged as findings. Controls live
outside this scope and were not re-verified this pass.

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** Applies to
  the `talk` dialogue path (`set_property`/`move_object`/`spawn_object` trust
  the effect's target id, bound to the verb's `allowed` subset). The
  `plant`/growth path does NOT share this shape (engine-constructed effects,
  engine-picked ids), and `rename_object` is unreachable from any LLM-driven
  dispatch. v2 `skills-authoring-and-security`.
- **Shared-world mutation: any authed tailnet session may drive verbs on any
  in-scope shared object.** Intended single-shared-world design; per-session
  ownership is v2. State-changing POSTs are CSRF-gated; `/ws` is Origin-gated
  + auth-gated.
- **Tailscale-mode auth is tailnet membership.** `auth.is_authed()` returns
  True in `tailscale` mode; `AccessMiddleware` (CGNAT `100.64.0.0/10` +
  loopback) is the real network gate.
- **NPC dialogue / growth prompt-injection via player input.** Player text is
  role-separator wrapped, length-capped, input-banlist-checked; LLM output is
  structured/validated, not trusted text; output is banlist-scanned before
  mutation. (The LLM refusal `reason` is narrated without an output banlist
  pass, in both `data.py` and `growth.py`; consistent pre-existing behavior,
  noted in CODEREVIEW.md for a future shared tightening; the text renders
  through escaped sinks.)
- **Operator-trust, not request-controlled (`bin/game`, `world load`).** World
  envelopes (incl. authored `growth`/`contains` blocks) are design-time
  operator content, loader-validated fail-loudly; `world reset`'s `rm -rf`,
  `.env`/`secrets.env` sourcing, `0.0.0.0` bind. None take network input.
- Cookie `https_only=False`; `/status/*` + `/cache/...`
  session-unauthenticated (AccessMiddleware-gated); liveness-gated claim
  takeover; unbounded slot-create body (incl. toon name length) + event
  queues; the deprecated `bootstrap_world` LLM path reading
  `ANTHROPIC_API_KEY` (design-time admin tool, never runtime). Missing CSP /
  `X-Content-Type-Options` on the SPA shell (`web/index.html`, out of this
  scope; XSS sinks are escaped).

---
*Prior review (2026-07-02, paths, commit `56a633d`): the five playtest-fix
commits (third-person dialogue voice, open-reveal line, phrase-hinted
direction, restricted `rename_object` husk rename, SPA veil/glow); verified
the new mutation surface stayed gated and all auth/banlist dependencies
byte-identical to the previously reviewed commit; 0 BLOCK / 0 WARN / 0 NOTE.*

<!-- SECURITY_META: {"date":"2026-07-02","commit":"60001de72f8092c555c92d7d3eb2eee6949af335","scope":"paths","scanned_files":["tests/test_growth.py"],"block":0,"warn":0,"note":0} -->
