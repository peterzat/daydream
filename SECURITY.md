## Security Review — 2026-07-02 (scope: paths)

**Summary:** Reviewed the five playtest-fix commits after the Dreamseeds turn
(`8b4e865..56a633d`): the third-person NPC dialogue voice + direct memory
binding (`data.py:_dialogue_system`, `verbs._handle_talk` passing `npc`), the
engine-announced open-reveal line, the phrase-hinted growth direction pick,
lowercased composed object names, the new restricted `rename_object` effect
(husk rename), the `object_renamed` WS refresh kind, natural-article refusal
lines, and the SPA stale-art veil + verbatim-narrate glow de-dup. Every
security-relevant dependency outside the scoped paths (`llm/safety.py`,
`api/auth.py`, `api/csrf.py`, `api/access.py`, `parser.py`, `api/slots.py`,
`pyproject.toml`) is byte-identical to the last reviewed commit `02788f7`, so
the previously verified wrapping/banlist/auth posture still holds underneath
this diff. The new mutation surface is correctly gated: `rename_object` joins
`RESTRICTED_KINDS` (excluded from `DEFAULT_KINDS`, declared only by `plant`,
regression-tested in `tests/test_effects.py` and `tests/test_verbs.py`), its
only producer is the engine-constructed husk rename in `growth._commit_growth`
with a fixed name (never LLM- or player-supplied), and `objects.rename` is
parameterized SQL. The dialogue system prompt now interpolates the NPC's
display name; traced and cleared below. Client-side, the new code paths add no
DOM sink: the narrate de-dup compares `dataset.text` and toggles classes, the
bg veil sets `src`/classes on server-controlled URLs, and `object_renamed`
frames fall into `renderEvent`'s non-rendering branch (no ids in player-visible
text). No secrets in the scoped files or in any commit of the range
(per-commit added-line scan); no external assets in `style.css` (self-hosted
font + inline data: URIs); no PII. Net: **0 BLOCK / 0 WARN / 0 NOTE.**

### Findings

No security issues identified in the reviewed scope.

Traced and cleared this run (not findings):

- **NPC-name interpolation into the dialogue system prompt is not a new
  injection surface.** `_dialogue_system(npc_obj.name, ...)` receives either
  the talk dobj (reachable only when the toon has a bound dialogue skill) or
  the legacy `t-<skill>` NPC; both are operator-authored in shipped worlds.
  Player-created toons (`t-slot{N}-{uuid8}` ids, no `dialogue` property) derive
  a skill name that matches nothing, so talk hits the no-dialogue stub with
  zero LLM calls. The only route for a player-chosen name to reach the prompt
  is the already-accepted LLM `set_property` chain (dialogue LLM writes a
  `dialogue` key onto a player toon), and even then the attacker gains nothing
  beyond what their own `args` already steer: output still passes refusal
  parse, output banlist, and talk's effect allowlist.
- **The open-reveal line ("Inside, you find: ...") narrates `contains` entry
  names.** These are operator-authored (or written via the accepted
  LLM-`set_property` risk) and render client-side through the escape-first
  `linkifyEntities`. No reachable XSS.
- **`growth._pick_direction` is a deterministic keyword scan** of a phrase
  already length-capped (120) and input-banlist-checked; it feeds no prompt
  and picks only from free engine directions. The rename effect in the same
  commit block uses the fixed name "spent dreamseed".
- **New `logger.debug` prompt/response lines in `data.py` are dormant** at the
  server's default (INFO) logging config; even if enabled they write player
  chat only to user-scoped runtime logs on this single-operator box, the same
  class as existing INFO logs.
- **Dependency manifests are out of this path scope**; `pyproject.toml` is
  unchanged in the reviewed range (verified).

### Accepted Risks

Durable register carried forward; not re-flagged as findings. Backend items
whose controls live outside the scoped files were not re-verified this pass
except where this diff touches them (noted above).

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
*Prior review (2026-07-02, paths, commit `02788f7`): the Dreamseeds turn —
traced the new player-phrase → local-LLM → persistent-world path end to end
(length cap, banlists, role-separator wrapping, strict schema validation,
engine-constructed effects with engine-picked ids/slug/direction), verified the
`spawn_room`/`link_exit` opt-in gating and the escape-first rendering of grown
text, and confirmed no secrets. 0 BLOCK / 0 WARN / 0 NOTE.*

<!-- SECURITY_META: {"date":"2026-07-02","commit":"56a633d5fb4e5b01e916bae9d176989155a705d2","scope":"paths","block":0,"warn":0,"note":0,"scanned_files":["daydream/api/ws.py","daydream/growth.py","daydream/objects.py","daydream/skills/data.py","daydream/skills/effects.py","daydream/verbs.py","tests/test_dialogue_voice.py","tests/test_effects.py","tests/test_frontend.py","tests/test_growth.py","tests/test_quest_playthrough.py","tests/test_verbs.py","tests/test_ws_grow.py","web/assets/main.js","web/assets/style.css"]} -->
