-- 018_toon_owner: a human toon belongs to one account (SPEC 2026-09-27
-- criterion 5).
--
-- Accounts live in their own database (accounts-<env>.db, daydream/accounts.py),
-- so this is a plain id, not a foreign key: a world reset keeps the accounts
-- and loses the toons, and an account with no toon simply makes a new one.
-- NULL means unowned (NPCs, and the seeded or pre-accounts human toons an
-- account may adopt). Additive: every existing row reads as unowned.

ALTER TABLE objects ADD COLUMN owner_account TEXT;

CREATE INDEX IF NOT EXISTS objects_toon_owner
    ON objects(world_id, owner_account)
    WHERE kind = 'toon' AND owner_account IS NOT NULL;
