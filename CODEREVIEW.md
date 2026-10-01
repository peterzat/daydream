## Review — 2026-10-01b (commit: 6a934d1)

**Summary:** Refresh review of `origin/main..6a934d1` (all 20 files in focus): the playthrough's gameplay fixes (a beat's chip hides the topic chip whose words it claims, the SPOKE-BELL twin of the first winding, `read` on an unauthored thing, the dreamseed's word count, the reading column's "more" tab and the margin's in-section tabs, WORLD_VERSION 1.14) and the /playthrough harness's honesty (no `text`, no printed labels, orange first-sighting tags, the pace/notes/budget gates, the session record). Tests before: short+medium 2770 passed; after one /codefix cycle: 2770 passed. Security (/security, paths): 0 BLOCK / 0 WARN / 8 NOTE (the last entry's WARN and one NOTE closed).

**External reviewers:**
None configured.

### Findings

[WARN] web/assets/main.js:1842 — the margin's "↓ ask <name>" tab scrolls to a stale row after any re-render: its click handler closes over the `.topic-row` element found when the band was drawn, but `renderTopics` rebuilds every row on each snapshot (`box.innerHTML = ""`, main.js:559) while the band's key (inner ids + sections + inventory count) stays the same, so the buttons are not redrawn. Clicking then measures a detached element (a zero rect) and scrolls the margin to the wrong place.
  Evidence: `go: () => m.scrollTo({ top: yOf(r) - 6, ... })` with `r` from the draw-time `querySelectorAll`; `if (idx.dataset.key !== key)` skips redraws; `renderTopics(others)` runs on every state_snapshot (main.js:358). The browser test clicks before any re-render, so it passes.
  Suggested fix: resolve the row when clicked (find the `#topics .topic-row` whose `.topic-who` names that person, and scroll to it if present), and add a step to the browser test that forces a re-snapshot (or re-renders the topics) between drawing the band and clicking the tab.

[WARN] web/assets/style.css:1012 — `#prose-index` is a full-width band over the reading column's foot (it reuses `.margin-index`, which takes pointer events), so a link on the column's last visible line under the band (the arrival line's "You see: ..." names often sit there) can no longer be clicked: the click lands on the band. The new tab is the only thing in it that should take a click.
  Evidence: `.margin-index { position: absolute; z-index: 5; ... }` with no `pointer-events` rule; `updateProseIndex` sizes the band to the column's full width (`idx.style.width = p.offsetWidth`). In the playthrough's own shot 013 the band sits across the arrival line.
  Suggested fix: `.prose-index { pointer-events: none; } .prose-index .index-tab { pointer-events: auto; }` (and the same for `.margin-index` is reasonable but optional); a browser assertion that `document.elementFromPoint` at a point on the band beside the tab is not the band.

[NOTE] daydream/verbs.py:1321 — `_WRITTEN_RE` matches common phrases in a look ("no sign of wear", "a list of chores"), so a stone so described gets the dream's drifting-words line rather than "nothing written on it". Harmless phrasing; noted only.

[NOTE] daydream/playthrough.py — carried: `run_player` still launches without pinging the session's browser first; the playthrough server still inherits the dev Jev key (documented dev egress).

### Fixes Applied

- [WARN] web/assets/main.js:1842 — the "↓ ask <name>" tab finds that resident's `#topics .topic-row` when clicked and measures it then (nothing happens if the row is gone). The browser test swaps every row for a clone under an unchanged band, scrolls the margin to the top, and clicks.
- [WARN] web/assets/style.css:1012 — `.prose-index` ignores pointer events and only its tab takes them; the browser test asserts a point on the band beside the tab reaches the column. `.margin-index` left as it was.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-10-01, full, `677a903`): the /playthrough skill and harness; 3 WARN fixed in one /codefix cycle (the player's sandbox escape through an importable cwd, `--session-dir` after `--as-player`, the inherited environment), 0 BLOCK.*

<!-- REVIEW_META: {"date":"2026-10-01","commit":"6a934d1","reviewed_up_to":"6a934d10361102581de15fab0c17840a7645dee4","base":"origin/main","tier":"refresh","block":0,"warn":2,"note":2} -->
