# SECURITY.md

## Security Review — 2026-09-26 (scope: paths)

**Summary:** Path-scoped audit of the 14 files changed since the last review
(`3fc761a`..`a1522eb`): the `appearance_seed` gate that closed the prior
WARN, the CI-parity test fixture, the model bake-off harness
(`model_eval.py`, its corpus and tests), and the Qwen3.5 9B / vLLM 0.30 swap
(`bin/game`, `bin/vllm-bootstrap`, `config.py`, the retell prompt line, the
sample-capture config snapshots). The prior WARN is resolved at the create
endpoint and the turn adds no new network-facing surface; the harness is an
operator CLI on hermetic temp DBs. Two new NOTEs: the default model now
resolves from a third-party uploader's Hugging Face repo at an unpinned ref,
and the new gate has a second writer through the accepted talk-path
`set_property` risk, where a non-string value takes down `GET /api/slots`
(reproduced). Net: **0 BLOCK / 0 WARN / 3 NOTE.**

### Findings

[NOTE] bin/vllm-bootstrap:104, bin/game:526 (defaults at bin/game:54,
bin/vllm-bootstrap:21, daydream/config.py:78) — the runtime model now
resolves from a single community uploader's Hugging Face repo
(`cyankiwi/Qwen3.5-9B-AWQ-4bit`) at its moving `main` ref, with no revision
pin on either the pre-cache or `vllm serve`.
  Attack vector: whoever controls that account (or compromises it) pushes a
  new revision; the next networked `bin/game vllm-up` or `bin/vllm-bootstrap`
  resolves `main` again and serves it with no review and no bake-off re-run.
  A replaced `chat_template.jinja` or replaced weights then shape every
  runtime generation. The unpinned-ref pattern predates this turn, but the
  previous default came from the model publisher's own org (`Qwen/...`), so
  this change widens who can alter runtime behavior. The blast radius is
  bounded: no `trust_remote_code` anywhere (bin/, daydream/, tools/, the
  operator env files), the cached snapshot is safetensors-only with no Python
  files, and output still passes the JSON, allowlist, and banlist gates,
  except the accepted talk-path `set_property` (next finding).
  Evidence: `snapshot_download("$MODEL")` with no `revision=`;
  `vllm serve "$VLLM_MODEL"` with no `--revision`. The local HF cache holds
  exactly one revision, `156edc4bbeb8d1910ee7be9196bafaf1bc052156`, which is
  what the 2026-09-26 bake-off measured.
  Remediation: pin that revision (a `DAYDREAM_VLLM_MODEL_REVISION` default
  passed to `snapshot_download(..., revision=...)` and to `vllm serve
  --revision ... --tokenizer-revision ...`), and/or launch `vllm serve` with
  `HF_HUB_OFFLINE=1`, since the bootstrap already pre-caches. Record the
  revision in the bake-off doc so a bump becomes a reviewed change.

[NOTE] daydream/images/client.py:262 via daydream/api/slots.py:130 and
daydream/api/ws.py:342 (writer: daydream/skills/effects.py:261) — the new
`appearance_seed` gate covers the create endpoint only. The accepted
talk-path `set_property` (LLM-chosen target, key, and value) can still write
`appearance_seed` on any toon, including another player's, with no length
cap, no banlist pass on `value` (`skills/data.py:290` scans only
text/seed/name/mood), and no type check. A truthy non-string value makes
`cached_portrait_url` raise on `.strip()`, so `GET /api/slots` returns 500
for every session (blocking picker-first entry) and state snapshots fail for
anyone sharing a room with that toon, until the property is repaired in the
DB.
  Attack vector: an authenticated player talks to an NPC with text that
  instructs the model to append `{"kind": "set_property", "target_id":
  "<toon id from GET /api/slots>", "key": "appearance_seed", "value": true}`.
  That text passes the input banlist, and talk's allowlist (`verbs.py:116`)
  admits `set_property`. With a string value, the same path swaps a player's
  portrait prompt for arbitrary unfiltered text. Whether the live 9B model
  follows such an injection was not tested; everything from the dispatched
  effect onward was reproduced deterministically in a temp data dir
  (create 200, `GET /api/slots` 200 before, 500 after).
  Evidence: `_apply_set_property` writes any key and value on any existing
  object; `Toon.from_object` (`toons.py:41`) and `cached_portrait_url` accept
  whatever is stored; `list_slots` and `_toon_card` call it with no guard.
  Remediation: treat a non-string `appearance_seed` as empty at read
  (`Toon.from_object` or `cached_portrait_url`), which removes the
  availability half in one line. For the content half, refuse player-facing
  keys such as `appearance_seed` in LLM-dispatched `set_property`, or include
  string `value`s in the output banlist scan. Both are small installments on
  the v2 `skills-authoring-and-security` item.

[NOTE] daydream/config.py:161-162 — carried forward, re-verified unchanged:
the per-install session secret is written with default permissions and then
chmod'd to 0600, and `~/.config/daydream/` is created with the default mode.
Sub-second first-boot window on a single-user box; practical exposure is
near nil. Remediation unchanged: create the file with
`os.open(..., O_CREAT | O_WRONLY | O_EXCL, 0o600)`, or
`secret_path.touch(mode=0o600)` before writing.

Open items outside this scope (carried forward from the 2026-07-07 review,
not re-verified this run): the CI workflow's mutable action tags and missing
`permissions:` block (`.github/workflows/test.yml`), and the uncapped
per-line command expansion of a WS `input` frame (`daydream/parser.py`).

Traced and cleared this run (not findings):

- **The prior WARN is resolved at its source.** `create_slot` strips the
  seed, caps it at 300 chars, and rejects `safety.first_banned` hits with a
  400 before any toon is created (`slots.py:165-178`);
  `tests/security/test_appearance_seed_gate.py` pins the over-cap,
  banned-word, and at-cap cases. The seed reaches ComfyUI by dict assignment
  into a deep-copied workflow (`images/client.py:196`), so it cannot alter
  workflow structure. Residual: the banlist is a small tone filter, and the
  optional portraits kill switch was not added.
- **The model-eval harness adds no runtime surface.** Nothing in the server
  imports `daydream.model_eval`; its global `litellm.acompletion` wrapper is
  installed only inside its own CLI process. Suites run on temp DBs with
  explicit paths and restore `DAYDREAM_DATA_DIR`; results land under
  `~/data/daydream/model-eval/`, outside git. Every input (label, out dir,
  base URL, override JSON) is an operator CLI argument, and the one
  interpolated SQL literal is a constant world id. The dialogue suite also
  adds a prompt-leak probe.
- **The vLLM launch stays local.** The host default remains `127.0.0.1`; the
  new flags (`--language-model-only`, server-side `enable_thinking=false`)
  add no endpoint exposure, and a stray thinking trace would fail JSON
  parsing closed. `DAYDREAM_VLLM_EXTRA_ARGS` and the venv `PATH` prefix are
  operator-controlled (standing operator-trust risk), and neither env file
  sets extra args. The bootstrap pins `vllm==0.30.0` exactly and moves a
  stale venv aside rather than upgrading in place.
- **Test fixtures tighten isolation.** `_no_real_llm` points unmarked tests
  at a dead loopback port, so the GPU-free tiers can no longer reach a live
  engine; `test_ws.py` pins the grounded parse with a mock. Test credentials
  remain labeled constants.
- **Prompt and snapshot deltas are inert.** The retell rule addition changes
  wording only (validator and authored fallback unchanged); the
  `_vllm_config_snapshot` edits are static strings; the refusal probe now
  exercises the production talk path.
- **Secrets and PII.** No keys or tokens in the scope files, their diffs, or
  the recent history of `bin/game`, `bin/vllm-bootstrap`, `config.py`, and
  `conftest.py`. The parser corpus holds only world ids and names.

### Accepted Risks

Durable register carried forward (trust model: single shared password,
tailnet membership as the outer gate, no per-user roles; loopback is the
admin boundary):

- **LLM-emitted effects take an unscoped, LLM-chosen target id and
  key/value** on the `talk` dialogue path (bound to talk's non-restricted
  allowlist: narrate/set_property/set_mood/spawn_object). Consumers traced
  so far and contained downstream: drift_pools, journal, growth.
  `appearance_seed` is the uncontained consumer, recorded as a NOTE above.
  Rule/growth/clock paths do not share this shape. v2
  `skills-authoring-and-security`.
- **Shared-world mutation: any authed session may drive verbs on any
  in-scope shared object** and repaint rooms while the regen UI is on
  (dev default). Intended single-shared-world co-op design; per-session
  ownership is v2. State-changing POSTs are CSRF-origin-gated; `/ws` is
  Origin-gated and auth-gated.
- **Parser raw player input is not role-separated** before the grounding
  LLM call; output is strictly re-grounded to a closed verb + in-scope id.
- **Tailscale-mode auth is tailnet membership** (`auth.is_authed` returns
  True unconditionally in `tailscale`; the AccessMiddleware CGNAT
  `100.64.0.0/10` + loopback check is the real gate). Cookie
  `https_only=False`; `/status/*` + `/cache/...` session-unauthenticated
  but AccessMiddleware-gated.
- **NPC dialogue / growth prompt-injection via player input**: role-
  separator wrapped, length-capped, input-banlist-checked; LLM output
  structured, validated, and output-banlist-scanned before mutation.
  (Refusal `reason` is narrated without an output-banlist pass in
  `data.py`/`growth.py`; renders through escaped sinks.)
- **Operator-trust world envelopes + `bin/game`**: `world load`/`reset`
  content (verbs/rules/fuses/daemons/growth/drift pools/dialogue),
  `reset`'s `rm -rf`, `.env`/`secrets.env` sourcing, the `0.0.0.0` bind,
  the deprecated `bootstrap_world` LLM path reading `ANTHROPIC_API_KEY`
  (design-time only). None take network input.
- Unbounded slot-create body (size; the prompt-content half was the
  2026-07-07 WARN, gated in `21fed3f`) + liveness-gated claim takeover; missing CSP /
  `X-Content-Type-Options` on the SPA shell (XSS sinks are escaped); event
  queues bounded (256, drop-oldest).

---
*Prior review (2026-07-07, paths, commit `3fc761a`): audit of the v1.0
release turn (42 files, ~15K lines): journal, seed propagation, portraits,
endings and onboarding, the repaint API, and the hardening trio (loopback-only
swap, regen kill switch, delete grace window). Every new LLM surface was
validated before mutation, every new SPA sink escaped, all SQL
parameterized. 0 BLOCK / 1 WARN (the unmoderated `appearance_seed`, since
resolved in `21fed3f`) / 3 NOTE (session-secret write window, CI action
pinning, WS input expansion cap).*

<!-- SECURITY_META: {"date":"2026-09-26","commit":"a1522eba2a846cce6c4fdfb69844ceace7ba90c5","scope":"paths","scanned_files":["bin/game","bin/vllm-bootstrap","daydream/api/slots.py","daydream/config.py","daydream/drift_samples.py","daydream/model_eval.py","daydream/retell.py","daydream/voice_samples.py","tests/conftest.py","tests/drift/test_dialogue_refusal_probe.py","tests/model_eval/corpus.json","tests/security/test_appearance_seed_gate.py","tests/test_model_eval.py","tests/test_ws.py"],"block":0,"warn":0,"note":3} -->
