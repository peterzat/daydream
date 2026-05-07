## Spec — 2026-05-07 — NPC memory retrieval (v0: SQLite-blob embeddings)

**Goal:** Give Rook and Iris a working memory of past exchanges so dialogue stops feeling goldfish. Add `daydream/memories.py` with capture + retrieve APIs backed by a per-world `memories` SQLite table; embed with `sentence-transformers` BGE-small on CPU; data-skill pipeline retrieves top-K by similarity + recency before LLM render and captures the exchange after dispatch. v0 deliberately defers LanceDB — embeddings are stored as BLOBs on each row and ranked with in-Python cosine + recency decay, which is sufficient at single-user scale and removes a dependency. Realizes the BACKLOG `npc-memory-retrieval` entry; closes the v1 NPC depth chain after `npc-drift-loop`.

### Acceptance Criteria

- [ ] **`daydream/memories.py` exposes capture and retrieve APIs that fail closed.** Module ships at minimum `capture(npc_id: str, world_id: str, text: str, source_event_seq: int | None = None) -> int | None` (returns the new memory id, or `None` on embedder/DB failure) and `retrieve(npc_id: str, world_id: str, query_text: str, k: int = 3) -> list[Memory]` (returns top-K by combined similarity + recency; empty list on failure). Both are sync; the CPU embedder doesn't need to be awaited and the data-skill pipeline calls them at well-defined points (see C4). Failures (embedder unavailable, model file missing, DB closed) are caught at the module boundary and logged via the existing `logging` pattern; never raised. The returned `Memory` shape carries at least `text`, `created_at`, `source_event_seq`, and a derived `age_seconds` field that the prompt template can render. Module DOES NOT take the GPU arbiter — embedding is CPU-only by construction.

- [ ] **Embedding via sentence-transformers BGE-small on CPU, lazy-loaded, lives in the shared HF cache.** Default model is `BAAI/bge-small-en-v1.5` (384-dim float32, ~1.5 KB per embedding); override via `DAYDREAM_MEMORY_MODEL`. Model loads on first capture/retrieve call (NOT at import or at server lifespan startup), cached as a module-level singleton thereafter. `device='cpu'` is set explicitly so a future GPU-aware default in `sentence-transformers` cannot accidentally pull the model onto the 20 GB card. The model file lives in `~/.cache/huggingface` per the zat.env shared-cache convention; a new `bin/memory-bootstrap` helper pre-downloads via `huggingface_hub.snapshot_download` and is idempotent (re-runs are a no-op when the model is already cached). `bin/memory-bootstrap` does NOT need to run at game start — `bin/game up` works without it; the first dialogue exchange triggers an on-demand download if the cache is cold (slow first call, fast thereafter). New runtime dependency added to `pyproject.toml`: `sentence-transformers` (and its transitive deps).

- [ ] **`migrations/009_memories.sql` adds the per-world memories table and is idempotent.** Columns: `id` (INTEGER PRIMARY KEY AUTOINCREMENT), `world_id` (TEXT NOT NULL REFERENCES worlds(id)), `npc_id` (TEXT NOT NULL — references toons but not as an FK so a deleted NPC's memories survive in the log; mirrors the events-table pattern), `text` (TEXT NOT NULL), `embedding` (BLOB — raw float32 bytes from the embedder, expected length 384*4 = 1536 bytes for BGE-small but column does not enforce), `created_at` (TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP), `source_event_seq` (INTEGER NULL — soft pointer to the event row that triggered capture, useful for traceability). Index on `(npc_id, world_id, created_at DESC)` so recency-ordered retrieval scales when memory counts grow. Migration uses `CREATE TABLE IF NOT EXISTS` + `CREATE INDEX IF NOT EXISTS` so re-runs converge.

- [ ] **NPC dialogue captures and retrieves memories around the LLM call in `daydream/skills/data.py`.** Skill-name → NPC-id mapping uses the toons table (look up the row whose name matches the skill's `ui_hint` or whose id is `f"t-{spec.name}"` — implementer picks the cheaper path that reads cleanly). If the skill has no matching NPC row (e.g., `forge` data skill, which is room-anchored not NPC-anchored), the memory retrieval/capture phases are skipped and the existing pipeline is unchanged.
  - **BEFORE Jinja render:** call `memories.retrieve(npc_id, world_id, args, k=DAYDREAM_MEMORY_TOP_K)` (default `k=3`); inject result into the template context as `memories` (a list of objects with `text`, `created_at`, `age_seconds`). Templates that don't reference `memories` are unaffected — the existing forge skill stays green.
  - **AFTER successful effects dispatch (i.e., not on refusal, not on empty-effects, not on banlist hit):** capture two memories — one for the player input (e.g., text formatted as "the visitor said: <args>") and one for the NPC's narration text extracted from the resulting `narrate` effect. Both tagged with the NPC's id. Capture is fire-and-forget at the function level: any failure inside `memories.capture` is swallowed by the module's own error handling (C1) and never propagates back into the skill pipeline.
  - The retrieval and capture phases run inside the same `arbiter.acquire()` window as the LLM call only insofar as that's where they're already invoked from; they themselves do NOT acquire the arbiter (CPU-only).

- [ ] **Rook and Iris prompt templates use the `memories` context variable when present and degrade silently when absent.** Both `skills/rook.json` and `skills/iris.json` updated to include a Jinja-conditional block — concretely something like `{% if memories %}You remember from earlier:\n{% for m in memories %}- {{ m.text }} ({{ m.age_seconds }}s ago)\n{% endfor %}{% endif %}`. The block is treated as **context the NPC may reference, not a literal recital**: the surrounding prompt-template language directs the NPC to weave one detail in naturally, NOT to quote or list memories. With `memories` empty (first-ever encounter, fresh world, retrieval-failed), the block renders to nothing and the existing Rook/Iris voices come through unchanged. Templates remain WHIMSY-tone-locked; no urgency, no modern tech, no harsh edges. The 1-2-sentence response shape and single-quoted dialogue convention are unchanged.

- [ ] **Tests cover capture + retrieve, scoping, ranking, and graceful failure; existing suites stay green.** New `tests/test_memories.py`:
   - **Roundtrip (tier_medium):** capture two memories with deterministic mocked embeddings, then retrieve with a query whose mock embedding has a known similarity ranking; assert the right memory is first.
   - **Per-NPC scoping (tier_medium):** capture for `t-rook` and `t-iris`; retrieve for `t-rook` returns only Rook's memories.
   - **Per-world scoping (tier_medium):** capture in `w-bunny` and a second test world; retrieve in one world doesn't leak the other.
   - **Top-K honored (tier_short with mocked retrieve internals OR tier_medium):** retrieve with `k=2` from a 5-memory store returns 2 entries.
   - **Recency tiebreaker (tier_medium):** two memories with identical similarity, the more recent one ranks higher.
   - **Empty store (tier_medium):** `retrieve` on an NPC with zero memories returns `[]`.
   - **Embedder failure (tier_short):** mock the embedder to raise; `retrieve` returns `[]`; `capture` returns `None`; both log a warning; no exception propagates.
   - **Integration (tier_medium, in `tests/test_ws_rook.py` or new):** end-to-end via TestClient — first turn captures memories, second turn's mocked LLM call sees a non-empty `memories` block in the rendered prompt. Mock the LLM to capture the `user` argument and assert the rendered-prompt contains the memory text. The existing 8 Rook tests + 8 Iris tests stay green by default (they run with memory disabled or with capture mocked, so no leak).

- [ ] **`bin/game test short` and `bin/game test medium` stay green; no new GPU-required tests.** Memory subsystem is opt-in for tests via `DAYDREAM_MEMORY_ENABLED` (default `1` in production code, default `0` in `tests/conftest.py`). When disabled, `memories.capture` and `memories.retrieve` short-circuit to no-op / `[]` so existing tests that don't care never load the embedder. Tests that exercise the memory path opt in via `monkeypatch.setenv("DAYDREAM_MEMORY_ENABLED", "1")` and mock `daydream.memories._embed` (or the `SentenceTransformer` class) to return deterministic vectors — no real BGE-small load anywhere in the test suite. `bin/memory-bootstrap` is a manual one-time tool, not invoked by any test; CI/test runs never touch the network or HF cache.

### Context

**Why the v0 simplification (no LanceDB).** The BACKLOG entry calls for "LanceDB vector store at `daydream/memories.py`". v0 instead stores the embedding as a BLOB column on the `memories` row and computes cosine similarity in Python at query time. At single-user scale (one human, two NPCs, conversation depth measured in dozens of exchanges), a linear scan over a per-NPC slice is sub-millisecond and adds zero new dependencies. LanceDB belongs in v1 once memory counts cross ~10K per NPC OR a second NPC archetype (cross-NPC retrieval, world-wide search) makes a proper index pay for itself. The future migration path is mechanical: read all rows, write to a Lance table, swap the retrieve internals. The BLOB column carries forward unchanged.

**Why CPU-only embedding.** BGE-small is ~100 MB, runs ~10-30 ms per query on CPU, and freeing the GPU is the higher-value choice on this 20 GB card (vLLM + ComfyUI already saturate the budget under the arbiter). The CPU path also dodges the arbiter entirely — capture and retrieve never serialize against in-flight LLM/image-gen calls, which is what the BACKLOG entry's "embed events near NPCs" cadence requires.

**Skill-name → NPC-id mapping.** The data-skill schema does not currently carry an `npc_id` field; the link is implicit via skill name + NPC name. v0 uses the cheapest of two paths — either `f"t-{spec.name}"` (works because Rook/Iris are `t-rook`/`t-iris`) or a query against `toons` by name match. Either is acceptable; the test for per-NPC scoping doesn't care about the mapping mechanism. Adding an explicit `npc_id` to the data-skill schema (heavier; touches `skills/*.json` + `daydream/skills/data.py` + DB schema) is deferred to v1 if the implicit mapping ever ambiguates.

**Capture trigger choice.** v0 captures memories ONLY for NPC dialogue exchanges (player input + NPC narration), not for every event in the log. The BACKLOG entry's "embed events near NPCs" admits broader interpretations (room enter/leave, drift narrates, snapshot transitions) that would inflate capture volume without proportional dialogue-quality gain. The narrower trigger keeps the contract testable and the storage footprint small. Drift-narrate capture is a defensible v1 extension once the v0 baseline is in.

**Salience formula.** The BACKLOG says "salience+recency". v0 collapses both into a single retrieval-time score: `score = cosine_similarity * exp(-age_hours / DECAY_HOURS)` with `DECAY_HOURS=24` (configurable via env if needed). Implementer is free to pick a different monotonic combination; the test contract only verifies "more similar wins" and "more recent wins on ties". Per-event salience tagging at capture (e.g., NPC speech > player input weighting) is deferred — adding a `salience` column is a one-migration future spec when needed.

**Test isolation pattern.** Mirrors the established `DAYDREAM_DRIFT_ENABLED=0` pattern from the previous turn. The conftest disables memory by default; tests opt in via monkeypatch. This keeps the existing 16 Rook/Iris dialogue tests stable (their LLM mocks pass through whatever prompt arrives; the new memories block is benign).

**zat.env conventions to respect.**
- Small committable increments. Natural split: C1+C2+C3 (module + embedder + migration) as one commit; C4 (data.py integration) as the next; C5 (template updates) as the next; C6+C7 (tests + green run) interleaved. Or bundle if a single commit reads cleanly.
- Commits attribute to `user.name` only.
- Verify `bin/game test short` and `bin/game test medium` pass before each commit.
- Don't add abstractions for v0. No plugin registry for memory backends, no per-NPC memory configs, no in-process eviction policy. One concrete implementation, one storage layout.
- Capture is fire-and-forget at the call site; no await dance, no try/except in the data.py call site beyond what the module already provides.
- Do NOT take the GPU arbiter from `daydream/memories.py`.
- HF cache (`~/.cache/huggingface`) is the model home — never override `HF_HOME`.

**Out of scope for this spec** (deferred):
- LanceDB vector store. Defer until single-user scale outgrows the linear scan.
- Memory pruning / GC. Few-dozen memories per NPC is fine forever at v0 scale.
- Per-event salience tagging at capture time.
- Cross-NPC memory sharing (Rook referencing what Iris was told). Per-NPC scoping is the v0 contract.
- Memory-driven mood updates (drift updating `toons.mood` from emotional memory cues).
- Drift-loop integration with memory (drift narrates as memory-aware) — current drift is pre-canned and stays so for v0.
- Ephemeral / forgotten memories (decay below a threshold → soft-delete). v0 keeps everything.
- Author-time memory editing tools / admin CLI.
- Voice-bench refresh against memory-augmented prompts. Existing voice baselines hold; if memory-bearing prompts visibly shift voice quality, that's a future spec.

**Critical files to create:**
- `daydream/memories.py` (C1, C2)
- `migrations/009_memories.sql` (C3)
- `tests/test_memories.py` (C6)
- `bin/memory-bootstrap` (C2; thin wrapper around `huggingface_hub.snapshot_download`)

**Critical files to modify:**
- `daydream/skills/data.py` (C4; retrieval before render, capture after dispatch)
- `skills/rook.json` (C5; memories block)
- `skills/iris.json` (C5; memories block)
- `tests/conftest.py` (C7; `DAYDREAM_MEMORY_ENABLED=0`)
- `tests/test_ws_rook.py` and/or `tests/test_ws_iris.py` (C6 integration test)
- `pyproject.toml` (C2; add `sentence-transformers` runtime dep)
- `CLAUDE.md` (brief subsection documenting the memory module + bootstrap path)

---
*Prior spec (2026-05-07): NPC drift loop (v0 pre-canned narrates) closed 5/5. `daydream/drift.py` ships an asyncio.Task drift loop with FastAPI lifespan integration (`start_drift_loop`/`stop_drift_loop`), env-overridable cadence (300 s idle / 1800 s busy), graceful cancellation, and a constant-dict pool of 4 lines per NPC (Rook + Iris). No GPU arbiter contention by design (no LLM call). `events.subscriber_count()` accessor added. Tests: 8 in `tests/test_drift.py`; tier_short 277 / tier_medium 376 green.*

<!-- SPEC_META: {"date":"2026-05-07","title":"NPC memory retrieval (v0: SQLite-blob embeddings)","criteria_total":7,"criteria_met":0} -->
