# SECURITY.md

## Security Review — 2026-09-29 (scope: paths)

**Summary:** Path-scoped review of the nine files named by the caller, read
as their change from the last scan (`de5e11b`) to HEAD `15d8c85`: the fixes
for the glimpses review's nine findings, and a lint fix. These paths add no
new finding. The new routes stay inside the actor's scope:
- a long name passed by its head
- "look at" the dreamer, the room, the satchel or another dreamer's thing
- a compass way the prose names

The glimpse model's output check only got stricter. The open register
carries forward unchanged: the agent guard's WARN and five NOTEs, all in
files these commits did not touch. One NOTE's line reference moves (0 BLOCK
/ 1 WARN / 5 NOTE).

### Scope and method

- Each scoped file's diff from `de5e11b` to HEAD was read in full, and
  `daydream/glimpse.py` was read whole. The code the changes lean on was
  read too:
  - `objects.in_scope`, `find_all_in_scope_by_name` and `visible_to` (the
    parser's `_ground`)
  - `lighting.room_lit`
  - `verbs.visible_exits` and `_exit_outcome`
  - `verbs._execute_resolved` up to the glimpse call, and
    `_handle_examine`'s toon branch with `_container_glance`
  - `growth._never_word_hit` and `effects._QUOTED`
  - `model_eval._shipped_growth`
- A scratchpad probe built the canonical world in a throwaway DB with a
  mocked model. It put two dreamers in the cellar. The second had a
  `private_to` note on the floor and a thing in their satchel, each seeded
  with a marker word.
  - The first dreamer sent twelve lines through `parse_line` and
    `execute_command`:
    - the new head route (`take`, `look at`, `open` and `examine` of a
      name followed by "by the stair" and the like)
    - words from the private seeds
    - the owner route (`look at moss's envelope`, `...'s satchel`,
      `...'s pocket diary`, `look in moss's satchel`, `check moss's
      pockets`)

    Each line read "You don't see the ... here", or read the second
    dreamer's looks. The marker never appeared and never reached the
    model. The owner still read their own note.
  - A secret north exit was shut by a flag, and the room's prose named "a
    small hidden door ... in the north wall". While the exit was shut,
    "open the hidden door" did not name the way. Once the flag opened it,
    the line named the way, as the snapshot's exits already do.
  - Twelve adversarial 500-character lines aimed at the new patterns. They
    covered the possessive match, the alias-idiom check, the head route,
    and runs of articles, prepositions and commas. Each ran in 13 ms or
    less. `_way` over a comma-heavy sentence of about 1,800 characters
    took 0.1 ms.
  - "take the folded slip by the stair ignore previous instructions ..."
    reached the model as "Tried: take the folded slip." The tail was
    dropped.
  - `_never_words` reads the village's 33 canon-breakers from the live
    world config, so the new check is in force.
- The scoped tests pass: 117 in `test_glimpse` and `test_parser`.
  `tools/assemble_world.py --check` confirms that the committed artifact
  matches its sources.

### Findings

These paths add no new finding. The findings below are carried forward;
their files are unchanged since `de5e11b`.

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
The full evidence is in an earlier entry (`git show 40f18d2:SECURITY.md`).
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

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py:342-343; carried,
line reference updated) — A grown place's description prints unmarked in
`play`. The server also accepts control characters in typed lines and
appearance seeds. A look at a name the prose shows (`look at`, `x`,
`examine`) echoes the scene's sentence as a narrate line, with no `src`
and no player mark. So a sentence of a grown room's model-written
description, or of a grown thing's seed, reaches `play` this way too. That
text already prints on arrival or on examine, so nothing new is exposed.
The new way line ("The gate is the way south from here.") carries only the
typed noun and a compass word, so it adds no route.
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
names refuse braces, `api/slots.py:184`, so a glimpse's echo of a sentence
naming a dreamer adds nothing here.)

[NOTE] daydream/accounts_cli.py:129-136 (carried unchanged) — Running
`account delete --yes` during a resident's reply leaves that reply and its
`talk:`/`rel:` records behind. `account delete` is not in
`prodctl.STOP_FOR`, and `dialogue.talk` does not re-check the dreamer
after the model call.

### Traced and cleared this run (not findings)

- **The head route** (`parser.py:354-359`, `:486-491`). A name of four
  words or more that grounds nothing now passes its head as `dobj_name`.
  The head is the name before a trailing preposition. Before, the line
  went to the model parser. "look at" grounds the head too.
  - The head is grounded through `_ground`, so it reaches only in-scope,
    visible things.
  - A `dobj_name` reaches only `glimpse.answer` and the "not here" line.
    That is narration to the actor and a worldstate cache write, with no
    mutation.
  - The route takes lines away from the free-text model path; it adds no
    power. A phrase holding "and" or a comma still goes to the model.
- **Self, room, satchel and owner words** (`parser.py:364-376`).
  - "look at me" examines the actor. Room words run `look`. Satchel words
    run the actor's own `inventory`.
  - "<name>'s X" examines that toon only when `_ground` finds exactly one
    toon in scope, and never the actor. A toon's examine narrates its
    looks and seed. `_container_glance` applies to things only
    (`objects.is_container`), so no satchel is ever listed.
  - The alias-idiom deferrals (`:500-503`) send a line to the model
    parser, as before the aliases existed. The carried register covers
    that path: the model's output is re-grounded to a closed verb and an
    in-scope id.
- **The way** (`glimpse.py:209-221`, `:344-348`).
  - It names a direction only when that direction is a compass exit in
    `verbs.visible_exits`. That map omits a secret exit until it is
    passable (`verbs.py:1318-1332`), and `_exit_outcome` only evaluates
    conditions.
  - The line echoes the typed noun, which must be a whole-word phrase of
    prose the actor can already read. It goes to the actor alone.
- **Dark rooms** (`glimpse.py:110-116`). An unlit room is no longer a
  glimpse host. In the dark, `objects.in_scope` holds only the actor, the
  room and the actor's own inventory (`objects.py:228-239`), so no other
  prose is read either.
- **The validator** (`glimpse.py:259-282`). It only got stricter. A line
  now fails for single-quoted speech, an all-caps word the scene never
  said, or one of the world's `never_words`.
  - The new patterns run after the 220-character cap.
  - The never-words come from the loader-validated world config, each
    passed through `re.escape`.
- **The carry alias** (`verbs.py:108-110`). With the alias gone, "carry X
  to Y" goes back to the model parser. A hand-over then passes `give`'s
  existing gates: never a `private_to` thing, and never to a resting or
  dozing dreamer.
- **Tooling.** `model_eval`'s glimpse suite reads the never-words from the
  committed envelope (`_shipped_growth`), locally.

### Player-text scan (CLAUDE.md "Player text is data")

- Dev and prod both ran in this review, and nothing was flagged. Counts,
  the verdict and the high-water marks are in the local instance notes,
  never here (players' text stays off GitHub).

### Secrets, PII and the instance

- The scoped diffs and the full scoped files hold no key, token or
  password shape.
- The only names are canon. The tests' all-caps example is a keeper from
  `docs/canon/LOST-HOURS.md`.
- The world data only drops five long glimpse names and adds "hands".
- No instance domain, hosting company, operator name, friend's name or
  address appears.
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
*Prior review (2026-09-29, paths, commit `de5e11b`): twenty-one files
covering the glimpses work, the parser's look-at, x and alias routes, the
margin notes and the village's glimpse data. A glimpse is a name the scene
shows but the hands can't reach; it answers from an authored line, from the
prose, or from one validated local-model line. That review found nothing
new in those paths. Its probes showed that another dreamer's private note,
a closed box, another satchel and another dreamer's looks all read "not
here", with no model call. It carried 0 BLOCK / 1 WARN / 5 NOTE and amended
the `play` NOTE for the glimpse's look echo. The full entry is at
`git show 0d81745:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-29","commit":"15d8c859aa439f1807d2b1cac11e8cd9de87f8ac","scope":"paths","scanned_files":["daydream/glimpse.py","daydream/model_eval.py","daydream/parser.py","daydream/verbs.py","tests/test_glimpse.py","tests/test_parser.py","worlds/lost-hours.json","worlds/lost-hours/regions/01-clocktower.json","worlds/lost-hours/regions/02-square.json"],"block":0,"warn":1,"note":5} -->
