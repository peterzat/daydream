---
name: invite
description: Invite a friend to the prod village. Mints a single-use two-word invite link for the named person, records who it is for, and drafts a text message to send. Use when the operator types /invite <name>, or asks to invite someone, re-send an invite, or reset a friend's password.
---

# /invite <name>

Mint an invitation to the prod village for one friend (SPEC 2026-09-27
criterion 18; design in docs/GOING-LIVE.md section 4).

## Steps

1. Take the friend's name from the arguments exactly as typed (e.g. "Robin
   Ash"). If none was given, ask for it; do not guess.
2. Check nothing open already exists for that name:
   `bin/game prod invite list`. If one does, say so and ask whether to revoke
   it (`bin/game prod invite revoke <id>`) and mint a fresh one, or re-send
   the old one (its slug cannot be recovered, only revoked and replaced).
3. Mint it:
   `bin/game prod invite create --for "<name>" --json`
   The JSON carries `slug`, `link`, `expires_at`, and `message`.
4. Reply with:
   - the link on its own line
   - the expiry date
   - the drafted message, in a quote block, ready to paste into a text. Offer
     to adjust its tone if the operator wants something more personal.
5. Remind the operator, briefly, only if relevant: the link works once, and
   the village must be awake for the friend to use it
   (`bin/game prod status`; `bin/game prod wake` is ask-first).

## Variants

- **Another instance** (docs/runbooks/instances.md): friends belong to an
  instance. `bin/game prod instance list` shows which is attached;
  `bin/game prod invite create --for "<name>" --json --instance <instance>`
  mints one for a detached instance. Its link works only while that instance
  is attached: say so to the operator.
- **Forgotten password:** `/invite reset <username>` runs
  `bin/game prod invite reset <username> --json` (3-day link; it sets a new
  password and ends the account's other sessions).
- **Dev instead of prod** (testing the flow): `bin/game invite create --for
  "<name>" --json` against the dev server.

## Never

- Never paste the slug anywhere but the reply to the operator (no commits,
  no files, no memory).
- Never create an account for the friend yourself: they choose their own
  username and password when they redeem the link.
- Never grant admin to a friend's account; `account role` is for the operator
  to ask for explicitly.
