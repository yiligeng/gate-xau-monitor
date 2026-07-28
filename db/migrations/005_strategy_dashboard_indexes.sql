BEGIN;

SET ROLE xau_monitor;

ALTER TABLE app.point_strategy_trials
    ADD COLUMN IF NOT EXISTS setup_day date;

UPDATE app.point_strategy_trials
SET setup_day = (created_at AT TIME ZONE 'Asia/Shanghai')::date
WHERE setup_day IS NULL;

ALTER TABLE app.point_strategy_trials
    ALTER COLUMN setup_day SET NOT NULL;

CREATE INDEX IF NOT EXISTS point_strategy_trials_daily_idx
    ON app.point_strategy_trials (
        chat_id,
        market,
        setup_day DESC,
        direction,
        status
    )
    INCLUDE (risk_points, reward_points);

CREATE INDEX IF NOT EXISTS point_strategy_trials_page_idx
    ON app.point_strategy_trials (chat_id, market, id DESC);

INSERT INTO app.schema_migrations (version, description)
VALUES (5, 'Strategy dashboard daily grain and pagination indexes')
ON CONFLICT (version) DO NOTHING;

RESET ROLE;

COMMIT;
