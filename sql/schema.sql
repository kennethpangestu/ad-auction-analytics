-- Warehouse schema: one staging table, a star schema, and run metadata.
-- The star schema is rebuilt on every run. Run metadata is kept across runs.

DROP TABLE IF EXISTS mart_hourly;
DROP TABLE IF EXISTS mart_cost_deciles;
DROP TABLE IF EXISTS mart_daily;
DROP TABLE IF EXISTS mart_campaign_daily;
DROP TABLE IF EXISTS fact_conversion;
DROP TABLE IF EXISTS fact_impression;
DROP TABLE IF EXISTS dim_user;
DROP TABLE IF EXISTS dim_campaign;
DROP TABLE IF EXISTS dim_date;
DROP TABLE IF EXISTS stg_impressions;

-- Source rows exactly as delivered, including -1 sentinel values.
CREATE TABLE stg_impressions (
    source_row            INTEGER PRIMARY KEY,
    timestamp             INTEGER,
    uid                   INTEGER,
    campaign              INTEGER,
    conversion            INTEGER,
    conversion_timestamp  INTEGER,
    conversion_id         INTEGER,
    attribution           INTEGER,
    click                 INTEGER,
    click_pos             INTEGER,
    click_nb              INTEGER,
    cost                  REAL,
    cpo                   REAL,
    time_since_last_click INTEGER,
    cat1 INTEGER, cat2 INTEGER, cat3 INTEGER, cat4 INTEGER, cat5 INTEGER,
    cat6 INTEGER, cat7 INTEGER, cat8 INTEGER, cat9 INTEGER
);

-- Timestamps in the source are seconds since the first impression, so days
-- are relative (day 0 = first day of traffic), not calendar dates.
CREATE TABLE dim_date (
    day_key     INTEGER PRIMARY KEY,
    week_index  INTEGER NOT NULL,
    day_of_week INTEGER NOT NULL  -- 0 to 6, relative to day 0
);

CREATE TABLE dim_campaign (
    campaign_id     INTEGER PRIMARY KEY,
    first_day       INTEGER NOT NULL,
    last_day        INTEGER NOT NULL,
    active_days     INTEGER NOT NULL,
    conversion_value REAL  -- typical value (cpo) of an attributed conversion
);

CREATE TABLE dim_user (
    user_id       INTEGER PRIMARY KEY,
    first_seen_ts INTEGER NOT NULL,
    last_seen_ts  INTEGER NOT NULL,
    impressions   INTEGER NOT NULL,
    campaigns     INTEGER NOT NULL
);

-- Grain: one row per ad impression (one auction won and displayed).
CREATE TABLE fact_impression (
    impression_id         INTEGER PRIMARY KEY,
    ts                    INTEGER NOT NULL,
    day_key               INTEGER NOT NULL REFERENCES dim_date (day_key),
    hour_of_day           INTEGER NOT NULL,
    user_id               INTEGER NOT NULL REFERENCES dim_user (user_id),
    campaign_id           INTEGER NOT NULL REFERENCES dim_campaign (campaign_id),
    cost                  REAL    NOT NULL,  -- price paid in the auction
    click                 INTEGER NOT NULL,
    click_pos             INTEGER,
    click_nb              INTEGER,
    conversion            INTEGER NOT NULL,
    conversion_id         INTEGER,
    conversion_ts         INTEGER,
    attributed            INTEGER NOT NULL,
    cpo                   REAL,
    time_since_last_click INTEGER,
    cat1 INTEGER, cat2 INTEGER, cat3 INTEGER, cat4 INTEGER, cat5 INTEGER,
    cat6 INTEGER, cat7 INTEGER, cat8 INTEGER, cat9 INTEGER
);

-- Grain: one row per conversion, with its journey summarized.
CREATE TABLE fact_conversion (
    conversion_id        INTEGER PRIMARY KEY,
    user_id              INTEGER NOT NULL REFERENCES dim_user (user_id),
    campaign_id          INTEGER NOT NULL REFERENCES dim_campaign (campaign_id),
    conversion_ts        INTEGER NOT NULL,
    conversion_day       INTEGER NOT NULL,
    touch_impressions    INTEGER NOT NULL,
    touch_clicks         INTEGER NOT NULL,
    first_touch_ts       INTEGER NOT NULL,
    last_touch_ts        INTEGER NOT NULL,
    hours_to_convert     REAL    NOT NULL,  -- from last impression to conversion
    attributed           INTEGER NOT NULL,
    journey_cost         REAL    NOT NULL,
    cpo                  REAL
);

CREATE TABLE IF NOT EXISTS pipeline_runs (
    run_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT NOT NULL,
    finished_at  TEXT,
    source_file  TEXT NOT NULL,
    source_bytes INTEGER,
    rows_loaded  INTEGER,
    status       TEXT NOT NULL,
    seconds      REAL
);

CREATE TABLE IF NOT EXISTS dq_results (
    run_id       INTEGER,
    check_name   TEXT NOT NULL,
    severity     TEXT NOT NULL,
    description  TEXT NOT NULL,
    failing_rows INTEGER NOT NULL,
    passed       INTEGER NOT NULL
);
