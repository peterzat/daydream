-- Accounts, sessions, invites and login throttles (SPEC 2026-09-27
-- criteria 2-4). Lives in its own per-env database (accounts-<env>.db),
-- never the world DB, so a world reset, swap or refresh cannot touch who
-- may play. All timestamps are UTC ISO-8601 "YYYY-MM-DDTHH:MM:SSZ", so
-- string comparison orders them.

CREATE TABLE accounts (
    id            TEXT PRIMARY KEY,                       -- a-<hex>
    username      TEXT NOT NULL UNIQUE COLLATE NOCASE,    -- login name, lowercase
    display_name  TEXT NOT NULL,                          -- the name the invite was for
    password_hash TEXT NOT NULL,                          -- argon2id encoded hash
    role          TEXT NOT NULL DEFAULT 'player' CHECK (role IN ('player', 'admin')),
    created_at    TEXT NOT NULL,
    invite_id     TEXT,                                   -- the join invite redeemed
    disabled_at   TEXT,                                   -- non-NULL: cannot log in
    last_login_at TEXT
);

CREATE TABLE sessions (
    id           TEXT PRIMARY KEY,                        -- s-<hex>; public id (controller_session)
    token_hash   TEXT NOT NULL UNIQUE,                    -- sha256 of the cookie token
    account_id   TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    created_at   TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    expires_at   TEXT NOT NULL,                           -- slides 30 days on use
    left_at      TEXT,                                    -- left the dream in this session
    user_agent   TEXT NOT NULL DEFAULT ''
);
CREATE INDEX sessions_by_account ON sessions(account_id);

CREATE TABLE invites (
    id          TEXT PRIMARY KEY,                         -- i-<hex>; what list/revoke name
    slug_hash   TEXT NOT NULL UNIQUE,                     -- sha256 of the two-word slug
    kind        TEXT NOT NULL CHECK (kind IN ('join', 'reset')),
    for_name    TEXT NOT NULL,                            -- who it was made for
    account_id  TEXT REFERENCES accounts(id),             -- reset target / account a join created
    created_at  TEXT NOT NULL,
    created_by  TEXT NOT NULL DEFAULT 'cli',
    expires_at  TEXT NOT NULL,
    redeemed_at TEXT,
    revoked_at  TEXT,
    note        TEXT NOT NULL DEFAULT ''
);

-- Fixed-window failure counters: login per address and per username,
-- invite redemption per address and globally (per hour and per day).
CREATE TABLE throttle (
    key          TEXT PRIMARY KEY,
    window_start TEXT NOT NULL,
    count        INTEGER NOT NULL
);
