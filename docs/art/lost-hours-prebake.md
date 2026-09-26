# The Village of Lost Hours: art pre-bake verdicts

SPEC 2026-09-26 criterion 20. Every room background and portrait was
rendered through the production pipeline (`bin/game prebake`: SDXL base +
the watercolor LoRA, the room and portrait workflows, the WHIMSY suffixes)
and graded by the agent against WHIMSY.md by looking at each render. First
pass 2026-09-26 on a scratch copy (so weak seeds could be fixed in the world
data before the live reset).

**Live pre-bake must reuse the sampler seeds below** (the cache key folds in
the seed TEXT and the workflow, not the KSampler seed):

```sh
bin/game prebake --reseed r-clocktower=5,t-quill=11
```

## Rooms (17)

| Room | Verdict | Notes |
|---|---|---|
| r-clocktower | pass (2nd rewrite + sampler seed 5) | first render split into two abstract panels; seed rewritten as a single interior (stairwell toward the clock face, the oak case, the lectern); the default sampler seed still split it, seed 5 gives one warm arched interior with the stair |
| r-loft | pass | the strongest: a cozy loft with clocks on shelves and round windows |
| r-balcony | pass (rewrite) | SDXL would not draw the rail and telescope legibly; rewritten as the view from the balcony, which renders as a high dusk view over the village. Mood, not information (the telescope is in the text) |
| r-cellar | pass | glass jars on shelves, warm |
| r-square | pass | a lantern-less canal-town square; mood reads (warm stones, houses); the lanterns live in the text |
| r-workshop | pass (rewrite) | first render was an exterior barn; rewritten as an interior: workbench, slant light, shelves |
| r-well | pass | a well-house in greenery |
| r-garden | pass | a green garden with a house; pendulums are not legible (they are in the text) |
| r-orchard | pass | crooked trees in low gold light |
| r-lane | pass | blue doors and hanging baskets down a narrow lane |
| r-post | pass | pigeonhole shelves (two panels, but both read as the post office) |
| r-waiting | pass | a warm stair hall with windows |
| r-lamphouse | pass (rewrite) | first render abstract; rewritten as an attic bedroom (wicks, lantern-skins, narrow bed, yellow scarf): now one of the best |
| r-bridge | pass | a stone bridge over a green river |
| r-river | pass | a still river with reeds |
| r-duskroad | pass | a meadow road with a fence |
| r-hill | pass | rolling hills |

## Portraits (15)

| Toon | Verdict | Notes |
|---|---|---|
| t-tace | pass | unchanged seed (the tier_long portrait anchor); spectacles, apron, tools |
| t-bell | pass | unchanged seed (the tier_long anchor); butter-yellow scarf, hat |
| t-mott | pass | broom over the shoulder |
| t-fen | pass | glasses, cap, reading letters |
| t-umber | pass | the best of the cast: bright-eyed, moss cardigan |
| t-sorrel | pass | green coat, sprig in the hat |
| t-linden | pass | flowered apron, tea tray |
| t-quill | pass (sampler seed 11) | the default seed drew him from behind with no face; seed 11: a shy smile and the long-spouted can |
| t-tock | pass | a grey cat, clock-bright eyes |
| t-pims-nap | pass | a small child with flowers in the hair (the birthday crown did not render; mood reads) |
| t-extra-hour | pass | a figure in an autumn coat among falling leaves |
| t-rain-wait | pass | a child under a green umbrella |
| t-marram | pass (kept faceless on purpose) | seen from behind on the dunes: the summer that cannot remember its own name |
| t-margin | pass | a profile among doodled stars |
| t-nells-evening | pass | a girl in a sunhat at golden hour |
