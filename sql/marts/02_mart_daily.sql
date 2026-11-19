-- Portfolio KPIs by day, rolled up from the campaign mart.

CREATE TABLE mart_daily AS
SELECT
    day_key,
    COUNT(*)                                AS active_campaigns,
    SUM(impressions)                        AS impressions,
    SUM(clicks)                             AS clicks,
    SUM(conversions)                        AS conversions,
    SUM(attributed_conversions)             AS attributed_conversions,
    SUM(spend)                              AS spend,
    SUM(attributed_value)                   AS attributed_value,
    1.0 * SUM(clicks) / SUM(impressions)    AS ctr,
    1000.0 * SUM(spend) / SUM(impressions)  AS ecpm,
    SUM(spend) / NULLIF(SUM(attributed_conversions), 0) AS cpa,
    SUM(attributed_value) / SUM(spend)      AS roas
FROM mart_campaign_daily
GROUP BY day_key
ORDER BY day_key;
