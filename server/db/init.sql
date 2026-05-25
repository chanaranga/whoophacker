CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS health_metrics (
    time          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    heart_rate    INTEGER,
    hrv_rmssd     FLOAT,
    spo2          FLOAT,
    skin_temp     FLOAT,
    resp_rate     FLOAT
);

SELECT create_hypertable('health_metrics', 'time', if_not_exists => TRUE);

CREATE TABLE IF NOT EXISTS sleep_sessions (
    id             SERIAL PRIMARY KEY,
    start_time     TIMESTAMPTZ NOT NULL,
    end_time       TIMESTAMPTZ,
    duration_min   INTEGER,
    avg_hrv        FLOAT,
    avg_hr         INTEGER,
    min_spo2       FLOAT,
    sleep_score    INTEGER,
    analysis_text  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
