# The front door and the asleep page (2026-09-27)

The watercolor on the edge Worker's asleep page
(`edge/public/daydream/_edge/night.png`, SPEC 2026-09-27 criterion 15). It was
rendered through the production pipeline (`bin/game image-test`: the room
workflow, SDXL plus the watercolor LoRA, with the WHIMSY suffix), then graded
in-session against WHIMSY.md.

Prompt: "a wide view of a sleeping storybook village under a big pale moon,
moonlit rooftops and a small clock tower, deep indigo night sky with soft
stars, every window dark except one warm glowing window, gentle night mist"
(sampler seed 42).

| Candidate | Verdict |
|---|---|
| seed 7 (first prompt) | rejected: the frame splits into two panels |
| seed 21 (first prompt) | rejected: reads as dusk or day, not a sleeping village |
| seed 3 | good, runner-up: clear night row, golden stars; busier |
| **seed 42** | **chosen**: calm indigo night, one warm window, and a round clock-face window that nods to the village's clock without depending on it |
| seed 88 | rejected: half the sky is blank paper |

Mood, not information: nothing on the page depends on reading the art.

## The front door's village (`web/assets/door-village.png`)

This is the painting a friend sees first, above the sign-in and invitation
card (web/door.html). It needs its own static file because room art sits
behind the sign-in gate. Same pipeline; prompt: "a wide view of a small
storybook village on a gentle hill in soft golden afternoon light, a small
clock tower among cottages with warm windows, a winding lane, soft clouds".

| Candidate | Verdict |
|---|---|
| **seed 42** | **chosen**: warm hillside cottages and a winding lane in golden light; inviting, and it pairs with the night village on the asleep page |
| seed 5 | rejected: pleasant, but the steepled building reads as a church, which is not this village |
