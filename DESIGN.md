# DESIGN.md — the interface bible

This file is the durable source of truth for Daydream's **user interface**: how
the running game looks and feels as a surface you act inside. It is the interface
counterpart to [`WHIMSY.md`](WHIMSY.md).

**Division of authority (never blur these):**

- **`WHIMSY.md` owns world tone, voice, and generated imagery** (narration style,
  NPC voice, the watercolor image-gen anchor). What the world *is*.
- **`DESIGN.md` owns the interface** (layout, type, color usage, component
  vocabulary, interaction patterns, the chrome the player touches). How the world
  is *presented*.

Read this before touching `web/` UI or authoring any component CSS. When the two
files could each claim a decision (a color, a mood word), WHIMSY sets the palette
band and DESIGN says how it is applied on screen.

**Canonical visual reference:** [`docs/mockups/01-reading-room/`](docs/mockups/01-reading-room/)
(`index.html` + `backpack.html`, with committed PNG renders). That is the North
Star the live SPA (`web/`) implements. The other three mockups
(`02-diorama`, `03-companion-desk`, `04-dream-pocket`) are retired exploration,
kept for history; do not build from them.

---

## UI anchors

Daydream's interface is **a storybook you act inside**: an open, illustrated leaf
resting on a warm reading table. A player should feel they are turning the pages
of a gentle novel, not operating a dashboard. The same touchstones as WHIMSY
(Spiritfarer, A Short Hike) apply to the chrome: soft, warm, unhurried, legible.

- A **single page** holds the scene, so the eye is never fragmented across panels.
- **The room image is a plate** (a matted, edge-feathered vignette), the way a
  chapter opens on an illustration.
- **Narration is prose**, set in a serif reading column with a drop cap, not a
  scrolling terminal.
- **The scene inventory is marginalia**, hand-noted in the right margin the way a
  reader annotates a book.
- **Actions and exits are quiet footers**, an ink-tab ribbon and a compass rose,
  never a toolbar.

If a change makes the screen feel more like an app and less like a book, it is
moving away from the anchor.

## Color system

The palette is WHIMSY's warm, low-saturation, paper band (cream, sage, dusty
amber). Values live once as tokens (see [Design tokens](#design-tokens-single-source-of-truth)).
Per-role usage:

- `--bg` / `--table`: the table the page rests on (the outermost surface); `--table`
  is the darker cream used behind the leaf.
- `--paper` / `--parch`: page and card surfaces (`--parch` is the warmer parchment
  used for revealed insets like the opened ledger).
- `--ink`: body prose.
- `--sage`: borders, dividers, secondary accent, dialogue-adjacent tint.
- `--sage-deep`: labels, the hand-lettered display type, staged/active emphasis.
- `--amber`: warm highlights (the drop cap, the staged-verb pip, object mentions,
  late-sun glow). The everyday "something is interactive / warm" accent.
- `--quest`: reserved for **errand/quest** emphasis only (a quest keepsake's name,
  the errand marginalia). Used sparingly so it stays meaningful.
- `--line`: hairline rules and card borders.
- `--speaker`: dialogue speaker names.

No pure black, no pure white, no bright red, no neon (inherited from WHIMSY).

## Typography

Three families, each with a job (tokens `--serif` / `--sans` / `--hand`):

- **`--serif` (body):** narration prose, descriptions, plate captions, ledger
  text. The reading voice.
- **`--sans` (labels):** small uppercase, letter-spaced eyebrows and micro-labels
  (`you`, `here with you`, `what you might do`, `ways from here`). The quiet
  annotation voice.
- **`--hand` (display):** the hand-lettered face (Caveat), for chapter titles,
  the wordmark, toon names, keepsake names, and the errand whisper. The storybook
  voice.

**The display face is self-hosted** (`web/assets/fonts/caveat-latin-var.woff2`,
loaded via `@font-face` in `style.css`). The runtime loads **no** Google Fonts or
CDN asset (local-only generation policy). `--hand` carries a system cursive
fallback so the design degrades gracefully if the file is ever missing.

Scale is fluid but anchored: chapter title ~3.3rem, drop cap ~4.4rem, body
~1.04rem/1.66 line-height, labels ~0.6rem with wide tracking. The first paragraph
of room narration takes a **drop cap** in `--amber`.

## Layout & surface

- **The page** is a centered leaf (`max ~844px`) on the `--table` ground, with a
  soft sage/lavender page shadow (`--page-shadow`) and faint paper grain. Two
  fainter leaves peek beneath to suggest a sheaf.
- **The chapter plate** mats the room image with an inset frame and a radial mask
  that melts the watercolor edges into the mat.
- **The body is a two-column grid:** a wide prose column and a narrower marginalia
  column separated by a hairline rule.
- **Revealed insets** (a read ledger, an examined detail) are warmer parchment
  cards, slightly rotated, that appear inline in the prose.
- **Corner radius** is one token (`--radius`); shadows are soft and downward, never
  hard drop-shadows.
- **Responsive:** below a narrow breakpoint the grid collapses to a single readable
  column (marginalia below the prose; ribbon and compass wrap; the plate scales)
  with no horizontal scroll. The page stays usable for reading and tapping on a
  phone.

## Component vocabulary

- **Chapter plate** (`#room-header` / `#room-bg`): matted room image + `painting…`
  overlay + image swap on `room_image_ready`.
- **Title block:** hand-lettered room title + a `--sans` folio subtitle.
- **Drop-cap prose** (`#chat` + `#room-desc`): the narration column; the arrival /
  room description takes the drop cap, and the running event log continues beneath
  as prose (newest last).
- **In-prose affordances** (`.entity-link`): in-scope object mentions become
  soft dotted-underline click targets; the staged/active target is emphasized.
- **Detail / ledger inset** (`.detail-inset`): the storybook expression of
  `examine` / `read`, a revealed parchment card with a tab label.
- **Marginalia groups:** `you` / `here with you` / `you carry` / an optional
  `a small errand`. Chips stay clickable.
- **Ink-tab verb ribbon** (`#verb-bar`): "what you might do" chips; the staged verb
  gets a pip and a one-line hint (`#verb-hint`).
- **Affordance ribbon** (`#skill-bar`): a quieter, italic second row beneath the verb
  ribbon for room-anchored data skills (`wind`, `listen`); present only when the room
  offers them, styled as whispers rather than tabs.
- **Compass footer** (`#exit-bar`): "ways from here", one route per exit.
- **Keepsakes backpack** (`#backpack-panel`): a two-page foldout spread of the
  carried inventory as specimen cards plus empty collection slots.
- **Overlays:** the calm connection/hot-swap wash (`.dream-overlay`) and the
  slot picker (`.slots-panel`), both on the paper aesthetic.

## Interaction patterns

- **Staged verb, then target.** Click a ribbon verb to stage it (pip + hint); the
  scene dims to only valid targets; click one to act. A bare object click defaults
  to `examine`.
- **Reveal, not navigate.** `examine` / `read` open an inline detail inset rather
  than replacing the page or opening a modal.
- **Two-step give/use.** A two-object verb stages the verb, then the direct object
  (which stays lit), then a kind-valid indirect object; both ids go in one command.
- **Dim, don't hide.** Non-applicable targets dim and go inert; they do not vanish,
  so the scene stays stable.
- **Ids are never shown.** No object/toon id appears in any player-visible text,
  ever. Names only.

## Banned patterns

Echoes WHIMSY's bans, for the interface:

- No pixel-art, neon, retrowave, hard edges, or techy-dashboard chrome.
- No pure black / pure white / bright red / harsh shadows.
- **No object or toon ids in player-visible text.**
- **No cloud-loaded runtime assets** (no Google Fonts / CDN links, no remote
  images or scripts). Everything the running game serves is local.
- No modal dialog stacks or toast spam; state changes are calm and inline.

## Design tokens (single source of truth)

These tokens are defined once in `web/assets/style.css` `:root` and mirrored here.
`tests/drift/test_design_tokens.py` (tier_short) extracts both sides and fails on
any divergence. **Edit either side and you must edit the other; DESIGN.md is the
durable source.**

| Token | Value |
|---|---|
| `--bg` | #f6f3ec |
| `--paper` | #fbf9f3 |
| `--ink` | #3a4a44 |
| `--sage` | #5a7a6a |
| `--sage-deep` | #4a6a5a |
| `--amber` | #c8a06e |
| `--line` | #d8d2c2 |
| `--speaker` | #6a8a7a |
| `--table` | #e6ddc8 |
| `--parch` | #f4ecd7 |
| `--quest` | #a97b3e |
| `--serif` | Georgia, "Iowan Old Style", Palatino, "Book Antiqua", serif |
| `--sans` | system-ui, "Segoe UI", "Helvetica Neue", sans-serif |
| `--hand` | "Caveat", "Segoe Print", "Bradley Hand", cursive |
| `--radius` | 12px |
| `--page-shadow` | 0 34px 64px -26px rgba(74,106,90,.42), 0 12px 30px -14px rgba(78,84,120,.20) |

## Drift-check procedure

1. **Always-on token gate.** `bin/game test short` runs
   `tests/drift/test_design_tokens.py`, which asserts the table above equals the
   CSS `:root`. A one-sided edit fails the pre-commit gate with a pointer to both
   sides. This is the mechanical half.
2. **Eyeball pass against the reference.** After a UI change, deploy and compare
   the live Stopped Clock room against `docs/mockups/01-reading-room/`: chapter
   plate shows the room image; drop-cap prose reads as a page; in-prose
   affordances stage and reveal an inset; marginalia shows you / here / carry;
   the verb ribbon stages with a pip and hint; the compass exits navigate; the
   keepsakes backpack foldout opens; picker and overlays intact; no ids anywhere.
   The aesthetic critic is the Claude Code agent reading the rendered UI against
   this file (no API key), escalating to `qpeek` or an in-browser human glance
   when a human eye is wanted (per the generation policy).
