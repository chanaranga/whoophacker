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

CREATE TABLE IF NOT EXISTS user_settings (
    key        TEXT PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS agent_memories (
    id         SERIAL PRIMARY KEY,
    content    TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS workout_sessions (
    id             SERIAL PRIMARY KEY,
    workout_type   TEXT NOT NULL,
    start_time     TIMESTAMPTZ NOT NULL,
    end_time       TIMESTAMPTZ,
    duration_min   INTEGER,
    avg_hr         INTEGER,
    max_hr         INTEGER,
    avg_hrv        FLOAT,
    effort_score   INTEGER,
    recovery_cost  INTEGER,
    analysis_text  TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

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
    stage_breakdown TEXT,
    created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);
