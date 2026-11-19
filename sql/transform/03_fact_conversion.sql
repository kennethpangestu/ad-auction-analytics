-- One row per conversion journey: every clicked impression that carries the
-- same (conversion_id, user_id). Criteo sub-sampled impressions before
-- release, so some journeys are missing their last click.

INSERT INTO fact_conversion (
    conversion_id, user_id, campaign_id, conversion_ts, conversion_day,
    clicks_in_data, clicks_total, first_click_ts, last_click_ts,
    hours_to_convert, attributed, journey_cost, cpo
)
SELECT
    conversion_id,
    user_id,
    MIN(campaign_id),
    MIN(conversion_ts),
    MIN(conversion_ts) / 86400,
    COUNT(*),
    MAX(click_nb),
    MIN(ts),
    MAX(CASE WHEN is_last_click = 1 THEN ts END),
    (MIN(conversion_ts) - MAX(CASE WHEN is_last_click = 1 THEN ts END)) / 3600.0,
    MAX(attributed),
    TOTAL(cost),
    AVG(cpo)
FROM fact_impression
WHERE conversion_id IS NOT NULL
GROUP BY conversion_id, user_id;
