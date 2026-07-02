## Security Review — 2026-07-02 (scope: paths)

**Summary:** Reviewed the Dreamseeds "grow the world from the inside" turn
(v0.5.0, HEAD `02788f7`): the new `plant` verb, its LLM growth pipeline
(`daydream/growth.py`), the two new world-shaping effects (`spawn_room` /
`link_exit`), the loader's `growth`/`contains` validation, the WS refresh
wiring, the authored dreamseed in `worlds/clockmakers-loft.json`, and the SPA's
plant prompt. The feature adds a NEW attacker-influenced path — a player's free
vision phrase feeds a local-LLM room composition that becomes persistent world
state visible to everyone — so I traced that path end to end. It is well
contained: the phrase is length-capped (120), input-banlist-checked, and
role-separator wrapped before the prompt; the LLM output is strictly validated
(schema windows, ≤2 objects reject-not-truncate, WHIMSY banlist over every text
field, anti-copy) before any mutation; and, critically, the ENGINE (not the LLM)
constructs every effect with engine-picked ids/slug/direction/kind — the model
supplies only text data (title/seed/description/object names), never an effect
kind, target id, direction, or property key. The world-shaping kinds are
correctly gated: `spawn_room`/`link_exit` are excluded from `DEFAULT_KINDS`, so a
data skill or NPC dialogue (both `allowed=None`) cannot emit them, and `data.py`
now advertises `DEFAULT_KINDS` (not `ALLOWED_KINDS`) to the dispatcher LLM.
Client-side, the LLM+player-influenced strings (grown room title/description,
spawned object names) reach the DOM only through `textContent`
(`main.js:120-123`) or the escape-first `linkifyEntities` (`main.js:177-184`,
`584`) — no XSS. The room-id slug is sanitized to `[a-z0-9-]`
(`growth._slugify`) so the `r-<slug>` id is safe in the image-cache path; all new
SQL (`rooms.grown_room_count`, `objects.by_slug`) is parameterized. The
`.gitignore` change correctly keeps the moved design-prompt working copy
(`docs/history/ORIGINAL-PROMPT.md`) untracked (verified: not in `git ls-files`,
never committed). **No secrets** in any scoped file. Net: **0 BLOCK / 0 WARN /
0 NEW NOTE.**

### Findings

No security issues identified in the reviewed scope.

Notes traced and cleared this run (not findings):
- **Growth prompt-injection blast radius is bounded.** A crafted vision phrase
  cannot escape the `<player_input>` wrapper (`safety.wrap_player_input`
  neutralizes case/space-variant close tags), and even a "successful" steer only
  yields a room whose text passes the WHIMSY banlist, fits the length windows,
  and is HTML-escaped on render. Same class as the accepted NPC-dialogue
  injection risk, and strictly more contained (no LLM-chosen effect/id here).
- **Growth is not a resource-exhaustion vector.** `DAYDREAM_GROWTH_MAX_ROOMS`
  (default 12) is checked pre-LLM and again at commit; the shipped world has a
  single quest-earned seed that becomes a `spent` husk (losing the `plant` verb)
  after one plant, so live growth is naturally bounded. LLM-invocation-per-verb
  is the pre-existing accepted "authed session drives verbs" risk, unchanged.
- **No CSP re-flag this run:** the carried missing-CSP NOTE pertains to
  `web/index.html`, which is out of this path scope. It remains in the register
  below; the new DOM sinks reached by grown-room text are `textContent` /
  escape-first, so no reachable XSS regardless.

### Accepted Risks

Durable register carried forward; not re-flagged as findings. Backend items
whose controls live outside the scoped files were not re-verified this pass
except where the Dreamseeds change touches them (noted above).

- **LLM-emitted effects take an unscoped, LLM-chosen target id.** Applies to the
  `talk` dialogue path (`set_property`/`move_object`/`spawn_object` trust the
  effect's target id, bound to the verb's `allowed` subset). NOTE: the new
  `plant`/growth path does NOT share this shape — its effects are
  engine-constructed with engine-picked ids — so growth adds no new instance.
  v2 `skills-authoring-and-security`.
- **Shared-world mutation: any authed tailnet session may drive verbs on any
  in-scope shared object** (now including `plant` on a carried dreamseed).
  Intended single-shared-world design; per-session ownership is v2.
  State-changing POSTs are CSRF-gated; `/ws` is Origin-gated + auth-gated.
- **Tailscale-mode auth is tailnet membership.** `auth.is_authed()` returns True
  in `tailscale` mode; `AccessMiddleware` (CGNAT `100.64.0.0/10` + loopback) is
  the real network gate.
- **NPC dialogue / growth prompt-injection via player input.** Player text is
  role-separator wrapped, length-capped, input-banlist-checked; LLM output is
  structured/validated, not trusted text; output is banlist-scanned before
  mutation. (Data-skill dialogue additionally renders through Jinja
  `SandboxedEnvironment`; the growth prompt is a plain string build, no template
  surface.)
- **Operator-trust, not request-controlled (`bin/game`, `world load`).** World
  envelopes (incl. the authored `growth`/`contains` blocks) are design-time
  operator content, loader-validated fail-loudly (`bootstrap._validate_growth`);
  `world reset`'s `rm -rf`, `.env`/`secrets.env` sourcing, `0.0.0.0` bind. None
  take network input.
- Cookie `https_only=False`; `/status/*` + `/cache/...` session-unauthenticated
  (AccessMiddleware-gated); liveness-gated claim takeover; the deprecated
  `bootstrap_world` LLM path reading `ANTHROPIC_API_KEY` (design-time admin tool,
  never runtime). Missing CSP / `X-Content-Type-Options` on the SPA shell
  (`web/index.html`, out of this scope; XSS sinks are escaped).

---
*Prior review (2026-07-01, paths, commit `94f419a`): re-review of the three live
frontend files after the playtest-fixes commit; traced every XSS sink (all
dynamic values escaped / `textContent` / escape-then-wrap `linkifyEntities`), no
external assets, no secrets. 0 BLOCK / 0 WARN / 1 NOTE (missing CSP on the SPA
shell).*

<!-- SECURITY_META: {"date":"2026-07-02","commit":"02788f7e507d6b2a8a80fb153d0047ddab81aa90","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":[".gitignore","daydream/api/ws.py","daydream/config.py","daydream/growth.py","daydream/llm/bootstrap.py","daydream/rooms.py","daydream/skills/data.py","daydream/skills/effects.py","daydream/verbs.py","daydream/version.py","tests/baselines/growth_compose_cedar_kitchen.golden.json","tests/baselines/growth_compose_mossy_stair.golden.json","tests/baselines/growth_compose_moth_attic.golden.json","tests/drift/test_growth_compose.py","tests/drift/test_parser_grounding.py","tests/test_bootstrap.py","tests/test_effects.py","tests/test_frontend.py","tests/test_growth.py","tests/test_parser.py","tests/test_quest_playthrough.py","tests/test_verbs.py","tests/test_world_integrity.py","tests/test_ws.py","tests/test_ws_grow.py","web/assets/main.js","worlds/clockmakers-loft.json"]} -->
