# SECURITY.md

## Security Review — 2026-09-29 (scope: paths)

**Summary:** Path-scoped review of the twenty-one files named by the caller,
read as their change from the last scan (`d2f7538`) to HEAD `de5e11b`. The
changes are glimpses, the parser's deterministic routes, the margin notes
and the village's glimpse data:
- Glimpses: a name that the scene's prose shows but the hands can't reach
  is answered from an authored line, from the prose itself, or from one
  validated local-model line.
- The parser now handles "look at", "x" and the new take and examine
  aliases without the model.
- The margin drops its two notes.
- The Village of Lost Hours gains authored glimpse data.

These paths add no new finding. The new model surface reads only the
scene's own prose and stays inside the actor's scope; probes of another
dreamer's private thing, a closed container and another dreamer's satchel
never reached it. Its line is validated and told only to the actor. The
open register carries forward: the agent guard's WARN and five NOTEs, all
in files these commits did not touch. One NOTE is amended for a second
route (0 BLOCK / 1 WARN / 5 NOTE).

### Scope and method

- Each scoped file's diff from `d2f7538` to HEAD was read in full, and the
  new `daydream/glimpse.py` was read whole. The code it leans on was read
  too:
  - `objects.in_scope` and `visible_to`
  - `verbs.detail_with_state`, and `verbs._execute_resolved` up to the
    dobj gate
  - `effects._apply_narrate`, and `spawn_object`'s properties passthrough
  - `rules._build_ctx` and the condition evaluator
  - the letter and parcel paths in `daydream/post.py`
  - growth's writes of seeds and descriptions
  - `play._line` and `play._scene`
- A scratchpad probe built the canonical world in a throwaway DB with a
  mocked model. The first dreamer asked for four things that are not
  theirs to see: a second dreamer's `private_to` note in the room, a closed
  iron box's contents, a thing in the second dreamer's satchel, and the
  second dreamer's looks. Each was asked through `glimpse.answer` directly
  and through `parse_line` and `execute_command` (look at, x, take, grab,
  check out). Every answer was `None` or "You don't see ... here", and the
  model was never called. The owner got their own note's sentence.
- Nine adversarial 500-character names ran through `authored`, `seen_in`
  and `parse_line`, each in under 2 ms. They covered runs of articles,
  repeated words, trailing phrases and whitespace, and regex
  metacharacters.
- The scoped tests pass. That is 122 in `test_glimpse`, `test_parser` and
  `test_walkthroughs`, and 19 in headless Chromium (`test_browser_flow`).

### Findings

These paths add no new finding. The findings below are carried forward;
their files are unchanged since `d2f7538`.

[WARN] tools/agent_guard.py:36-38, :267 (with :47, :163-169, :264-266) —
Carried unchanged. It stays open for a session with the operator, because
the guard asks before any change to itself. These get no opinion:
- A recursive search rooted one directory below home. Examples:
  `grep -rn ... ~/.config`, the same search with `rg`, with
  `$HOME/.config` or with a trailing slash, `find ~/.config ... -exec cat
  {} +`, and a search under `~/.claude`. These print the Cloudflare or
  GitHub token.
- `gh auth status -th github.com`, which prints the GitHub token.
  Attack vector: An ordinary or steered search one folder below `~` prints
a live credential into the session and its transcript. For a Bash read,
the hook is the deterministic layer that CLAUDE.md relies on.
  Evidence: `BROAD_ROOTS` matches only exact home-level roots.
`_names_credentials` matches a credential directory as a substring, so a
parent directory never matches. The token pattern needs a literal `-t`.
The full evidence is in the prior entry (`git show 40f18d2:SECURITY.md`).
  Remediation:
- Expand and normalize each argument of a searcher (and of `tar`,
  `zip -r`, `cp -r` and `rsync`). Ask when one is an ancestor of a
  credential directory.
- After `gh auth status`, treat a short-flag cluster holding `t` as
  `--show-token`.
- Deny any command containing `oauth_token`.
- Test each shape.

[NOTE] tools/agent_guard.py:246-255 (carried unchanged) — The raw
gated-verb pass has three gaps. It cuts at the first redirection. It does
not read a list-form `subprocess.run([...])`. And it returns its ask before
the parsed pass's credential denials run. Remediation: drop a redirection
word and its target instead of cutting there. Add `,[]` to the split. Let
a deny win over an ask.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py:200-207; carried
unchanged) — About twenty pushes to a fork pull request from a branch
named `main` fill the one page of runs. A red main then reads "unknown" in
`prod check` and `prod plan`. `ci watch` filters by commit and is
unaffected. Remediation: read main's head sha and that commit's runs, or
page until `limit` push runs are found. Say so when a full page held none.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py:296-297; carried,
amended) — A grown place's description prints unmarked in `play`. The
server also accepts control characters in typed lines and appearance
seeds. This run adds a second route. A look at a name the prose shows
(`look at`, `x`, `examine`) now echoes the scene's sentence as a narrate
line, with no `src` and no player mark. So a sentence of a grown room's
model-written description, or of a grown thing's seed, reaches `play` this
way too. That text already prints on arrival or on examine, so nothing new
is exposed, but the proposed snapshot marker would not cover this route.
Remediation:
- Carry a grown marker in the snapshot and print that description marked.
- Carry the same marker on the narrate lines that echo grown text: a
  grown thing's examine, and `glimpse.answer` when its host was grown
  (`generated_by` starting `plant:`).
- Refuse non-printable characters at the server, as names already are.

[NOTE] daydream/skills/effects.py:347 (carried unchanged) — The
placeholder expander still runs over a letter's body and a dreamer's
looks. It fills only `{dreamers_today}`. The `from_player` flag is a ready
skip condition. BACKLOG `placeholders-over-player-text`. (New dreamer
names now refuse braces, `api/slots.py:184`, so a glimpse's echo of a
sentence naming a dreamer adds nothing here.)

[NOTE] daydream/accounts_cli.py:129-136 (carried unchanged) — Running
`account delete --yes` during a resident's reply leaves that reply and its
`talk:`/`rel:` records behind. `account delete` is not in
`prodctl.STOP_FOR`, and `dialogue.talk` does not re-check the dreamer
after the model call.

### Traced and cleared this run (not findings)

- **Scope.** `glimpse._hosts` (`glimpse.py:102-105`) is `objects.in_scope`
  without toons. It drops things `private_to` someone else (`visible_to`).
  It skips a closed opaque container's contents and other dreamers'
  satchels. It holds no toon, so no one's looks are read. The probe above
  confirmed each.
- **What prose it reads.** `_prose` (`:139-146`) reads a room's description
  and a thing's `seed` with its `state_text`. It never reads
  `examined_text` (where a husk keeps its planter's words), a letter's body
  (`properties.text`), or a dreamer's looks. In the live world, those
  fields have three writers. The loader and dreams write authored text. A
  letter's seed template adds only dreamer names. Growth writes
  model-composed text from a vision phrase, and validates it. So raw player
  words never reach the glimpse model.
- **The model call** (`:257-283`).
  - It runs on the local client under the arbiter, with no key.
  - Its input is that prose, a noun that must be a whole-word phrase of the
    prose (each typed word `re.escape`d), and a closed verb.
  - The line is validated, told only to the actor (`to: "@actor"`), and
    tagged `src: "local"`.
  - The cache is keyed by room and by a hash of noun, verb and sentence.
    Players share it, but it is built only from shared prose, so it
    carries nothing from one dreamer to another.
  - A failed line is not cached, so a player can repeat the call. Calls
    run one at a time per socket, under the 3/s frame bucket, the same
    cost class as `talk`.
  - Every backend failure raises `LLMUnavailable`, and the player reads
    the plain line.
- **The log line** (`:269`) prints only that noun, with `%r`.
- **Authored glimpses.** The loader validates `glimpsed` and fails loudly
  (`format2.py:337-340`, `:410-413`). It checks keys, names, text and verb
  lines, and runs `if` through `validate_condition_list`.
  `conditions_hold` only reads. In the live world only authored paths
  write `glimpsed`. A model can reach `spawn_object`'s properties
  passthrough only on the data-skill paths, which are not live (carried
  register).
- **The parser.** `look at <absent name>` of under four words
  (`parser.py:353`) now takes the deterministic examine instead of the
  model. `x <name>` routes only to a verb that takes a target (`:330`).
  The new take and examine aliases pass through the same executor gates as
  before.
- **The page.** The change only removes the satchel and book notes. What
  remains writes through `textContent`, and the change to `index.html` is
  static markup.
- **Tooling.** The glimpse suite in `model_eval` reads a committed corpus
  and calls the production prompt and validator. `DAYDREAM_GLIMPSE_LLM` is
  a kill switch, on by default, and uses only the local model.

### Player-text scan (CLAUDE.md "Player text is data")

- Dev and prod both ran in this review, and nothing was flagged. Counts,
  the verdict and the high-water marks are in the local instance notes,
  never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The scoped diffs, and the last three commits of `daydream/config.py`,
  hold no key, token or password shape. The world data names only canon
  residents, and the tests use the project's long-standing test dreamer.
  No instance domain, hosting company, operator name or email appears.
- `instance/` and `.claude/settings.local.json` are still ignored.

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
  the operator's user could point it at the tunnel token. Anyone who can do
  that already holds `docker`.
- **The pre-login surface is public** (the door, login, invite redemption,
  static assets). The app and the edge both throttle it.
- **Friends drive shared-world verbs on shared objects** (the co-op
  design).
- **What friends type reaches the local LLM.** Role separation, length
  caps, banlists and strict output validation stand between them.

Accepted in the 2026-09-29 codereview (CODEREVIEW.md):

- **A village thing handed to a dozing dreamer** (`verbs._hand_to_player`,
  the tuck-away branch) waits in their satchel until they rest; a page that
  never returns holds it until `world rest-toon` or `account delete` sends
  it home. Refusing it broke the arc contract (walkthrough players never
  open a socket, so every walkthrough hand-over runs through the dozing
  branch). BACKLOG `dozing-handover-of-village-things`.

Carried register (from prior reviews; still open, not re-flagged):

- LLM-emitted effects take an unscoped, LLM-chosen target id on the
  data-skill paths. Neither path exists in the live Lost Hours world
  (planned for v2).
- Raw parser input is not role-separated. The output is re-grounded to a
  closed verb and an in-scope id.
- NPC dialogue and growth are exposed to prompt injection.
  - Input is wrapped, capped and banlisted, and output is validated before
    any mutation.
  - Refusal `reason` text is narrated without an output-banlist pass,
    through escaped sinks.
- World envelopes, archives and `bin/game` are trusted as the operator's
  own. That covers world load and reset content, `reset`'s `rm -rf`, dev
  `.env` sourcing, the dev `0.0.0.0` bind, and the deprecated
  `bootstrap_world`. None of these takes network input.
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
- Toon names are not unique, and lookalikes are not folded. Moderation
  refuses an ambiguous key, and `/status/who` shows the id and the owner.
  (Since 2026-09-29 a new dreamer's name must be unique under case, spacing
  and compatibility folding; confusable alphabets are still not folded, and
  legacy duplicates stay.)
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one. `tools/agent_guard.py` backs them (since 2026-09-29).
  It is a pattern check, not a boundary: spellings through variables,
  `$'...'`, globs in a verb, interpreter one-liners and the like remain
  (BACKLOG `agent-sessions-without-root`). Its gaps this run are the WARN
  and the first NOTE.
- Player text reaches the agent's context through `bin/game play`: names,
  speech and move lines, and (marked since 2026-09-29) letters and looks.
  The verbs an injected instruction would want stay behind ask rules.

---
*Prior review (2026-09-29, paths, commit `d2f7538`): eleven files. They
covered the fixes for the scan before it (the CI reader and the agent
guard), the server closing a socket whose page has been quiet for 150 s,
and the margin naming the satchel and the book. It found 0 BLOCK / 1 WARN
/ 5 NOTE. Its WARN was that the guard misses recursive searches rooted at
the credential files' parent directories, and a clustered `-th` on
`gh auth status`. That WARN and its guard and CI NOTEs are carried above,
along with the three NOTEs it carried itself. The full entry is at
`git show 40f18d2:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-29","commit":"de5e11b68642316a08bd23f006966943b0b351ff","scope":"paths","scanned_files":["daydream/config.py","daydream/glimpse.py","daydream/llm/format2.py","daydream/model_eval.py","daydream/parser.py","daydream/verbs.py","daydream/version.py","tests/model_eval/glimpse.json","tests/test_browser_flow.py","tests/test_glimpse.py","tests/test_parser.py","web/assets/main.js","web/assets/style.css","web/index.html","worlds/lost-hours.json","worlds/lost-hours/arcs/08-tace-hour.json","worlds/lost-hours/regions/01-clocktower.json","worlds/lost-hours/regions/02-square.json","worlds/lost-hours/regions/03-lane.json","worlds/lost-hours/walkthroughs/tace-hour-past-eleven.json","worlds/lost-hours/walkthroughs/tace-hour-within-reach.json"],"block":0,"warn":1,"note":5} -->
