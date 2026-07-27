BEGIN;

CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION xau_monitor;

SET ROLE xau_monitor;

CREATE TABLE IF NOT EXISTS app.schema_migrations (
    version integer PRIMARY KEY,
    description text NOT NULL,
    applied_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO app.schema_migrations (version, description)
VALUES (1, 'Initial PostgreSQL schema')
ON CONFLICT (version) DO NOTHING;

CREATE TABLE IF NOT EXISTS app.strategy_snapshots (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    market text NOT NULL CHECK (market IN ('xau', 'btc')),
    observed_at timestamptz NOT NULL,
    price numeric(24, 8) NOT NULL,
    strategy_version text NOT NULL,
    decision text NOT NULL,
    score smallint CHECK (score BETWEEN 0 AND 100),
    payload jsonb NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE (market, observed_at)
);

CREATE INDEX IF NOT EXISTS strategy_snapshots_market_time_idx
    ON app.strategy_snapshots (market, observed_at DESC);

RESET ROLE;

COMMIT;
