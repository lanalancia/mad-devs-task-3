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

CREATE TABLE maintenances (
    id bigserial PRIMARY KEY,
    target_kind text NOT NULL CHECK (target_kind IN ('url', 'group')),
    poll_entry_id bigint REFERENCES poll_entries (id) ON DELETE CASCADE,
    poll_group_id bigint REFERENCES poll_groups (id) ON DELETE CASCADE,
    starts_at timestamptz NOT NULL,
    ends_at timestamptz NOT NULL,
    settled_at timestamptz,
    CHECK (ends_at > starts_at),
    CHECK (
        (target_kind = 'url' AND poll_entry_id IS NOT NULL AND poll_group_id IS NULL)
        OR (target_kind = 'group' AND poll_group_id IS NOT NULL AND poll_entry_id IS NULL)
    )
);

CREATE INDEX maintenances_entry_idx ON maintenances (poll_entry_id);
CREATE INDEX maintenances_group_idx ON maintenances (poll_group_id);

CREATE TABLE incident_mail (
    poll_entry_id bigint NOT NULL REFERENCES poll_entries (id) ON DELETE CASCADE,
    incident_start timestamptz NOT NULL,
    started text NOT NULL CHECK (started IN ('wait', 'sent', 'skip')),
    ended text NOT NULL CHECK (ended IN ('wait', 'sent', 'skip')),
    PRIMARY KEY (poll_entry_id, incident_start)
);

CREATE TABLE sent_mails (
    id bigserial PRIMARY KEY,
    poll_entry_id bigint NOT NULL REFERENCES poll_entries (id) ON DELETE CASCADE,
    incident_start timestamptz NOT NULL,
    kind text NOT NULL CHECK (kind IN ('started', 'ended')),
    addresses text[] NOT NULL,
    message text NOT NULL,
    created_at timestamptz NOT NULL,
    UNIQUE (poll_entry_id, incident_start, kind)
);
