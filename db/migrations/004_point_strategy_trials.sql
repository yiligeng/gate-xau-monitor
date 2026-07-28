BEGIN;

SET ROLE xau_monitor;

CREATE TABLE IF NOT EXISTS app.point_strategy_trials (
    id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    price_alert_id bigint NOT NULL UNIQUE
        REFERENCES app.price_alerts(id) ON DELETE RESTRICT,
    chat_id text NOT NULL,
    market text NOT NULL CHECK (market IN ('xau', 'btc')),
    strategy_version text NOT NULL DEFAULT 'LEVEL-5X5-V1',
    price_basis text NOT NULL DEFAULT 'last' CHECK (price_basis = 'last'),
    direction text NOT NULL CHECK (direction IN ('long', 'short')),
    initial_price numeric(24, 8) NOT NULL,
    entry_price numeric(24, 8) NOT NULL,
    stop_loss numeric(24, 8) NOT NULL,
    take_profit numeric(24, 8) NOT NULL,
    risk_points numeric(12, 4) NOT NULL DEFAULT 5.0 CHECK (risk_points > 0),
    reward_points numeric(12, 4) NOT NULL DEFAULT 5.0 CHECK (reward_points > 0),
    status text NOT NULL DEFAULT 'pending'
        CHECK (
            status IN (
                'pending',
                'open',
                'win',
                'loss',
                'expired',
                'replaced',
                'cancelled'
            )
        ),
    entry_expires_at timestamptz NOT NULL,
    trigger_observed_price numeric(24, 8),
    exit_observed_price numeric(24, 8),
    triggered_at timestamptz,
    resolved_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (
        (
            direction = 'long'
            AND stop_loss < entry_price
            AND take_profit > entry_price
        )
        OR
        (
            direction = 'short'
            AND stop_loss > entry_price
            AND take_profit < entry_price
        )
    )
);

CREATE INDEX IF NOT EXISTS point_strategy_trials_market_status_idx
    ON app.point_strategy_trials (market, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS point_strategy_trials_chat_market_idx
    ON app.point_strategy_trials (chat_id, market, created_at DESC);

INSERT INTO app.point_strategy_trials (
    price_alert_id,
    chat_id,
    market,
    direction,
    initial_price,
    entry_price,
    stop_loss,
    take_profit,
    entry_expires_at,
    created_at,
    updated_at
)
SELECT
    alert.id,
    alert.chat_id,
    alert.market,
    CASE alert.side
        WHEN 'below' THEN 'long'
        WHEN 'above' THEN 'short'
    END,
    alert.created_price,
    alert.level,
    CASE alert.side
        WHEN 'below' THEN alert.level - 5.0
        WHEN 'above' THEN alert.level + 5.0
    END,
    CASE alert.side
        WHEN 'below' THEN alert.level + 5.0
        WHEN 'above' THEN alert.level - 5.0
    END,
    alert.expires_at,
    alert.created_at,
    now()
FROM app.price_alerts AS alert
WHERE alert.status = 'active'
  AND alert.expires_at > now()
  AND alert.side IN ('above', 'below')
ON CONFLICT (price_alert_id) DO NOTHING;

INSERT INTO app.schema_migrations (version, description)
VALUES (4, 'Fixed five-point level strategy trials')
ON CONFLICT (version) DO NOTHING;

RESET ROLE;

COMMIT;
