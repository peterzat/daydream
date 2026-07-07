## Spec — 2026-07-07 — daydream v1.0: the release turn

**Goal:** Complete a credible v1.0 and cut the release. Four flagship features
close the product's own promises (the world grows from the inside as a loop,
the cast has painted faces, the book remembers your story, endings are
visible and newcomers are welcomed); the shipped loft world absorbs the
authored batch behind one WORLD_VERSION bump; the turn's already-landed
groundwork (dead-code removal, guest hardening, CI, the oracle ratification)
is verified under this contract; and the repo's public release identity
catches up to its code: version constant, license, changelog, refreshed
docs, backfilled tags, and a v1.0.0 GitHub release.

### Acceptance Criteria

- [x] **1. Dreamseeds propagate (the growing-world loop).** A seed whose
  authored `growth.propagation` block (`chance` in (0,1], `max_generation`
  1–4, optional `seed_text`) survives fail-loud loader validation can, on a
  successful plant, yield a fresh dreamseed inside the newly grown room:
  spawned in the same commit batch, inheriting the parent's growth
  boundaries with `generation` incremented and provenance
  `propagation:<parent-seed-id>`, plantable end-to-end (a WS test grows
  twice in a row). The roll is seeded-deterministic; it is suppressed at
  `generation >= max_generation` and when the world is at the grown-room
  cap; every existing failure path still leaves the parent seed intact and
  the world unmutated. No new LLM surface: propagation adds zero prompts
  and zero model calls, and deterministic tests run under a mocked LLM.

- [x] **2. The cast has faces (NPC/toon portraits).** A toon with a
  non-empty appearance seed lazily gets a watercolor portrait through the
  existing persistent-image pipeline as `target_kind='toon'`: rendered
  under the arbiter's exclusive image slot, cached and recorded in
  `generated_assets`, served from the existing `/cache/...` route.
  Adding portraits changes no existing room-art cache key (a regression
  test proves a room target's path and dedup key are byte-identical).
  Snapshots carry `image_url` on toon cards (self included) when the
  portrait is cached; a paint completion event triggers the same
  re-snapshot flow room art uses, so co-located players see faces appear
  live. `GET /api/slots` exposes cached-only portrait thumbnails (the
  picker never triggers renders). The SPA shows portraits in the scene
  margin and the picker, with a quiet placeholder until painted;
  ComfyUI-down degrades to the placeholder without blocking play.

- [x] **3. The book remembers (dream journal).** Leaving the dream
  (`POST /api/session/leave`) triggers a background journal write for the
  released toon: one local-LLM call over the toon's own recent events
  produces a 2–3 sentence past-tense second-person entry, validated
  (refusal parse, length window, banlist) and appended to a FIFO-capped
  per-toon journal with sequence idempotency (leaving twice with no new
  events writes nothing). The leave endpoint always succeeds regardless of
  LLM outcome; LLM-down or validation failure skips the entry silently.
  Snapshots carry the journal for the controlled toon only — never a
  co-located player's. Returning to a toon with journal entries shows a
  "previously in your dream" beat once per connection.
  `DAYDREAM_JOURNAL_ENABLED` is the kill switch; the test suite forces it
  off and journal tests mock the LLM.

- [x] **4. Keepsakes are real.** The backpack's collection page renders
  actual content: journal entries and carried items enriched with their
  examined/authored detail (a new inventory-card field), replacing the
  hardcoded decorative-empty slots. Frontend contract tests cover the
  collection rendering and the inventory detail field.

- [x] **5. Winning is visible.** A `win` effect reaches every connected
  player in the world (not just the firing room) carrying score and rank;
  the SPA presents a dismissible "The End" storybook page; the world keeps
  running after dismissal; late joiners and reconnects see a quiet
  ended-marker derived from snapshot status that can reopen the page. All
  ending text is world-agnostic (the no-world-literals gate stays green).

- [x] **6. Newcomers are welcomed.** A first-visit "how to dream" leaf in
  the Reading Room idiom explains speaking, clicking verbs and objects,
  exits, the satchel, and leaving/picking a toon; it shows once per
  browser, is reachable anytime from a persistent affordance, and never
  blocks input. Pure client feature; frontend contract tests.

- [ ] **7. The loft learns the batch (WORLD_VERSION 1.4 + one reset).**
  `worlds/clockmakers-loft.json` gains: per-NPC authored drift pools for
  Tace/Bell/Mott (validated by the loader; the drift loop prefers a toon's
  authored pools over the generic fallback, closing the bunny-keyed-pools
  gap), the dreamseed's `propagation` config, and an authored one-time
  first-planting chapter-close beat (narrated in the room and written to
  the planter's journal; explicitly not a `win`). `WORLD_VERSION` bumps to
  1.4; one archive-then-reset installs the batch as the live world.

- [x] **8. The benign-refusal mystery is resolved.** A repeatable probe
  runs greeting-class inputs through live loft NPC dialogue at least 20
  times, attributing every refusal to its layer (input banlist, refusal
  parse, output banlist, truncation). The root cause is fixed, or the
  observed rate is ratified with recorded evidence; either way a
  regression case lands in `tests/security/` and the BACKLOG entry closes.

- [ ] **9. The v0.6 gate closes (operator playtest).** The prior spec's
  criterion 15 human half is done: the operator plays the live-swapped
  Zork world in a browser, findings are recorded and fixed or backlogged,
  and the v0.6 spec line is checked in the prior-spec record. (The machine
  half already replays 350/Master Adventurer over WS on the final
  envelope, `--verify` green.)

- [x] **10. The turn's groundwork stands verified.** In-repo evidence for
  what landed ahead of this spec: the legacy core-skill/interpreter path
  is gone and the registry serves data skills only (contract tests); the
  hardening cluster is covered by `tests/security/` (regen kill switch
  gating endpoints 404 + snapshot flag + SPA binding, delete grace window
  vs transient disconnects, loopback-only world swap); the tree is
  ruff-clean and `.github/workflows/test.yml` runs lint + the GPU-free
  medium tier on 3.10 and 3.12; the archive→cascade-delete→restore drill
  diffs the full world fingerprint; the dfrotz differential oracle is
  GREEN against real Zork I (v0.6 criterion 14 checked, ratification
  recorded in BACKLOG).

- [x] **11. Generation stays local.** Every new runtime generation this
  turn (journal, portraits, propagation) runs only on the local engines
  behind the GPU arbiter. No cloud LLM key exists anywhere in runtime,
  tooling, or CI (grep-verifiable); new prompt surfaces are documented in
  `docs/prompts.md`; deterministic tests keep their zero-LLM spies.

- [x] **12. The long tier ratifies the generative work (GPU batch, server
  down).** `bin/game test long` is green: new portrait dHash anchors are
  golden-ratified, the journal quality probe runs against real vLLM, and
  existing goldens (growth compose, parser, retell, images, arbiter)
  hold. `bin/game review` regenerates the contact sheet including
  portraits; the agent grades renders and journal samples against
  WHIMSY.md in-session and records verdicts. Honest-default rule: any
  flagship whose local-model quality misses the bar ships with its flag
  defaulted off and the finding recorded (flag-local-limits pact).

- [x] **13. The app knows its version.** `APP_VERSION = "1.0.0"` lives in
  `daydream/version.py`, is served by `GET /status/build`, and matches
  `pyproject.toml` (a drift-guard test fails on mismatch). WORLD_VERSION
  (1.4) remains the separate world-content stamp and both are documented.

- [x] **14. Licensed and attributed.** An MIT `LICENSE` sits at the root;
  README carries a Zork I provenance note (mechanics and identity derive
  from the MIT-licensed historical ZIL source; all prose freshly authored;
  no story file, dump, or original prose committed — consistent with the
  repo's actual contents).

- [x] **15. The docs tell the v1.0 truth.** `CHANGELOG.md` records
  v0.1.0 → v1.0.0 (extracted from README's release notes, which become a
  pointer plus narrative); README is overhauled (v1.0 status, the four
  flagships, CI + license badges, current test counts, ROADMAP pointer);
  TESTING.md's dated header reflects the current suite; WHIMSY.md loses
  the stale "lands in v1" line and gains the portrait prompt suffix
  (mirrored with a drift test like the room suffix); CLAUDE.md rolls
  forward (new features, flags, version story); BACKLOG is groomed
  (entries shipped this turn annotated closed); `docs/ROADMAP.md` exists
  and holds the post-1.0 direction (v1.x polish vs v2 shared-world),
  absorbing this spec's out-of-scope list.

- [ ] **16. v1.0.0 ships.** Annotated tags `v0.3.0`–`v0.6.0` exist at
  their historical release-notes commits and `v1.0.0` at the release
  commit; the pre-push gate passes (/codereview with /security, marker
  written); `git push --follow-tags` lands and GitHub Actions is green on
  the pushed commit; the GitHub repo carries a description and topics;
  exactly one new GitHub release (`v1.0.0`, marked Latest) summarizes the
  full v1.0 state; `bin/game deploy` leaves the live server reporting
  app 1.0.0 at `/status/build`.

### Context

Adopted from the user-approved plan
(`~/.claude/plans/consider-this-whole-repo-unified-knuth.md`): all four
flagships in, both v0.6 operator gates closed in-turn, MIT license,
backfill tags + a single v1.0.0 release. Read that plan for the
increment-ordered design (file-level seams, risk register, release
runbook).

Constraints the implementer must respect:

- **Generation policy (CLAUDE.md) is absolute.** Runtime and tooling call
  only local engines; design-time heavy authoring (loft drift pools,
  first-planting beat, ROADMAP, release notes) is done by the agent
  in-session and baked into data. A feature that seems to want a cloud
  call gets pre-baked or rethought.
- **The loft envelope is the pre-bake surface.** Authored content changes
  batch into criterion 7's single MINOR bump and one reset (resets destroy
  live toons/grown rooms — archive first).
- **GPU discipline.** tier_long and `bin/game review` run with the game
  server down (the arbiter is in-process; two processes can OOM the
  20 GB card). Batch GPU work; note server cycles in one line.
- **zat.env practices carried in:** small committable increments with
  tests in the same increment; the medium tier green at every commit;
  never modify tests to accommodate a regression; verification quality is
  the ceiling — prefer ratify-once-then-mechanical proxies (goldens,
  drift tests, contract greps) over repeated eyeballing, and batch the
  irreducible human looks into the review sheet and one playtest
  (minimize-eyeballs).
- **Walkthrough turn-alignment:** any further Zork dataset edit upstream
  of the fights re-derives the fight phase (the k-search pattern from the
  oracle turn); prefer post-fight edits.
- Prior-spec C15 (criterion 9 here) needs the operator; everything else
  is agent-executable. The release step (criterion 16) is the one
  explicitly-authorized push of this turn.

### Status at session close (2026-07-07, pushed ahead of the playtests)

13/16 checked above. Implementation, verification, docs, and the review
gate are done: /codereview + /security covered the full turn (0 BLOCK /
2 WARN both fixed / 5 NOTE; marker written), medium tier 1213 green,
tier_long green end-to-end including the dfrotz oracle, portrait +
journal quality ratified in-session. On the operator's instruction the
push happened AHEAD of the playtests: `main` and the backfilled annotated
tags v0.3.0–v0.6.0 are on origin as of this note, which also fired
GitHub Actions' first-ever run. The final turn closes the three open
criteria, in this order:

- **Criterion 9 (Zork playtest).** The live world is Zork on the
  reviewed build. Play it in a browser; fix or backlog findings; check
  this box and the v0.6 spec's C15 line.
- **Criterion 7 (the reset).** The 1.4 batch is authored, committed, and
  load-verified, and the live Zork world is archived
  (`archives/w-zork1-20260707-140643.tar.gz`). Run `bin/game world reset
  --yes` (operator-gated destructive step) to install the loft as the
  live world, then check this box. Follow with the Inc-13 loft playtest
  (plant → propagated child seed → replant; portraits in margin +
  picker; leave → journal → return beat; help leaf; endings via a
  temporary zork swap).
- **Criterion 16 (v1.0.0 ships).** Still owed after the early push: any
  playtest fix round (new commits invalidate the marker → refresh
  /codereview, a cheap 0-BLOCK refresh), `git tag -a v1.0.0 -m "daydream
  v1.0.0"` at the final release commit, `git push origin main
  --follow-tags`, GitHub Actions green on that commit, `gh repo edit`
  description + topics, exactly ONE GitHub release (`gh release create
  v1.0.0 --title "daydream v1.0.0" --notes-file docs/releases/v1.0.0.md
  --latest`), and `bin/game deploy` leaving `/status/build` reporting
  app 1.0.0.

FIRST-FABLE.md still owes its append-only Part-4 addenda (the oracle run
grade and this turn's playtest/verdict), co-written with the operator at
close-out.

---
*Prior spec (2026-07-02): Zork I as pure world data on Zork-agnostic
platform primitives — closed 15/16 in-turn (walkthrough 350 deterministic
+ live over WS; differential oracle GREEN against real Zork I on
2026-07-07); its criterion 15 browser-playtest half carries forward as
criterion 9 above.*

<!-- SPEC_META: {"date":"2026-07-07","title":"daydream v1.0: the release turn","criteria_total":16,"criteria_met":13} -->
