BEGIN;

SET ROLE xau_monitor;

ALTER TABLE app.price_alerts
    ALTER COLUMN alert_limit SET DEFAULT 3;

UPDATE app.price_alerts
SET alert_limit = 3,
    updated_at = now()
WHERE status = 'active'
  AND alert_limit < 3;

INSERT INTO app.schema_migrations (version, description)
VALUES (7, 'Three-stage WeCom price alerts')
ON CONFLICT (version) DO NOTHING;

RESET ROLE;

COMMIT;
