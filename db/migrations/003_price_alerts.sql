BEGIN;

SET ROLE xau_monitor;

CREATE TABLE IF NOT EXISTS app.price_alerts (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    chat_id text NOT NULL,
    created_by text NOT NULL DEFAULT '',
    market text NOT NULL CHECK (market IN ('xau', 'btc')),
    level numeric(24, 8) NOT NULL,
    created_price numeric(24, 8) NOT NULL,
    side text NOT NULL CHECK (side IN ('above', 'below', 'at')),
    approach_distance numeric(12, 4) NOT NULL DEFAULT 3.0,
    alert_limit smallint NOT NULL DEFAULT 2 CHECK (alert_limit BETWEEN 1 AND 10),
    alerts_sent smallint NOT NULL DEFAULT 0 CHECK (alerts_sent >= 0),
    status text NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'breached', 'expired', 'replaced', 'cancelled')),
    source_text text NOT NULL DEFAULT '',
    expires_at timestamptz NOT NULL,
    last_alert_at timestamptz,
    breached_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS price_alerts_active_market_idx
    ON app.price_alerts (market, expires_at, status)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS price_alerts_chat_market_idx
    ON app.price_alerts (chat_id, market, expires_at DESC);

INSERT INTO app.schema_migrations (version, description)
VALUES (3, 'WeCom daily price alerts')
ON CONFLICT (version) DO NOTHING;

RESET ROLE;

COMMIT;
