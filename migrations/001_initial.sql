-- 001_initial: bootstrap "the smallest dream" world.
--
-- One world (bunny-world), one room (a quiet meadow), one toon (Wren), one
-- item (lantern with a sentinel-bearing seed for SPEC criterion 5). All
-- table shapes match the data model section in
-- ~/.claude/plans/let-s-design-a-fairly-giggly-narwhal.md; columns we don't
-- need yet (e.g., NPC memory tables) land in v1 migrations.

CREATE TABLE worlds (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    slug            TEXT NOT NULL UNIQUE,
    created_at      TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    aesthetic_seed  TEXT NOT NULL,
    clock_minutes   INTEGER NOT NULL DEFAULT 0,
    weather         TEXT NOT NULL DEFAULT 'still',
    schema_version  INTEGER NOT NULL DEFAULT 1,
    is_shelved      INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE rooms (
    id                  TEXT PRIMARY KEY,
    world_id            TEXT NOT NULL REFERENCES worlds(id),
    slug                TEXT NOT NULL,
    title               TEXT NOT NULL,
    seed                TEXT NOT NULL,
    description_cached  TEXT,
    image_cache_key     TEXT,
    exits_json          TEXT NOT NULL DEFAULT '{}',
    parent_id           TEXT REFERENCES rooms(id),
    UNIQUE (world_id, slug)
);

CREATE TABLE toons (
    id                  TEXT PRIMARY KEY,
    world_id            TEXT NOT NULL REFERENCES worlds(id),
    slot                INTEGER NOT NULL,
    name                TEXT NOT NULL,
    seed                TEXT NOT NULL,
    appearance_seed     TEXT NOT NULL,
    current_room_id     TEXT REFERENCES rooms(id),
    is_human_controlled INTEGER NOT NULL DEFAULT 0,
    controller_session  TEXT,
    inventory_json      TEXT NOT NULL DEFAULT '[]',
    mood                TEXT NOT NULL DEFAULT 'curious',
    created_at          TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    kicked_at           TEXT,
    UNIQUE (world_id, slot)
);

CREATE TABLE items (
    id              TEXT PRIMARY KEY,
    world_id        TEXT NOT NULL REFERENCES worlds(id),
    name            TEXT NOT NULL,
    seed            TEXT NOT NULL,
    room_id         TEXT REFERENCES rooms(id),
    toon_id         TEXT REFERENCES toons(id),
    properties_json TEXT NOT NULL DEFAULT '{}',
    is_unique       INTEGER NOT NULL DEFAULT 0,
    CHECK ((room_id IS NOT NULL) <> (toon_id IS NOT NULL))
);

CREATE TABLE skills (
    id                      TEXT PRIMARY KEY,
    name                    TEXT NOT NULL UNIQUE,
    kind                    TEXT NOT NULL CHECK (kind IN ('core', 'data')),
    context_predicate_json  TEXT NOT NULL DEFAULT '{}',
    prompt_template         TEXT,
    ui_hint                 TEXT,
    effects_schema_json     TEXT,
    author                  TEXT NOT NULL DEFAULT 'system',
    safety_rating           TEXT,
    enabled                 INTEGER NOT NULL DEFAULT 1
);

CREATE TABLE seeds (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_type TEXT NOT NULL,
    entity_id   TEXT NOT NULL,
    text        TEXT NOT NULL,
    created_at  TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    created_by  TEXT NOT NULL DEFAULT 'system'
);

CREATE TABLE events (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    actor_type   TEXT NOT NULL,
    actor_id     TEXT,
    kind         TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    room_id      TEXT REFERENCES rooms(id)
);

CREATE INDEX idx_events_room_seq ON events(room_id, seq);

-- v0 starter content. The lantern's seed contains "hairline crack" as a
-- sentinel that SPEC criterion 5 (`examine the lantern`) verifies.
INSERT INTO worlds (id, name, slug, aesthetic_seed) VALUES
    ('w-bunny', 'bunny world', 'bunny-world',
     'cozy soft painterly Spiritfarer-warm twilight, watercolor edges');

INSERT INTO rooms (id, world_id, slug, title, seed, description_cached) VALUES
    ('r-meadow', 'w-bunny', 'meadow', 'A Quiet Meadow',
     'a small grassy meadow at dusk, fireflies just beginning, soft watercolor edges',
     'A small grassy meadow at dusk. Fireflies are just beginning to drift between the tall grasses, and the air smells like cooling earth.');

INSERT INTO toons
    (id, world_id, slot, name, seed, appearance_seed, current_room_id, is_human_controlled, mood)
VALUES
    ('t-wren', 'w-bunny', 1, 'Wren',
     'a quiet wandering toon who hums when alone',
     'a soft watercolor toon, dusty cloak, freckles, kind eyes',
     'r-meadow', 0, 'curious');

INSERT INTO items (id, world_id, name, seed, room_id, properties_json, is_unique) VALUES
    ('i-lantern', 'w-bunny', 'lantern',
     'an old brass lantern with a hairline crack and a steady warm flame',
     'r-meadow', '{"lit": true}', 1);
