# Sleep and wake

The village is often down on purpose: the box is lent to other GPU work, or
under maintenance. Asleep is a normal state, not an outage. Friends who open
the page see the storybook asleep page with the note, how long it has slept,
and "send the Night Warden a note", plus (if signed in on that device in the
last 30 days) their own journal, book and portrait.

## Put it to sleep (lend the GPU, a maintenance window)

```sh
bin/game prod status                                   # who is playing?
bin/game prod sleep --note "lent to a training run until Sunday"
```

`sleep` warns players and waits 60 s (`--grace N` to change), flips the edge
flag to asleep, stops the tunnel, the service and the egress gateway, rests
everyone and writes their journals, syncs keepsakes to the edge, and stops vLLM and ComfyUI so
the GPU is free. `--keep-engines` leaves the engines up (dev can keep using
them). The note is what friends read: short, warm, and true. If the operator
gave none, propose one.

Verify: `bin/game prod check` (expects the asleep answers) and
`nvidia-smi` (the card is free unless `--keep-engines`).

## Wake it

```sh
bin/game prod wake
bin/game prod check
```

`wake` starts the engines if they are down (30-60 s), the egress gateway
(docs/EXTERNAL.md; a failure there is a warning, never a stop), the tunnel,
then the service; waits for health; flips the edge flag to awake. Open tabs reconnect
on their own. If the release is behind HEAD, say so; deploy only if asked.

## A maintenance window on the box (updates, a reboot, disk work)

1. `bin/game prod sleep --note "back in an hour: maintenance"`.
2. Do the work. The operator runs anything that needs root.
3. After a **reboot**, nothing daydream starts by itself except the timers:
   the service and the tunnel are deliberately not enabled at boot, so the
   edge shows friends the asleep page until someone wakes the village.
4. `bin/game prod wake`, then `bin/game prod check`.

## Unplanned: the box went down

Friends see the asleep page without a note, and open tabs show "the dream is
sleeping..." for a minute and then the asleep note, retrying every 30 s. A
deploy's restart also reads as a short unplanned outage and recovers within
seconds. When the box is back: `bin/game prod wake` (it is idempotent), then
`bin/game prod check`. See [incident.md](incident.md) if wake fails.

Reading `bin/game prod status` meanwhile: its edge line leads with what
friends see (`friends see asleep (unplanned: the box does not answer)`); the
flag after it still says awake, because the flag is the intent and an outage
does not change it. After a reboot the jobs read "not run since boot" until
their next run: systemd forgets a unit's last run at boot
(`systemctl list-timers 'daydream-*'` and the backups folder say what ran).

## The flag alone

`bin/game edge sleep "<note>"` and `bin/game edge wake` change only the
public flag, not the box. Use them to put up a note while leaving prod
running (rare), or to fix a flag that `prod sleep`/`wake` could not set
because the Cloudflare API was unreachable (they warn and carry on).
