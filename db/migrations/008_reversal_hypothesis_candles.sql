BEGIN;

SET ROLE xau_monitor;

CREATE TABLE IF NOT EXISTS app.market_candles_1m (
    market text NOT NULL CHECK (market IN ('xau', 'btc')),
    opened_at timestamptz NOT NULL,
    open numeric(24, 8) NOT NULL,
    high numeric(24, 8) NOT NULL,
    low numeric(24, 8) NOT NULL,
    close numeric(24, 8) NOT NULL,
    source text NOT NULL,
    captured_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (market, opened_at),
    CHECK (high >= low),
    CHECK (high >= open AND high >= close),
    CHECK (low <= open AND low <= close)
);

CREATE INDEX IF NOT EXISTS market_candles_1m_time_idx
    ON app.market_candles_1m (opened_at DESC, market);

INSERT INTO app.schema_migrations (version, description)
VALUES (8, 'Persist one-minute candles for reversal hypothesis research')
ON CONFLICT (version) DO NOTHING;

RESET ROLE;

COMMIT;
