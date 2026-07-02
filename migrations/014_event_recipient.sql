-- 014_event_recipient: actor-private event routing.
--
-- NULL recipient_id (every pre-014 row and the default) means broadcast:
-- the event reaches every connection whose room filter matches, exactly as
-- before. A non-NULL recipient_id restricts delivery to the connection
-- controlling that toon: the WS broadcast loop drops the event for everyone
-- else, and snapshot/reconnect replay (events.fetch_since with a
-- recipient_for) filters symmetrically. Self-narrations (look / examine /
-- read / inventory and their validation refusals) ride this so one player's
-- reading never spams a co-located player's log.

ALTER TABLE events ADD COLUMN recipient_id TEXT;
