-- Clean staged rows into the impression fact table.
-- -1 is the source's "not applicable" value; it becomes NULL here so that
-- averages and counts in SQL do not silently include it.
--
-- Two derived columns matter for attribution:
--   is_last_click  this click was the last one before its conversion
--   credited       last click of a conversion the advertiser attributed to
--                  Criteo, i.e. the impression a last-click advertiser pays for

INSERT INTO fact_impression (
    impression_id, ts, day_key, hour_of_day, user_id, campaign_id,
    impression_number, cost, click, click_pos, click_nb, conversion,
    conversion_id, conversion_ts, attributed, is_last_click, credited, cpo,
    time_since_last_click,
    cat1, cat2, cat3, cat4, cat5, cat6, cat7, cat8, cat9
)
SELECT
    source_row,
    timestamp,
    timestamp / 86400,
    (timestamp % 86400) / 3600,
    uid,
    campaign,
    ROW_NUMBER() OVER (PARTITION BY uid, campaign ORDER BY timestamp, source_row),
    cost,
    click,
    NULLIF(click_pos, -1),
    NULLIF(click_nb, -1),
    conversion,
    NULLIF(conversion_id, -1),
    NULLIF(conversion_timestamp, -1),
    attribution,
    CASE WHEN click_nb > 0 AND click_pos = click_nb - 1 THEN 1 ELSE 0 END,
    CASE WHEN attribution = 1 AND click_nb > 0 AND click_pos = click_nb - 1 THEN 1 ELSE 0 END,
    cpo,
    NULLIF(time_since_last_click, -1),
    cat1, cat2, cat3, cat4, cat5, cat6, cat7, cat8, cat9
FROM stg_impressions
ORDER BY source_row;

CREATE INDEX idx_fact_impression_campaign_day ON fact_impression (campaign_id, day_key);
CREATE INDEX idx_fact_impression_user ON fact_impression (user_id);
CREATE INDEX idx_fact_impression_journey ON fact_impression (conversion_id, user_id)
    WHERE conversion_id IS NOT NULL;
