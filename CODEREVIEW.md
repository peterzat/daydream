## Review — 2026-09-30c (commit: bc0fb71)

**Summary:** Refresh review of `791e579..bc0fb71`: the playtest turn (the heard gate ignores model lines, reply ranking by unmet names, glimpse parts with forwarding, refusals by the typed name, part links and cards, the detail lint, the forget-me-not clock) and two /codefix cycles. A fresh reviewer probed the diff with the model mocked (1 BLOCK, 4 WARN, 2 NOTE); my own pass added a WARN; `/security` on the changed paths found 3 WARN (two in the agent guard, one in click-id logging). All BLOCK and WARN fixed. Tests: medium 2531 before, 2537 after cycle 1, 2578 after cycle 2; `ruff check .` clean.

**External reviewers:**
None configured.

### Findings

[BLOCK] daydream/verbs.py:553 (fed by daydream/parser.py:667) — the refusal says back pronouns and loses an authored name's casing.
  Evidence: in the loft, "examine the clocks" then "take it" reads `You can't take the it.`; "take them" reads `You can't take the them.`; "wind mott's tin" reads `You can't wind the mott's tin.` (was `Mott's tin`). `_ground` resolves IT/THEM, the parser passes the raw word as dobj_name, `bare_name` lowercases it, and `f"the {said}"` skips `_the_name`.
  Suggested fix: say back the typed name only when its normalized form equals the thing's name or one of its aliases, using that authored string through `_the_name`; otherwise `_the(dobj)`. The parser should not carry dobj_name for it/them/him/her.

[WARN] daydream/verbs.py:530 — a part's look counts as a refusal, so a chain stops after it.
  Evidence: "examine the forget-me-nots. examine the workbench" gives the part's look then "(So you leave the next part for now.)"; before, the alias's examine returned True and the chain ran on.
  Suggested fix: return True when `glimpse.answer` gave a part's look (its card carries `part`).

[WARN] daydream/verbs.py:492 — forwarding a part's verb to its thing does not update IT.
  Evidence: "examine the workbench", "wind the painted clock", "examine it" examines the workbench.
  Suggested fix: `pronouns.remember_it_name(actor.id, dobj_name)` in the forward block.

[WARN] daydream/play.py:256 (`_resolve`) — `bin/game play click` sends a part's name as its thing's id.
  Evidence: `_resolve(st, "forget-me-nots")` returns `o-resting-clocks`, so an agent's click gets the shelf's card while a browser's gets the part's.
  Suggested fix: when the matched entity has `part`, send `dobj_name` instead of `dobj_id`.

[WARN] daydream/api/ws.py `_handle_command` with daydream/textscan.py:92 — a click frame's `dobj_name` is player text (up to 60 characters) recorded only in `resolved_json`, which the player-text scan does not read (it reads verb and args for command rows).
  Suggested fix: the scan includes a command row's resolved `dobj_name`.

[WARN] daydream/parser.py:596-625 and 751 — two-object verbs, talk and gestures that name a part now reach the model (a regression from the alias's deterministic grounding).
  Evidence (model mocked): "give the forget-me-nots to tace", "put the painted clock on the workbench", "wave at the forget-me-nots", "talk to the painted clock": one model call each, "The dream isn't sure what you mean by that."; before, 0 calls.
  Suggested fix: where these branches find no in-scope match, ground to the thing `glimpse.part_host` names.

[NOTE] daydream/glimpse.py:493 — the loader rejects only a part name equal to its thing's name or alias; a part name that is a trailing word of one ("clock" on the resting clocks) never answers either (the last-words grounding finds the thing first). No such name in the data.
[NOTE] daydream/prose_nouns.py `_PREPS` lists "painted", which is no preposition (it makes "clock painted with ..." head on "clock").

### Cycle 2 findings (from /security; fixed in bc0fb71)

[WARN] (security) tools/agent_guard.py:110-112 (`_RAW_REDIRECTION`, applied at :366), with :130-133 — a regression from aef3abd: the raw pass deletes a redirection's whole double-quoted target, `$( )` and backticks included, before it looks for gated verbs, and the parsed pass never reads inside a quoted target. `echo x > "$(bin/game prod invite create --for Eve)"` gets no decision (17 of SECURITY.md's 28 probes; six asked at d98b73f).
  Suggested fix (SECURITY.md has the exact line): end a raw-pass target at a substitution (a backtick or `$(` ends the double-quoted alternative; a backtick joins the unquoted class's exclusions), keep a plain variable in it; in `_split_commands`, never take a separator as a redirection's target; add the 28 probes to `test_a_redirection_and_its_target_are_read_whole`.

[WARN] (security) tools/agent_guard.py:434-445 (`main`), with :182-183 (`eval` in `_unwrap`) — the guard fails open: a chain of about 500 `eval`s raises RecursionError, the hook exits 1 and the command runs with no decision (a glob-spelled credential read that is denied alone gets through); an 81 KB line takes 4.7 s of the 5 s timeout (`TOKEN_PRINTERS`).
  Suggested fix: wrap `decide` in `main` in `try/except Exception` and print an ask naming the failure; ask past an `eval`/shell nesting depth of 16; ask before any regex for a command above 16 KB. Tests: a 1,000-`eval` chain asks or denies; a 100 KB line decides within the timeout.

  Both guard WARNs: the guard asks the operator before any change to itself, so apply every change to tools/agent_guard.py as ONE Write of the whole file (one approval), not several Edits. Its tests file is not protected.

[WARN] (security) daydream/api/ws.py:1241-1253 (`_handle_command`) — pre-existing: a click frame's `dobj_id` and `iobj_id` are recorded as sent (any string up to 2,000 characters); the dream digest prints them (dream.py:520, :596) and the player-text scan does not read them.
  Suggested fix: record only ids that resolve in the dreamer's scope (reuse `clicked_in_scope`), a fixed marker for the rest; have `textscan.gather` read `dobj_id` and `iobj_id` for command rows. A test: a frame with an unknown id records the marker, and the scan shows what a frame with an in-scope id carries.

[NOTE] (security) tools/agent_guard.py `_resolve` — one word of about 50,000 nested braces (100 KB) still takes 9.6 s, past the hook's 5 s timeout (18.9 s before). A time limit inside `main` or a single-pass brace expansion would close it; asking on every command over 16 KB would turn the committed 96 KB deny test into an ask. Waits for the next guard batch (each guard edit costs the operator an approval).
[NOTE] tools/agent_guard.py — the new redirection pattern asks on a quoted log path with a substitution in it; a plain path stays quiet.
[NOTE] tools/agent_guard.py — over 16 KB, the whole-line token-printer patterns are skipped, so those commands ask rather than deny; the parser's own token deny still applies.

### Fixes Applied

Cycle 1 (/codefix, committed 836ebe1): the BLOCK (refusals repeat only an authored name or alias; a pronoun names the thing), the chain after a part's look, IT after a forwarded verb, `bin/game play click` on a part, the text scan reads a click's `dobj_name`, gestures and two-object lines ground a part to its thing. Declined with reason: "talk to the painted clock" made one model call before this diff too (talk's shortcut grounds only people). Tests: medium 2531 to 2537.

Cycle 2 (/codefix, committed bc0fb71; tools/agent_guard.py as one Write, one approval): the redirection-target WARN (all 28 probes ask), the fail-open WARN (an exception asks; nesting past 16 asks; over 16 KB the slow checks are skipped and it asks, a deny still wins), the click-id WARN (ids kept only in scope; the scan reads ids). Tests: medium 2537 to 2578.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-09-30b, refresh, `aef3abd`): the agent-guard fix and the click-scope NOTE; five guard WARNs and a parser whitespace WARN fixed; three guard NOTEs left open for a session with the operator.*

<!-- REVIEW_META: {"date":"2026-09-30","commit":"bc0fb71","reviewed_up_to":"bc0fb71aea29cf423eb614f524ae6bf86b6fc102","base":"origin/main","tier":"refresh","block":0,"warn":0,"note":5} -->
