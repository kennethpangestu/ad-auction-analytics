-- Clean staged rows into the impression fact table.
-- -1 is the source's "not applicable" value; it becomes NULL here so that
-- averages and counts in SQL do not silently include it.

INSERT INTO fact_impression (
    impression_id, ts, day_key, hour_of_day, user_id, campaign_id, cost,
    click, click_pos, click_nb, conversion, conversion_id, conversion_ts,
    attributed, cpo, time_since_last_click,
    cat1, cat2, cat3, cat4, cat5, cat6, cat7, cat8, cat9
)
SELECT
    source_row,
    timestamp,
    timestamp / 86400,
    (timestamp % 86400) / 3600,
    uid,
    campaign,
    cost,
    click,
    NULLIF(click_pos, -1),
    NULLIF(click_nb, -1),
    conversion,
    NULLIF(conversion_id, -1),
    NULLIF(conversion_timestamp, -1),
    attribution,
    cpo,
    NULLIF(time_since_last_click, -1),
    cat1, cat2, cat3, cat4, cat5, cat6, cat7, cat8, cat9
FROM stg_impressions
ORDER BY source_row;

CREATE INDEX idx_fact_impression_campaign_day ON fact_impression (campaign_id, day_key);
CREATE INDEX idx_fact_impression_user ON fact_impression (user_id);
CREATE INDEX idx_fact_impression_conversion ON fact_impression (conversion_id)
    WHERE conversion_id IS NOT NULL;
