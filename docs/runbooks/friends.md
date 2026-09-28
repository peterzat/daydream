# Friends: invites, sign-in, moderation

Everyone plays with an account; accounts come only from invites. Admin power
lives in the shell, never in a browser.

## Invite someone

`/invite <name>` in a Claude Code session (the skill), or:

```sh
bin/game prod invite list                          # nothing open for them already?
bin/game prod invite create --for "Robin Ash"      # a single-use two-word link, 14 days
```

The village must be awake for them to use it. The link works once. The
drafted message says who the Night Warden is; send it yourself (a text).

## "I can't sign in"

| Symptom | Do |
|---|---|
| Forgot the password | `bin/game prod invite reset <username>` (prompts: it mints a set-a-new-password link, 3 days) |
| "too many tries; wait a few minutes" | Per-address (10) and per-username (5) failures in 15 minutes; it clears itself. |
| "invitations are resting" | Strangers' guesses hit the global cap; `bin/game prod invite unblock` |
| The invite says it can't be used | Used, expired or revoked: `invite list`, `invite revoke <id>`, then a fresh `invite create` |
| Signed in but bounced to the door | The session was revoked, disabled, or is 180+ days old: sign in again |
| "you're dreaming in another window" | Another tab or device of the same account has the toon, and this tab has stopped retrying: reload this tab, or press enter in "your dreamer" here, to take it back |

## Accounts

```sh
bin/game prod account list
bin/game prod account sessions <username> [--revoke]    # end every session of theirs
bin/game prod account disable <username>                # the moderation stop
bin/game prod account enable <username>
bin/game prod account role <username> admin             # prompts; admin = repaint, status, several toons
```

## Moderation

Disabling an account is the stop: it ends their sessions and the next frame
refuses them. To act on a toon:

```sh
bin/game prod world rest-toon <toon id>      # send it to rest (keeps it)
bin/game prod world delete-toon <toon id>    # remove it; what it carried stays in its room
```

Name a toon by its **id** (from `bin/game prod status` or the admin
`/status/who`). Names are not unique, and a player can name a toon after
another toon's id: an ambiguous key is refused with every match listed. A
rest from the shell does not close the player's open socket; disable the
account when you need them out now.

Never mend the great clock with the operator's own account.
