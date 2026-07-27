BEGIN;

SET ROLE xau_monitor;

CREATE TABLE IF NOT EXISTS app.users (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username text NOT NULL,
    username_key text NOT NULL UNIQUE,
    password_hash text NOT NULL,
    is_active boolean NOT NULL DEFAULT true,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    password_changed_at timestamptz NOT NULL DEFAULT now(),
    last_login_at timestamptz
);

CREATE TABLE IF NOT EXISTS app.sessions (
    token_hash text PRIMARY KEY,
    user_id bigint NOT NULL REFERENCES app.users(id) ON DELETE CASCADE,
    created_at timestamptz NOT NULL DEFAULT now(),
    expires_at timestamptz NOT NULL,
    last_seen_at timestamptz NOT NULL DEFAULT now(),
    ip_address inet NOT NULL,
    user_agent text NOT NULL DEFAULT '',
    CHECK (expires_at > created_at)
);

CREATE INDEX IF NOT EXISTS sessions_user_id_idx
    ON app.sessions (user_id);
CREATE INDEX IF NOT EXISTS sessions_expires_at_idx
    ON app.sessions (expires_at);

INSERT INTO app.schema_migrations (version, description)
VALUES (2, 'Database-backed users and sessions')
ON CONFLICT (version) DO NOTHING;

RESET ROLE;

COMMIT;
