CREATE TABLE poll_groups (
    id bigserial PRIMARY KEY,
    name text NOT NULL UNIQUE CHECK (char_length(name) BETWEEN 1 AND 50),
    paused boolean NOT NULL DEFAULT false
);

CREATE TABLE poll_group_emails (
    id bigserial PRIMARY KEY,
    poll_group_id bigint NOT NULL REFERENCES poll_groups (id) ON DELETE CASCADE,
    address text NOT NULL,
    UNIQUE (poll_group_id, address)
);

CREATE TABLE poll_entries (
    id bigserial PRIMARY KEY,
    url text NOT NULL UNIQUE,
    timeout_seconds integer NOT NULL,
    interval_seconds integer NOT NULL,
    expected_code integer NOT NULL,
    status text NOT NULL CHECK (status IN ('ACTIVE', 'PAUSED', 'DELETED')),
    group_id bigint REFERENCES poll_groups (id) ON DELETE SET NULL
);

CREATE INDEX poll_entries_group_id_idx ON poll_entries (group_id);

CREATE TABLE poll_history (
    id bigserial PRIMARY KEY,
    poll_entry_id bigint NOT NULL REFERENCES poll_entries (id),
    polled_at timestamptz NOT NULL,
    http_status integer,
    duration_ms integer NOT NULL,
    message text NOT NULL
);

CREATE INDEX poll_history_entry_polled_at_idx
    ON poll_history (poll_entry_id, polled_at DESC);

CREATE TABLE poll_entry_events (
    id bigserial PRIMARY KEY,
    poll_entry_id bigint NOT NULL REFERENCES poll_entries (id) ON DELETE CASCADE,
    kind text NOT NULL CHECK (kind IN ('paused', 'resumed', 'deleted', 'restored')),
    happened_at timestamptz NOT NULL
);

CREATE INDEX poll_entry_events_entry_happened_at_idx
    ON poll_entry_events (poll_entry_id, happened_at);

CREATE TABLE users (
    id bigserial PRIMARY KEY,
    username text NOT NULL UNIQUE,
    password text NOT NULL
);
