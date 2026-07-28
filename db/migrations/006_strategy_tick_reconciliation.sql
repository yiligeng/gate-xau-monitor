BEGIN;

SET ROLE xau_monitor;

ALTER TABLE app.point_strategy_trials
    DROP CONSTRAINT IF EXISTS point_strategy_trials_status_check;

ALTER TABLE app.point_strategy_trials
    ADD CONSTRAINT point_strategy_trials_status_check
    CHECK (
        status IN (
            'pending',
            'open',
            'win',
            'loss',
            'ambiguous',
            'expired',
            'replaced',
            'cancelled'
        )
    ),
    ADD COLUMN IF NOT EXISTS strategy_reconciled_at timestamptz
        NOT NULL DEFAULT now(),
    ADD COLUMN IF NOT EXISTS resolution_source text
        NOT NULL DEFAULT 'gate_last_live',
    ADD COLUMN IF NOT EXISTS ambiguity_reason text;

CREATE INDEX IF NOT EXISTS point_strategy_trials_reconcile_idx
    ON app.point_strategy_trials (
        market,
        strategy_reconciled_at,
        id
    )
    WHERE status IN ('pending', 'open');

CREATE INDEX IF NOT EXISTS price_alerts_chat_market_created_idx
    ON app.price_alerts (chat_id, market, created_at DESC)
    INCLUDE (
        level,
        status,
        alerts_sent,
        alert_limit,
        last_alert_at,
        breached_at
    );

INSERT INTO app.schema_migrations (version, description)
VALUES (6, 'Alert history and one-second strategy wick reconciliation')
ON CONFLICT (version) DO NOTHING;

RESET ROLE;

COMMIT;
