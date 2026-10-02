## Review — 2026-10-01f (commit: 62d77ef)

**Summary:** Refresh review of `origin/main..d03a48a` (all files in focus): `prod status` leads its edge line with what friends see and reads a timer job with no run since boot as "not run since boot" (113b1df, from the first reboot of the live system); the door page carries Open Graph and Twitter tags with a 1200x630 card and site icons, `card_image` is a new instance word, `tools/make_link_card.py` makes the card (d03a48a). Tests: short+medium 2791 passed before the fixes, 2792 after (one new test). One /codefix cycle fixed all four WARNs (62d77ef). Security (/security, paths): 0 BLOCK / 0 WARN / 9 NOTE, all carried.

**External reviewers:**
None configured.

**Built-in review:**
`/code-review high`: 8 findings, 8 kept after Step 6 (2 merged into WARNs, 6 NOTEs).

### Findings

[WARN, fixed] (security) daydream/edge.py:227 — `public_status()` catches `URLError`, `OSError` and `ValueError`, but a truncated body raises `http.client.IncompleteRead` (an `HTTPException`, neither of those); `edge_line` (daydream/prodctl.py:904) catches only `EdgeError`/`OSError`, so `prod status`, which now calls `public_status()`, ends in a traceback. (high)
  Evidence: `with urllib.request.urlopen(req, timeout=10) as r: return json.loads(r.read())` / `except (urllib.error.URLError, OSError, ValueError)`; reproduced on loopback by the security pass.
  Suggested fix: also catch `http.client.HTTPException` in `public_status()`, with a test that a truncated read returns None.

[WARN, fixed] (also claude-code) daydream/instance.py:81 — the `card_image` fallback reads the raw, unstripped values and copies the door into the card without the card's own shape: a `.webp` door becomes a `.webp` card (a value `validate` refuses when written directly, and one previews may not render); `"card_image": "  "` beside a custom door skips the fallback and previews with the village's card; `"door_image": "  "` sets the card to the village's door painting. (high)
  Evidence: `if raw.get("door_image") and not raw.get("card_image"): words["card_image"] = words["door_image"]`.
  Suggested fix: decide on the validated values (did the file set a door, did it set a card, after stripping), and fall back to the door only when it matches the card's shape (png/jpg); otherwise keep the default card. Test the webp and whitespace cases.

[WARN, fixed] docs/runbooks/sleep-and-wake.md:58 — says "`systemctl list-timers 'daydream-*'` and the backups folder say what ran", but a timer's LAST can be the time it was installed: on this box the offsite timer shows 2026-09-27 21:55 while its job has never run (no journal entries in any boot). The playbook would lead a reader to the same misreading this change set out to remove. (high)
  Evidence: `systemctl list-timers` LAST for daydream-offsite.timer vs `journalctl -u daydream-offsite.service` empty across boots.
  Suggested fix: point at the backups folder and `journalctl -u daydream-<job>` for what ran, and say a timer's LAST may be its install time.

[WARN, fixed] (also claude-code) tools/make_link_card.py:6 — the module docstring says platforms want "a PNG" and that the icons "are a square crop of the same painting"; the tool writes a JPEG card and icon-32 is the drawn mark (`mark()`). (high)
  Evidence: docstring lines 6-11 vs `card(door).save(args.card, optimize=True, quality=88)` and `icons()` returning `mark(32)`.
  Suggested fix: make the docstring say what the tool writes.

[NOTE] (also claude-code) web/door.html:13 — the preview tags live only on the origin's door: while the village sleeps the Worker answers an invite link with asleep.html (no Open Graph tags) or 503 JSON, so a link sent then unfurls bare, and iMessage keeps that at send time. Send invites while awake; Worker-side tags and a card under `_edge/` would close it (an edge deploy). (medium)

[NOTE] (claude-code) daydream/server.py:240 — markers are replaced one after another, so an instance word containing a later marker (`{{card_url}}` in a lede) is expanded again; pre-existing for the first four markers, and instance words are operator-authored. (low)

[NOTE] (claude-code) daydream/prodcheck.py:168 — "not run since boot" also describes a just-installed timer that has never run (true, but it hints at an earlier run); a job that failed before a reboot reads ok until its next run (as before this change). (low)

[NOTE] (claude-code) daydream/prodctl.py:909 — `prod status` now makes a 10 s-timeout HTTPS probe before the Cloudflare API calls; a slow route stalls status. (low)

[NOTE] (claude-code) tools/make_link_card.py:101 — `icons()` crops a square of the painting's height without checking the painting is that wide; a portrait door pads the icon with black. `card()` refuses tall paintings; `icons()` does not. (low)

[NOTE] (claude-code) tools/make_link_card.py:60 — the shadow is blurred twice (paste source and mask). (low)

[NOTE] web/index.html:8 — the game page's icons are absolute URLs; browsers honor `<base>`, so base-relative would do there and could not fall foul of `img-src 'self'` where `DAYDREAM_PUBLIC_ORIGIN` differs from the host a browser uses. (low)

[NOTE] daydream/server.py:267 — a password-reset link is also `/invite/<slug>`, so it previews as "An invitation to ..." (the GET deliberately never reads the slug). (low)

[NOTE] web/assets/card-village.jpg — nothing ties the committed card to the door painting it was made from; a repainted door leaves a stale card until someone reruns the tool. Crawler access through Cloudflare (bot checks, rate limits) is unverified until the deploy. (low)

### Fixes Applied

- [WARN] (security) daydream/edge.py — `public_status()` also catches `http.client.HTTPException`; a test feeds it a truncated read.
- [WARN] daydream/instance.py — the card follows the door only when the file set a door and no card (stripped) and the door is png/jpg; tests for a webp door, a blank card and a blank door.
- [WARN] docs/runbooks/sleep-and-wake.md — what ran: the backups folder and `journalctl -u daydream-<job>`; a timer's LAST may be its install time.
- [WARN] tools/make_link_card.py — the docstring says the card is a JPEG, icon-180 a crop, icon-32 the drawn mark.

### Accepted Risks

- The guard is a pattern check over command text, not a sandbox: what it does not model (above) is covered by the permission prompts and the operator.
- **A thing with a `home` handed to a DOZING dreamer** waits in their satchel until they rest (BACKLOG `dozing-handover-of-village-things`; also in SECURITY.md).
- Carried from SECURITY.md: LLM-emitted effects take an unscoped, LLM-chosen target id within each verb's allowed subset; stored prompt-injection via captured NPC memory; bootstrap `$MODEL` heredoc; `cmd_logs` path component; qpeek clone; `world reset` rm -rf operator trust; CGNAT hardcoding in tailscale mode; an account deleted mid-reply leaves the reply and its `talk:`/`rel:` records.

---
*Prior review (2026-10-01e, refresh, `2a8d93b`): shrunk screenshots, playthrough purge and the nudity banlist; 0 BLOCK / 0 WARN / 3 NOTE (a corrupt session.json stops purge; "naked" refuses innocent phrases; the content banlist is short and the workflows' negative prompts name no content).*

<!-- REVIEW_META: {"date":"2026-10-01","commit":"62d77ef","reviewed_up_to":"62d77ef0943565ce4b21c6ba0216c5b0d8959105","base":"origin/main","tier":"refresh","block":0,"warn":4,"note":9} -->
