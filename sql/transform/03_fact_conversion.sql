-- One row per conversion, summarizing the impressions that led to it.
-- The campaign credited here is the one behind the last impression before
-- the conversion.

INSERT INTO fact_conversion (
    conversion_id, user_id, campaign_id, conversion_ts, conversion_day,
    touch_impressions, touch_clicks, first_touch_ts, last_touch_ts,
    hours_to_convert, attributed, journey_cost, cpo
)
WITH touches AS (
    SELECT
        conversion_id, user_id, campaign_id, ts, conversion_ts, click,
        attributed, cost, cpo,
        ROW_NUMBER() OVER (PARTITION BY conversion_id ORDER BY ts DESC, impression_id DESC) AS rn
    FROM fact_impression
    WHERE conversion_id IS NOT NULL
),
journeys AS (
    SELECT
        conversion_id,
        MAX(conversion_ts) AS conversion_ts,
        COUNT(*)           AS touch_impressions,
        SUM(click)         AS touch_clicks,
        MIN(ts)            AS first_touch_ts,
        MAX(ts)            AS last_touch_ts,
        MAX(attributed)    AS attributed,
        SUM(cost)          AS journey_cost,
        MAX(cpo)           AS cpo
    FROM touches
    GROUP BY conversion_id
)
SELECT
    j.conversion_id,
    t.user_id,
    t.campaign_id,
    j.conversion_ts,
    j.conversion_ts / 86400,
    j.touch_impressions,
    j.touch_clicks,
    j.first_touch_ts,
    j.last_touch_ts,
    (j.conversion_ts - j.last_touch_ts) / 3600.0,
    j.attributed,
    j.journey_cost,
    j.cpo
FROM journeys j
JOIN touches t ON t.conversion_id = j.conversion_id AND t.rn = 1;
