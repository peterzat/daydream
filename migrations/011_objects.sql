-- 011_objects: unify rooms / toons / items into a single `objects` table.
--
-- The MOO-style object model (plan the-output-of-this-greedy-hedgehog,
-- SPEC 2026-06-30). One table holds rooms, toons, things, and prototypes,
-- discriminated by `kind`. Containment is a self-referential `location_id`
-- (a toon's location is its room; a thing's location is the room it sits in
-- OR the toon carrying it; a room is top-level / NULL). Inheritance is a
-- `prototype_id` link to a `kind='prototype'` row that carries default verbs.
--
-- This migration TRANSFORMS the existing seeded rows in place (preserving
-- their ids -- r-meadow, t-wren, i-lantern, t-rook, t-iris, the multi-room
-- exits, presence_text, mood) so every id the running code and the test
-- suite reference survives the cutover, then drops the old tables. The
-- live world is separately archived + re-authored onto this schema by the
-- destructive reset; this transform is what keeps fresh DBs (tests,
-- `world load` outputs before re-author) coherent.
--
-- Promoted columns (real SQL columns, not JSON): the toon auth/slot fields
-- the slot-picker + uniqueness need (slot, controller_session,
-- is_human_controlled, kicked_at) plus the structural ones. Everything
-- kind-specific (seed, title, slug, exits, description_cached,
-- appearance_seed, mood, presence_text, is_unique, the old item property
-- bag) lives in properties_json.
--
-- Idempotency: this is a one-way structural migration, guarded by the
-- runner's filename-applied check; it is not re-runnable by hand (the
-- DROPs would fail on a second pass). That matches every other structural
-- migration in this chain.

CREATE TABLE objects (
    id                   TEXT PRIMARY KEY,
    world_id             TEXT NOT NULL REFERENCES worlds(id),
    kind                 TEXT NOT NULL CHECK (kind IN ('room', 'toon', 'thing', 'prototype')),
    name                 TEXT NOT NULL,
    aliases_json         TEXT NOT NULL DEFAULT '[]',
    -- MOO containment. NULL for rooms (top-level) and prototypes.
    location_id          TEXT REFERENCES objects(id),
    -- Archetype link (shallow, one level this turn). NULL for prototypes.
    prototype_id         TEXT REFERENCES objects(id),
    properties_json      TEXT NOT NULL DEFAULT '{}',
    -- Promoted toon-only columns (NULL for rooms / things / prototypes).
    slot                 INTEGER,
    controller_session   TEXT,
    is_human_controlled  INTEGER NOT NULL DEFAULT 0,
    kicked_at            TEXT,
    created_at           TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- Per-world slot uniqueness for toons (carries the old toons UNIQUE(world_id,
-- slot) forward; partial so non-toon rows, whose slot is NULL, are exempt).
CREATE UNIQUE INDEX idx_objects_world_slot ON objects(world_id, slot) WHERE kind = 'toon';
-- Containment scans (contents of a room / a toon's inventory).
CREATE INDEX idx_objects_world_location ON objects(world_id, location_id);
-- Kind scans (all toons / all things in a world).
CREATE INDEX idx_objects_world_kind ON objects(world_id, kind);

-- Prototypes first (FK targets for prototype_id below). One set per world;
-- v0 is single-world-per-DB (every reference hardcodes w-bunny), so the
-- bare `proto-*` ids do not collide. Each carries its default verb set in
-- properties.verbs; the verb registry (increment 2) reads these.
INSERT INTO objects (id, world_id, kind, name, properties_json)
    SELECT 'proto-room', id, 'prototype', 'room', '{"verbs":["look"]}' FROM worlds;
INSERT INTO objects (id, world_id, kind, name, properties_json)
    SELECT 'proto-npc', id, 'prototype', 'npc', '{"verbs":["examine","talk"]}' FROM worlds;
INSERT INTO objects (id, world_id, kind, name, properties_json)
    SELECT 'proto-thing', id, 'prototype', 'thing', '{"verbs":["examine","take","drop"]}' FROM worlds;
INSERT INTO objects (id, world_id, kind, name, properties_json)
    SELECT 'proto-readable', id, 'prototype', 'readable', '{"verbs":["examine","take","drop"]}' FROM worlds;

-- Rooms -> objects (location NULL; name = title; exits embedded as JSON).
INSERT INTO objects (id, world_id, kind, name, location_id, prototype_id, properties_json)
    SELECT id, world_id, 'room', title, NULL, 'proto-room',
           json_object(
               'slug', slug,
               'title', title,
               'seed', seed,
               'description_cached', description_cached,
               'exits', json(exits_json),
               'parent_id', parent_id
           )
    FROM rooms;

-- Toons -> objects (location = current room; promoted auth/slot columns;
-- everything else into properties).
INSERT INTO objects (id, world_id, kind, name, location_id, prototype_id,
                     properties_json, slot, controller_session,
                     is_human_controlled, kicked_at, created_at)
    SELECT id, world_id, 'toon', name, current_room_id, 'proto-npc',
           json_object(
               'seed', seed,
               'appearance_seed', appearance_seed,
               'mood', mood,
               'presence_text', presence_text
           ),
           slot, controller_session, is_human_controlled, kicked_at, created_at
    FROM toons;

-- Items -> objects (kind 'thing'; location = room OR carrier toon; old item
-- property bag merged with seed + is_unique).
INSERT INTO objects (id, world_id, kind, name, location_id, prototype_id, properties_json)
    SELECT id, world_id, 'thing', name, COALESCE(room_id, toon_id), 'proto-thing',
           json_patch(properties_json, json_object('seed', seed, 'is_unique', is_unique))
    FROM items;

-- Drop the old tables (children before parents for FK integrity).
DROP TABLE items;
DROP TABLE toons;
DROP TABLE rooms;
