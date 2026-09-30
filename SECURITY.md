# SECURITY.md

## Security Review — 2026-09-30 (scope: paths)

**Summary:** Path-scoped review of the 15 files the caller named, read as
their change from the last scan (`a7cdb15`) to HEAD `d98b73f`. That covers
the review fixes in `4aeb1e9` and the agent-guard rework in `d98b73f`. Every
open item in these files is resolved: the tea-cup WARN, the agent-guard
WARN, and two NOTEs. There is one new WARN: the parser's chain splits
backtrack super-linearly, so one invited player's typed lines can keep the
server's event loop busy. There is one new NOTE: the guard fails open when
it raises. The register is now 0 BLOCK / 1 WARN / 5 NOTE.

### Scope and method

- Each scoped file's diff from `a7cdb15` to `d98b73f` was read in full.
  `tools/agent_guard.py` was read whole. So was the code the changes lean
  on:
  - `verbs._resolve_in_scope` and `objects.in_scope`
  - the WS receive loop and `_handle_input`
  - `parser.parse_line` and `_segments`
  - the dreamer-create throttle in `api/slots.py`
- `tests/test_agent_guard.py` and `tests/test_fragments_pronouns.py` pass
  (128 tests). `tools/assemble_world.py --check` confirms that the
  committed artifact matches its sources.
- The chain-split patterns were timed on lines of up to 500 characters (the
  socket's cap). They were timed before and after 4aeb1e9, and again with
  whitespace collapsed.

### Findings

[WARN] daydream/parser.py:156 (`_THEN_SPLIT`, changed in 4aeb1e9), with
:64 (`_AND_JOIN`, present since 5c61c88) — Both chain-split patterns
backtrack super-linearly on a line that holds a long run of whitespace.
`_segments` (:319-324) runs them on every typed line, synchronously, on the
server's one event loop. Nothing collapses whitespace first: the receive
loop only caps the length (`daydream/api/ws.py:1345-1351`), and
`parse_line` only strips the ends (:233).
  Attack vector: Any invited player sends typed lines of up to 500
characters (`ws.MAX_INPUT_CHARS`) that are mostly whitespace. Each line
costs about 0.38 s of event-loop CPU before any model call. The socket
admits a burst of 12 lines, then 3 a second (`ws.py:1258-1259`). That is
enough for one player to keep the loop saturated. While it lasts, every
other player's frames, broadcasts and HTTP requests wait.
  Evidence (best of three runs on this box):
- `_THEN_SPLIT.split` took 4.3 ms at 125 characters, 34 ms at 250 and
  265 ms at 500, which is cubic growth. The pattern before 4aeb1e9 took
  0.9 ms at 500.
- `_AND_JOIN.split` took 112 ms at 500. The previous scan timed lines
  without long whitespace runs and missed it.
- With whitespace runs collapsed to single spaces, both took under 0.01 ms.
  Remediation:
- Collapse whitespace runs to one space at the top of `parse_line`, after
  `strip()`, or in `_handle_input` after the length cap. `inputs.record`
  keeps the raw line either way.
- Alternatively, rewrite both patterns so that no two adjacent quantifiers
  can match the same whitespace.
- Add a tier_short test: a 500-character line with a long whitespace run
  parses in a few milliseconds.

[NOTE] tools/agent_guard.py:394-405 — `main()` catches only a malformed
payload. If `decide()` raises, the hook exits 1, which Claude Code treats as
a non-blocking error: the tool call proceeds with no opinion from the
guard. Since d98b73f, `decide` holds the raw pass's ask until the end
(:338-348, :391), so that a later deny can win. As a result, an exception in
the parsed pass now also discards an ask already found. Before d98b73f, that
ask was returned at once.
  Attack vector: Defense in depth only. A command would have to make the
guard raise, and the ask rules in settings still apply. The guard is a
pattern check, not a boundary (Accepted Risks).
  Remediation: In `main`, wrap `decide` in `try/except Exception` and print
an `ask` that names the guard's failure, so that the guard fails closed.
Add a test where `decide` raises and the hook still asks.

Resolved since the last entry (verified this run):

- **[WARN] Umber's cup** (worlds/lost-hours/world.json:693-694;
  cast/others.json:418-470).
  - The pour and the `tea` topic are now gated by the `UMBER-CUP` player
    flag, the way the clock and the seed are.
  - A dreamer gets one cup. Later pours are drunk by the stair and spawn
    nothing.
  - A new dreamer starts without the flag, but a player can make at most
    six dreamers a day (`daydream/api/slots.py:212`). That keeps the cups
    to a handful per account per day.
  - The engine cap is BACKLOG `repeated-things-caps`. Cups poured in prod
    before the gate stay (a CODEREVIEW NOTE).
- **[NOTE] A clicked id became IT before any scope check.**
  - `clicked_in_scope` (`daydream/api/ws.py:1046-1052`, used at
    :1364-1365) keeps only string ids that resolve through
    `verbs._resolve_in_scope`.
  - That check goes through `objects.in_scope` and `visible_to`, so
    another dreamer's private thing never becomes IT.
  - Covered by `test_a_click_names_it_only_inside_scope` and
    `test_a_click_frames_ids_that_are_not_strings_are_ignored`.
- **[WARN] The agent guard's searches one folder below home, and gh's
  short-flag bundle.**
  - A searcher, archiver or copier rooted at a folder that holds a
    credential now asks. Its roots are expanded and normalized, and the
    working directory is followed through `cd`.
  - A credential path spelled another way is resolved and denied, both for
    Bash arguments and for Read and Write paths.
  - `gh auth status` with `t` in a short-flag bundle is denied, as is any
    command naming `oauth_token`.
  - Covered by `test_folders_that_hold_credentials` and
    `test_a_credential_path_spelled_another_way_is_not_read`. The guard
    remains a pattern check (Accepted Risks).
- **[NOTE] The guard's raw pass.**
  - `_raw_words` drops only a redirection and its target, and it splits on
    list brackets and commas.
  - A deny anywhere in a command beats an ask.
  - Covered by `test_the_raw_pass_reads_past_redirections_and_lists`.

The findings below are carried forward. Their files are unchanged, or
outside this scope.

[NOTE] daydream/ci.py:49-61 (with daydream/prodcheck.py:200-207) — About
twenty pushes to a fork pull request from a branch named `main` fill the one
page of runs. A red main then reads "unknown" in `prod check` and
`prod plan`. Remediation: read main's head sha and that commit's runs, or
page until `limit` push runs are found.

[NOTE] daydream/play.py:84-85 (with daydream/glimpse.py) — A grown place's
description prints unmarked in `play`. So does a look that echoes a
sentence from a grown room or a grown thing. The server accepts control
characters in typed lines and appearance seeds. `glimpse.py` changed only
in `exit_named`, so nothing here has changed. Remediation: carry a grown
marker in the snapshot and on those narrate lines, and refuse non-printable
characters at the server.

[NOTE] daydream/skills/effects.py:347 — The placeholder expander still runs
over a letter's body and a dreamer's looks. It fills only
`{dreamers_today}`. BACKLOG `placeholders-over-player-text`.

[NOTE] daydream/accounts_cli.py:129-136 — Running `account delete --yes`
during a resident's reply leaves that reply and its `talk:`/`rel:` records
behind. The stale-beat branch newly added to `dialogue.talk` (:754-761) can
await one more judge call, which makes this window a little longer on that
branch.

### Traced and cleared this run (not findings)

- **Chains** (`ws.py:791-809`, `parser.py:276-280`, `:1207`). The stop now
  compares segments, and its notice is fixed text. Referents are remembered
  per segment, from grounded ids only.
- **Untrusted JSON** (`parser.py:358`, `:1173-1177`). Non-string model
  fields and click ids are now ignored instead of raising.
- **Names taken from a line** (`_typed_target`, `_gesture_fast_path`).
  - Such a name reaches only in-scope grounding, `absent.elsewhere`,
    authored glimpses, or the model's grounded call.
  - It is told only to the actor.
  - `_HOW` and the "for" cut are linear on 500-character lines.
- **The absent answer** (`absent.py:35-38`) now places only toons that are
  somewhere, and only if they are players or residents with a voice or a
  schedule. That narrows what it discloses. In gestures, a resting dreamer
  reads as absent (`gestures.py:149-152`, `verbs.py:1670-1672`).
- **The promise guard's stale-beat branch** (`dialogue.py:754-761`).
  - The judge returns one enum verdict.
  - A failed draft yields the authored deflection, so no model text is
    shown unjudged there.
  - The narrowed `_COMMITS` reads model drafts only.
- **Ways by name** (`glimpse.exit_named(exact=)`, `parser.py:521-534`). The
  match is tighter, and a move still goes only through
  `verbs.visible_exits`, so a shut secret exit stays shut.
- **World data.**
  - The new content is authored narration, the flag gate, and glimpse
    validation for rooms with exit names (`format2.py:350-351`).
  - `assemble_world --check` matches.

### Player-text scan (CLAUDE.md "Player text is data")

- Prod and dev both ran in this review. Nothing was flagged, and neither
  had new typed lines. The counts, the verdict and the high-water marks are
  in the local instance notes, never here (players' text stays off
  GitHub).

### Secrets, PII and the instance

- The scoped files, and the guard's last three commits, hold no key, token
  or private-key shape. The only long-string hits were test names and
  comment rules.
- The only names are canon residents. No email, operator name, instance
  domain or box address appears. The guard derives home from `~` and
  hardcodes no username.
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
  the tuck-away branch) waits in their satchel until they rest. A page that
  never returns holds it until `world rest-toon` or `account delete` sends
  it home. Refusing the hand-over broke the arc contract: walkthrough
  players never open a socket, so every walkthrough hand-over runs through
  the dozing branch. BACKLOG `dozing-handover-of-village-things`.

Carried register (from prior reviews; still open, not re-flagged):

- LLM-emitted effects take an unscoped, LLM-chosen target id on the
  data-skill paths. Neither path exists in the live Lost Hours world
  (planned for v2).
- Raw parser input is not role-separated. The output is re-grounded to a
  closed verb and an in-scope id. One reply may carry up to three commands,
  and each passes the same check. A target name the model gives reaches
  only glimpses and "not here", told to the actor.
- NPC dialogue and growth are exposed to prompt injection.
  - Input is wrapped, capped and banlisted, and output is validated before
    any mutation.
  - Refusal `reason` text is narrated without an output-banlist pass,
    through escaped sinks.
  - Every titled place, grown ones included, is in each resident's prompt.
  - A promise judge reads the drafts and the player's words. Its output is
    one enum verdict per draft and only chooses among the drafts or the
    authored deflection.
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
- Toon names are not unique, and lookalikes are not folded.
  - Moderation refuses an ambiguous key, and `/status/who` shows the id and
    the owner.
  - Since 2026-09-29, a new dreamer's name must be unique under case,
    spacing and compatibility folding.
  - Confusable alphabets are still not folded, and legacy duplicates stay.
- Supply chain: the prod lock pins versions but not hashes, and CI actions
  use tags.
- The standing prod grant's `ask` rules are text patterns, so a quoted word
  may slip past one.
  - `tools/agent_guard.py` has backed them since 2026-09-29. It is a
    pattern check, not a boundary: spellings through variables, `$'...'`,
    globs, interpreter one-liners and the like remain (BACKLOG
    `agent-sessions-without-root`).
  - The WARN and NOTE carried against it are resolved this run. The
    fail-closed NOTE above is new.
- Player text reaches the agent's context through `bin/game play`: names,
  speech and move lines, and, marked since 2026-09-29, letters and looks.
  Gesture lines carry dreamer names the same way. The verbs an injected
  instruction would want stay behind ask rules.

---
*Prior review (2026-09-30, paths, commit `a7cdb15`): 36 files covering the
"Reflexes and few dead ends" spec and the v2 hook installer. It found one
new WARN (Umber's cup could be multiplied without bound) and one new NOTE
(a clicked id became IT before any scope check). It carried
0 BLOCK / 2 WARN / 6 NOTE. The full entry is at
`git show d98b73f:SECURITY.md`.*

<!-- SECURITY_META: {"date":"2026-09-30","commit":"d98b73f6330fc90bae76a4ac245658be5c13825b","scope":"paths","scanned_files":["daydream/absent.py","daydream/api/ws.py","daydream/dialogue.py","daydream/gestures.py","daydream/glimpse.py","daydream/llm/format2.py","daydream/meta.py","daydream/parser.py","daydream/verbs.py","tests/test_agent_guard.py","tests/test_fragments_pronouns.py","tools/agent_guard.py","worlds/lost-hours.json","worlds/lost-hours/cast/others.json","worlds/lost-hours/world.json"],"block":0,"warn":1,"note":5} -->
