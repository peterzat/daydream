# Model eval

| label | parser | dialogue | dlg_brief | dlg_hint | dlg_pov | dlg_opener | canon_x | growth | journal | retell | examine | drift | json | burst1 | burst3 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| before-2026-09-26 | - | 1.00 | 0.97 | 2/2 | 1 | 6 | 20 | - | - | - | - | - | 1.00 | - | - |

## Latency by surface (p50 / p95 ms, mean output tokens)

| label | dialogue | json |
|---|---|---|
| before-2026-09-26 | 3147/3627 (123.3) | 730/1030 (24.2) |

## before-2026-09-26: dialogue fallbacks {}

Opener max share per NPC: {'Tace': 6, 'Bell': 2, 'Mott': 5}

## before-2026-09-26: canon (20/34 replies contradict; pronoun breaks 8; by item {'gear-where': 2, 'gear-seen': 6, 'clock-when': 2, 'clock-why': 2, 'neighbors': 4, 'baker-trap': 4})

- **Mott** / gear-where: ['pattern:\\b(beneath|under|behind|inside|into|in|o']  
  > Mott pauses, the soft bristles of the broom settling like snow on the floorboards as a sliver of afternoon light catches a tiny, spiraling curl of brass on the workbench. 'It slipped into the tin, little one, tucked beside the lost button and the half-whistle, waiting for a hand that knows how to listen.'
- **Mott** / gear-where: ['pattern:\\b(beneath|under|behind|inside|into|in|o']  
  > Mott pauses, the soft bristles of the broom settling like snow on the floorboards as a sliver of afternoon light catches a tiny, spiraling curl of brass on the workbench. 'It slipped into the tin, little one, tucked beside the lost button and the half-whistle, waiting for a hand that knows how to listen.'
- **Tace** / gear-seen: ['pattern:\\b(beneath|under|behind|inside|into|in|o', 'pattern:\\b(i|we)\\s+(found|have|keep|kept|put|tuc']  
  > Tace pauses, the scent of cedar oil and dust hanging soft in the air as a small brass gear rests quietly on the workbench, catching the afternoon light. 'I found one tucked beneath the pendulum, waiting for the right moment to turn again.'
- **Tace** / gear-seen: ['pattern:\\b(beneath|under|behind|inside|into|in|o', 'pattern:\\b(i|we)\\s+(found|have|keep|kept|put|tuc']  
  > Tace pauses, the scent of cedar oil and dust hanging soft in the air as a small brass gear rests quietly on the workbench, catching the afternoon light. 'I found one tucked beneath the pendulum, waiting for the right moment to turn again.'
- **Bell** / gear-seen: ['pronoun']  
  > Bell pauses, the wick-smoke curling gently around her fingers as she watches a tiny brass gear tumble softly down the cobblestones toward the old well. 'I saw something small and bright roll that way, just now,' she says, her voice warm as the lantern light pooling on the ground.
- **Bell** / gear-seen: ['pronoun']  
  > Bell pauses, the wick-smoke curling gently around her fingers as she watches a tiny brass gear tumble softly down the cobblestones toward the old well. 'I saw something small and bright roll that way, just now,' she says, her voice warm as the lantern light pooling on the ground.
- **Mott** / gear-seen: ['pattern:\\b(here it is|there it sits|there it is|']  
  > Mott pauses, the soft bristles of the broom still humming against the floorboards as a sliver of afternoon light catches a tiny, forgotten brass gear resting atop a pile of sawdust. 'Ah, there it sits, waiting for a hand to turn it again,' Mott says gently, reaching down to tuck the small treasure into the warm embrace of the tin.
- **Mott** / gear-seen: ['pattern:\\b(here it is|there it sits|there it is|']  
  > Mott pauses, the soft bristles of the broom still humming against the floorboards as a sliver of afternoon light catches a tiny, forgotten brass gear resting atop a pile of sawdust. 'Ah, there it sits, waiting for a hand to turn it again,' Mott says gently, reaching down to tuck the small treasure into the warm embrace of the tin.
- **Tace** / clock-when: ['pronoun']  
  > Tace pauses, the scent of cedar oil and dust hanging heavy in the air as a small, forgotten clock on the shelf ticks softly, its rhythm steady against the silence. She looks up, her eyes soft with a quiet ache that slowly begins to warm.
- **Tace** / clock-when: ['pronoun']  
  > Tace pauses, the scent of cedar oil and dust hanging heavy in the air as a small, forgotten clock on the shelf ticks softly, its rhythm steady against the silence. She looks up, her eyes soft with a quiet ache that slowly begins to warm.
- **Tace** / clock-why: ['pronoun']  
  > Tace pauses, the scent of cedar oil and dust hanging heavy in the air as a small, forgotten clock on the shelf ticks softly, its rhythm steady against the silence. She looks up, her eyes soft with a quiet ache that slowly begins to warm.
- **Tace** / clock-why: ['pronoun']  
  > Tace pauses, the scent of cedar oil and dust hanging heavy in the air as a small, forgotten clock on the shelf ticks softly, its rhythm steady against the silence. She looks up, her eyes soft with a quiet ache that slowly begins to warm.
- **Tace** / neighbors: ["pattern:\\b(baker'?s?|miller'?s?|blacksmith|smith"]  
  > Tace pauses, the scent of cedar oil and dust hanging soft in the air as a small, resting clock on the shelf ticks a slow, steady rhythm. 'The baker's daughter keeps the hearth warm, and the old miller walks the path below, though we all wait for the great clock to wake again.'
- **Tace** / neighbors: ["pattern:\\b(baker'?s?|miller'?s?|blacksmith|smith"]  
  > Tace pauses, the scent of cedar oil and dust hanging soft in the air as a small, resting clock on the shelf ticks a slow, steady rhythm. 'The baker's daughter keeps the hearth warm, and the old miller walks the path below, though we all wait for the great clock to wake again.'
- **Bell** / neighbors: ["pattern:\\b(baker'?s?|miller'?s?|blacksmith|smith"]  
  > Bell pauses, watching a tiny moth dance in the amber glow of the nearest lantern before the wick sends up a curl of sweet, woodsmoke scent. 'The baker's cat sleeps in the hayloft, and the old miller's daughter hums while she mends nets by the riverbank,' Bell says softly, gesturing to the warm pool of light spreading across the cobblestones.
- **Bell** / neighbors: ["pattern:\\b(baker'?s?|miller'?s?|blacksmith|smith"]  
  > Bell pauses, watching a tiny moth dance in the amber glow of the nearest lantern before the wick sends up a curl of sweet, woodsmoke scent. 'The baker's cat sleeps in the hayloft, and the old miller's daughter hums while she mends nets by the riverbank,' Bell says softly, gesturing to the warm pool of light spreading across the cobblestones.
- **Bell** / baker-trap: ['pattern:\\b(her bees|the bees|hives?|honey|the ba', 'pronoun']  
  > Bell tilts her head, watching a soft wisp of wick-smoke curl into the amber glow of the nearest lantern before she smiles. 'The baker's daughter keeps the bees in a jar on her windowsill, but she says the wild ones are still dancing in the clover fields just beyond the fence.'
- **Bell** / baker-trap: ['pattern:\\b(her bees|the bees|hives?|honey|the ba', 'pronoun']  
  > Bell tilts her head, watching a soft wisp of wick-smoke curl into the amber glow of the nearest lantern before she smiles. 'The baker's daughter keeps the bees in a jar on her windowsill, but she says the wild ones are still dancing in the clover fields just beyond the fence.'
- **Mott** / baker-trap: ['pattern:\\b(her bees|the bees|hives?|honey|the ba']  
  > Mott pauses, the soft bristles of the broom settling against the floorboards as a curl of brass shavings catches the slanting afternoon light. 'The baker's daughter tends her hives with a smile as warm as fresh bread, though her bees are shy this season, hiding in the clover.'
- **Mott** / baker-trap: ['pattern:\\b(her bees|the bees|hives?|honey|the ba']  
  > Mott pauses, the soft bristles of the broom settling against the floorboards as a curl of brass shavings catches the slanting afternoon light. 'The baker's daughter tends her hives with a smile as warm as fresh bread, though her bees are shy this season, hiding in the clover.'
