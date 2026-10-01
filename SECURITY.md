# SECURITY.md

## Security Review — 2026-10-01 (scope: paths)

**Summary:** Path-scoped review of the 33 paths the caller named (70 files,
counting each changed walkthrough), read as their change from the last scan
(`6a934d1`) to HEAD `adc00ff`. That covers six commits:
- `bf12222`: the /codereview fixes to the fold tabs.
- `777b525`: SPA. A wheel over a rail scrolls, the margin band keeps to one
  line, and keepsakes pick their glyph by kind.
- `b2b112d`: parser. A clause is not a name in a list, and `<name>, <words>`
  or words said to someone here are talking to them.
- `71d7f50`: growth. The Ledger keeps each place a player planted.
- `deb1e6c`: the prologue's gear trail. Bell points south, the ferns hide
  the gear, and the one who carries it home sets it in.
- `adc00ff`: playthrough fixes. Answers stay in view, the verb bar keeps to
  one row, plant states its limit, threads count as read only once the
  satchel opens (a new `seen` frame), and a grown room's painting is made
  from its planter's words (`art_seed`). `WORLD_VERSION` is 1.15.

One new WARN: a grown room's painting now leads with the planter's own
words, so the gardener no longer shapes what is painted. A text-only probe
against the served model showed the gardener filtering content that
`art_seed` then restored. Register: 0 BLOCK / 1 WARN / 8 NOTE (the eight
NOTEs carried; their files are unchanged).

### Findings

[WARN] daydream/growth.py:364-377 and :651 (with daydream/rooms.py:38 and daydream/api/ws.py:1199, :1556) — A grown room is now painted from `art_seed`: the planter's phrase first, at weight 1.4, then each colour it names, then the composed `room_seed`. Before `adc00ff` the painting came from `room_seed` alone, which the dream-gardener writes under its rules (no people in the place's things, no violence, no darkness) and the validator checks. Those rules no longer decide what SDXL paints.
  Attack vector: A friend holding an unspent dreamseed plants a vision of up to 120 characters. It passes the tone banlist and the village's canon `never_words`. The banlist's content category is three words (`daydream/llm/safety.py:57-58`), so "nude", "unclothed", "bullet" and "grave" pass. Once the gardener composes a room, the first entry to it renders `art_seed` through SDXL (`ws.py:1199`, `:1556`), with the phrase leading at weight 1.4 (`growth.py:374`). The workflow's negative prompt has no content terms, and nothing checks the image. Every player who enters that room sees the painting. It stays cached, and the art keep holds it for good.
  Evidence: A text-only probe sent six visions of my own (one a benign control) through the production gates, `GROWTH_SYSTEM`, `_user_prompt` and `validate_growth_output` against the served Qwen3.5 9B. It made 6 calls, rendered no image and wrote nothing. All six passed the gates and composed on the first try.
  - For a bather described as unclothed, and for a soldier's helmet with a bullet hole, the composed `room_seed` left the content out.
  - A grave came back as "a freshly dug earth bed".
  - In all three cases, `art_seed` put the player's original words back at the front of the prompt.
  - A nude statue was kept by the gardener too, so `art_seed` only raises its weight.
  Precedent: appearance seeds reach SDXL raw behind a 300-character cap and the same banlist (the fix for the v1.0 WARN). The plant phrase meets that bar. What is new is that this change undoes a filter that was measurably working, for the picture every visitor sees. The code is not in prod yet (`origin/main` is `bf12222`).
  Remediation:
  - Weight only the planter's words that the composition kept: drop any phrase word, colours included, that does not appear in `room_seed`. The gardener's choices then hold, and the A/B'd colour fix stays (the control's "pale blue flower ... between warm stones" survived whole).
  - Add a test where the composition drops a word from the phrase, and assert that `art_seed` omits it.
  - Separately, add an image-content wordlist for every player text that reaches SDXL, appearance seeds included.
  - Add content terms to the negative prompt at the next workflow change. That change busts every room's cache key, so batch it with another one.
  - A painting already made can be replaced with the admin repaint tool's custom prompt.

  Status (2026-10-01, /codereview fix cycle): fixed as the first two remediations say. `art_seed` weights only the phrase's words the composition kept, in the phrase's order, and a colour only when all its words are in `room_seed`; `test_a_grown_rooms_painting_weights_only_what_the_composition_kept` drops "grave" and "red" and asserts neither is weighted. The wordlist and negative-prompt items stay open as NOTE-level follow-ups.

Carried from the last entry (still open; none of their files changed since `6a934d1`):

[NOTE] docs/claude-settings.local.example.json:8-13 — The allow list includes `.venv/bin/python *`, `python3 *`, `node *` and `timeout *`, so interpreter code runs with no prompt. The guard reads code only for literal spellings, so a computed argv or path gets neither a prompt nor a decision. Narrower rules (`.venv/bin/python -m pytest *`) cut the no-prompt paths. They cannot make the guard a boundary while the agent edits and runs repo code (BACKLOG `agent-sessions-without-root`). The template's allow list is unchanged.

[NOTE] daydream/jev/settings.py:33-37, with tools/agent_guard.py:61-62 — The dev Jev key lives in the repo's `.env`, which is not on the guard's credential list. `cat .env` and a Read of it get no decision, while the Cloudflare token's folder is denied. Either move the dev key under `~/.config/daydream/` (already denied) and have `bin/game` load it, or add the repo's `.env` to `CREDENTIAL_PATHS`.

[NOTE] daydream/jev/runtime.py:34 and :61 (called once per free line and once per improvised reply from `daydream/verbs.py` and `daydream/dialogue.py`), with daydream/jev/client.py:34 — There is still no spend ceiling. Since `d09493d` the client pauses for a minute after a timeout, a network error, a 429 or a 5xx. That caps what an outage costs in time, not what a busy player spends. This run's parser change sends more lines to residents (`<name>, <words>`), and so, with a key set, to Jev. Remediation: a daily ceiling from the ledger, past which `enabled()` reads off.

[NOTE] tools/agent_guard.py:451-462 (`_resolve`) — A `cd` into one word of about 50,000 nested braces took 9.6 s at the last measure, past the hook's 5 s timeout, so it gets no decision. The code is unchanged and was not re-measured this run. A time limit inside `main`, or a single-pass brace expansion, would close it.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py) — About twenty pushes to a fork pull request from a branch named `main` fill the one page of runs, and a red main then reads "unknown". Outside this scope; unchanged.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's description prints unmarked in `play`, and so does a look that echoes a sentence from a grown room or thing. The new `read` reply on written prose (`glimpse.py:471`) names a noun from the same prose. The server accepts control characters in typed lines and appearance seeds. `play.py` is unchanged.

[NOTE] daydream/skills/effects.py:356-357 — The placeholder expander still runs over a letter's body and a dreamer's looks. It fills after routing, and a line its actor reads alone may say "you". It still fills only `{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:131-142 — `account delete --yes` run during a resident's reply leaves that reply, its `talk:`/`rel:` records and, with a key set, its Jev decision row (pruned after 30 days). Outside this scope; unchanged.

### Traced and cleared this run (not findings)

- **`art_seed`'s prompt syntax.** `growth.py:371` strips parentheses,
  brackets and colons from the phrase, so it cannot set its own weights or
  name an embedding. Colours come from a fixed list, and `_COLOR` has no
  nested quantifiers. Only engine code and authored data write a room's
  `art_seed`: `plant` is the only verb with `spawn_room`, and
  `set_property` is off talk's allowlist and the data-skill default.
- **The Ledger line** (`growth.py:735-744`, `story.chronicle_note` at
  `story.py:733`).
  - It is built with `str.replace`, never `format`. Dreamer names refuse
    braces at create (`api/slots.py:184`), and the title is validated
    gardener output.
  - It reaches players as escaped narration (`main.js` escapes before it
    links), and the edge's sleep page escapes it too (`edge/src/worker.js:434`).
  - The director's prompt sees the last three chronicle lines
    (`director.py:241`), but its answer is a schema enum of authored ids.
  - The Ledger keeps a deleted dreamer's name. `docs/DATA-LIFECYCLE.md`
    keeps shared history this way, and the door says so.
- **The planter's phrase is retained in more places now.** It was already
  public (the husk quotes it, `growth.py:690`) and stored in `grown.phrase`.
  It now also sits in the painting's recorded prompt and in the keep's
  provenance, which nothing deletes. That matches how portrait provenance
  keeps appearance text.
- **The `seen` frame** (`ws.py:1381`, `saw_threads` at `:1408`) runs after
  the per-frame session re-check, the hold check and the token bucket. It
  marks only the sender's own toon as having heard its own threads.
- **The vocative path** (`parser.py:728`) and `_said_to_someone` (`:1260`)
  ground only toons in scope. `_toon_prefix` uses `_ground` and skips the
  actor, `people_in(scope)` comes from `:1309`, and `execute_command`
  re-checks scope. Lines that now take the talk path reach TypeSafe when a
  key is set. That is within the accepted Jev risk (friends' typed lines to
  residents).
- **The image-prompt endpoint** (`api/rooms.py:62`) now shows `art_seed`. It
  is still admin-only and still behind the regen switch.
- **The SPA.** `text_note` goes in through `createTextNode`. The verb bar
  and fold tabs change only classes and `dataset`. `keepsakeGlyph` returns a
  constant SVG and uses the name only in tests, and the rail's wheel handler
  only scrolls.
- **The village data.**
  - The new effects are `move_object`, `set_flag` and `destroy_object` on
    fixed ids, and `set_pflag` on the actor. `{actor}` comes from existing
    rules.
  - A case-opener without the gear is refused before the after-rule
    destroys the gear (`00-prologue.json:66-82`).
  - `bootstrap._validate_growth` limits `ledger_text` to its three
    placeholders.

### Player-text scan (CLAUDE.md "Player text is data")

- Both scans ran in this review.
  - Prod `--since 0` returned 0 items (nobody since the clean start).
  - Dev `--since 548` returned 63 items: 31 dreamer names, 31 looks and 1
    username. They are the agents' probe dreamers and the operator's dev
    username, with no typed lines, unchanged since the last scan.
- Nothing was flagged, and there were no bursts. Verdict: nobody steering.
- The counts, the verdict and the high-water marks (prod 0, dev 548) are in
  the local instance notes, never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The scoped diff and the whole unpushed range (`bf12222..HEAD`, every
  file), plus `bf12222` itself, hold none of these: a key, a token, a
  private-key block, an email, a box or tailnet address, a home path, the
  operator's name or the instance domain. The only pattern hits were pytest
  decorators.
- The names in tests are fixtures (Wren, Ivo) and village residents.
- `instance/`, `playthroughs/`, `.env` and `.claude/settings.local.json` are
  still ignored, and git tracks nothing under `instance/` or `playthroughs/`.

### Coverage

- All dimensions were reviewed. No dependency manifests or ops files are in
  scope.
- The thirteen Python files were read as diffs from `6a934d1`, with the code
  around each change read in context:
  - `execute_plant`'s gates and commit block, the gardener prompt and its
    validator;
  - the image client's prompt path and the room enqueue;
  - the WS receive loop, `heard.note`, `_toon_prefix`, `interpret` and
    `glimpse.answer`;
  - every chronicle consumer (keepsakes, the director, the dream digest,
    absence, the edge's renderer);
  - dreamer-name validation.
- The SPA files were read as diffs, along with their escaping helpers.
- The test files were read as diffs and run: 350 passed, none skipped,
  Chromium included. `tools/assemble_world.py --check` passes.
- All 38 walkthrough diffs were checked: they add only `cmd` and `expect`
  steps.
- One live probe ran: six text calls to the shared vLLM while prod was
  awake. No image was rendered. The WARN rests on the prompt SDXL receives
  and the workflow's negative prompt, not on a picture.
- Git history: no credential-handling files are in scope. The commits since
  `6a934d1` were checked for key-shaped values.

### Accepted Risks

Accepted by the operator for going live (`docs/GOING-LIVE.md` section 9;
docs/ADMIN-ROOT.md "Security posture", 2026-09-28):

- **The engines run as `peter`.** vLLM (`:8000`) and ComfyUI (`:8188`)
  listen unauthenticated on loopback and run as `peter`, who is in the
  docker group. The prod service user can reach both. Planned fix: a
  separate engines user.
- **Local attackers are best-efforts only.** The box is single-user, and
  `peter` keeps the root-equivalent `docker` group, so a hostile process
  running as the operator is out of scope. The helper, the root-only
  secrets, and the validated and logged root actions are reasonable
  precautions, not a boundary against the operator's own user.
- **Known local-only residual (docs/ADMIN-ROOT.md).** systemd reads a
  release's `.release.env` as root, and releases belong to the operator. So
  the operator's user could point it at the tunnel token or at the
  gateway's key file. Anyone who can do that already holds `docker`.
- **The pre-login surface is public** (the door, login, invite redemption,
  static assets). The app and the edge both throttle it.
- **Friends drive shared-world verbs on shared objects** (the co-op
  design).
- **What friends type reaches the local LLM.** Role separation, length
  caps, banlists and strict output validation stand between them.

Accepted by the operator for Jev (docs/EXTERNAL.md, 2026-09-30; the exact
judge list confirmed in `1768691`):

- **While a key is set, TypeSafe receives** friends' typed lines to
  residents and the judge's context. That context includes other dreamers'
  names, whereabouts and deeds. TypeSafe states no retention, and the door
  does not say so.

Accepted in the 2026-09-29 codereview (CODEREVIEW.md):

- **A village thing handed to a dozing dreamer** (`verbs._hand_to_player`,
  the tuck-away branch) waits in their satchel until they rest. A page that
  never returns holds it until `world rest-toon` or `account delete` sends
  it home. BACKLOG `dozing-handover-of-village-things`.

Carried register (from prior reviews; still open, not re-flagged):

- LLM-emitted effects take an unscoped, LLM-chosen target id on the
  data-skill paths. Neither path exists in the live Lost Hours world
  (planned for v2).
- Raw parser input is not role-separated. The output is re-grounded to a
  closed verb and an in-scope id. One reply may carry up to three commands,
  and each passes the same check.
- NPC dialogue and growth are exposed to prompt injection. Input is
  wrapped, capped and banlisted, and output is validated before any
  mutation. A promise judge (with Jev beside it when a key is set) only
  chooses among drafts or the authored deflection.
- World envelopes, archives, the installer and `bin/game` are trusted as
  the operator's own. That covers world load and reset content, `reset`'s
  `rm -rf`, dev `.env` sourcing, the dev `0.0.0.0` bind, and the deprecated
  `bootstrap_world`.
- Event queues are bounded (256, drop-oldest).
- DNS (127.0.0.53) and AF_UNIX leave the prod sandbox.
- Any local process can reach `127.0.0.1:54322` and set its own
  `X-Daydream-Client-IP`. That moves throttle keys only; the gate still
  applies.
- `gpu.lock` is writable by the service.
- Invite slugs are unsalted sha256 over about 983,000 phrases, so a copy of
  the accounts DB recovers open slugs.
- Strangers can keep invitations paused (a global cap); `invite unblock`
  reopens them.
- On the Workers Free plan, an anonymous client can exhaust the daily
  request quota. The one WAF rule covers the login and invite paths.
- The operator's Cloudflare token is account-wide: Workers Scripts edit
  cannot be scoped to one Worker.
- Toon names are not unique, and lookalikes are not folded. A new
  dreamer's name must be unique under case, spacing and compatibility
  folding; confusable alphabets and legacy duplicates remain.
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one.
  - `tools/agent_guard.py` has backed them since 2026-09-29, and since
    `8eb8107` the hook runs an installed copy that the operator promotes.
    It is a pattern check, not a boundary: spellings through variables,
    `$'...'`, extglob, interpreter one-liners, script files and the like
    remain (BACKLOG `agent-sessions-without-root`). The allow list runs
    interpreters with no prompt (NOTE above).
- Player text reaches the agent's context through `bin/game play` (names,
  speech, moves, gestures; letters and looks marked) and through
  `bin/game jev report --disagreements` (labelled as data). The verbs an
  injected instruction would want stay behind ask rules.

---
*Prior review (2026-10-01, paths, commit `6a934d1`): sixteen files covering `abeeb5a` (the playthrough sandbox fixes), `0ced720` (the playthrough's gameplay fixes, WORLD_VERSION 1.14) and `6a934d1` (the screen-only player with its pace, notes and budget gates). It found nothing new and confirmed the earlier sandbox WARN and environment NOTE fixed. The register stood at 0 BLOCK / 0 WARN / 8 NOTE. The full entry is at `git show bf12222:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-10-01","commit":"adc00ff8048126413ce1f4a8cee46d145188d75e","scope":"paths","scanned_files":["daydream/absence.py","daydream/api/rooms.py","daydream/api/ws.py","daydream/glimpse.py","daydream/growth.py","daydream/heard.py","daydream/llm/bootstrap.py","daydream/parser.py","daydream/prebake.py","daydream/rooms.py","daydream/story.py","daydream/verbs.py","daydream/version.py","tests/baselines/prose_nouns.json","tests/test_absence.py","tests/test_browser_flow.py","tests/test_browser_playtest.py","tests/test_frontend.py","tests/test_glimpse.py","tests/test_growth.py","tests/test_heard.py","tests/test_parser.py","web/assets/main.js","web/assets/style.css","web/index.html","worlds/lost-hours.json","worlds/lost-hours/arcs/00-prologue.json","worlds/lost-hours/cast/bell-mott.json","worlds/lost-hours/cast/tace.json","worlds/lost-hours/regions/01-clocktower.json","worlds/lost-hours/regions/02-square.json","worlds/lost-hours/walkthroughs/bell-dawn-dusk-enough.json","worlds/lost-hours/walkthroughs/bell-dawn-first-dawn.json","worlds/lost-hours/walkthroughs/bell-dawn-second-flask.json","worlds/lost-hours/walkthroughs/bell-dawn-spare-skin.json","worlds/lost-hours/walkthroughs/everyday.json","worlds/lost-hours/walkthroughs/extra-hour-everyones.json","worlds/lost-hours/walkthroughs/extra-hour-hilltop.json","worlds/lost-hours/walkthroughs/extra-hour-sat-down.json","worlds/lost-hours/walkthroughs/keeper-welcome.json","worlds/lost-hours/walkthroughs/latecomer.json","worlds/lost-hours/walkthroughs/letters-dead-letter.json","worlds/lost-hours/walkthroughs/letters-found-letters.json","worlds/lost-hours/walkthroughs/margin-doodling.json","worlds/lost-hours/walkthroughs/margin-finished.json","worlds/lost-hours/walkthroughs/margin-pigeonhole-late.json","worlds/lost-hours/walkthroughs/margin-pigeonhole.json","worlds/lost-hours/walkthroughs/mott-minute-kept-for-later-mat.json","worlds/lost-hours/walkthroughs/mott-minute-kept-for-later.json","worlds/lost-hours/walkthroughs/mott-minute-looked-together.json","worlds/lost-hours/walkthroughs/nell-evening-armchair.json","worlds/lost-hours/walkthroughs/nell-evening-home.json","worlds/lost-hours/walkthroughs/nell-evening-orchard.json","worlds/lost-hours/walkthroughs/pim-home.json","worlds/lost-hours/walkthroughs/pim-jar.json","worlds/lost-hours/walkthroughs/pim-stays.json","worlds/lost-hours/walkthroughs/prologue-together.json","worlds/lost-hours/walkthroughs/prologue.json","worlds/lost-hours/walkthroughs/quill-seed.json","worlds/lost-hours/walkthroughs/rain-wait-river.json","worlds/lost-hours/walkthroughs/rain-wait-stays.json","worlds/lost-hours/walkthroughs/rain-wait-the-end.json","worlds/lost-hours/walkthroughs/summer-downstream.json","worlds/lost-hours/walkthroughs/summer-home.json","worlds/lost-hours/walkthroughs/summer-meadow-late.json","worlds/lost-hours/walkthroughs/summer-meadow.json","worlds/lost-hours/walkthroughs/tace-hour-another-season.json","worlds/lost-hours/walkthroughs/tace-hour-past-eleven.json","worlds/lost-hours/walkthroughs/tace-hour-within-reach.json","worlds/lost-hours/world.json"],"block":0,"warn":1,"note":8} -->
