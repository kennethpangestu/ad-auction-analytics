-- Warehouse schema: one staging table, a star schema, and run metadata.
-- The star schema is rebuilt on every run. Run metadata is kept across runs.

DROP TABLE IF EXISTS mart_conversion_delay;
DROP TABLE IF EXISTS mart_frequency;
DROP TABLE IF EXISTS mart_price_deciles;
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
    avg_cpo         REAL NOT NULL
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
    impression_number     INTEGER NOT NULL,  -- 1 = first time this user saw this campaign
    cost                  REAL    NOT NULL,  -- price paid in the auction
    click                 INTEGER NOT NULL,
    click_pos             INTEGER,
    click_nb              INTEGER,
    conversion            INTEGER NOT NULL,
    conversion_id         INTEGER,
    conversion_ts         INTEGER,
    attributed            INTEGER NOT NULL,
    is_last_click         INTEGER NOT NULL,  -- last click before its conversion
    credited              INTEGER NOT NULL,  -- last click of an attributed conversion
    cpo                   REAL    NOT NULL,  -- advertiser's value for an attributed order
    time_since_last_click INTEGER,
    cat1 INTEGER, cat2 INTEGER, cat3 INTEGER, cat4 INTEGER, cat5 INTEGER,
    cat6 INTEGER, cat7 INTEGER, cat8 INTEGER, cat9 INTEGER
);

-- Grain: one row per conversion journey, keyed by (conversion_id, user_id)
-- because a small number of anonymized conversion_ids are shared by users.
-- In this dataset conversions are post-click: every touchpoint is a click.
CREATE TABLE fact_conversion (
    conversion_key   INTEGER PRIMARY KEY,
    conversion_id    INTEGER NOT NULL,
    user_id          INTEGER NOT NULL REFERENCES dim_user (user_id),
    campaign_id      INTEGER NOT NULL REFERENCES dim_campaign (campaign_id),
    conversion_ts    INTEGER NOT NULL,
    conversion_day   INTEGER NOT NULL,
    clicks_in_data   INTEGER NOT NULL,  -- clicked impressions in this sample
    clicks_total     INTEGER NOT NULL,  -- clicks before the conversion (click_nb)
    first_click_ts   INTEGER NOT NULL,
    last_click_ts    INTEGER,           -- NULL when the last click was sampled out
    hours_to_convert REAL,              -- from the last click to the conversion
    attributed       INTEGER NOT NULL,
    journey_cost     REAL    NOT NULL,
    cpo              REAL    NOT NULL,
    UNIQUE (conversion_id, user_id)
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
