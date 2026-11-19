-- Campaign x day KPIs: the table a campaign performance dashboard reads.
-- Conversions are counted on the day of the last click that earned them.
--   eCPM = spend per 1,000 impressions
--   CPA  = spend per attributed conversion
--   ROAS = attributed order value per unit of spend

CREATE TABLE mart_campaign_daily AS
SELECT
    campaign_id,
    day_key,
    COUNT(*)                                                    AS impressions,
    SUM(click)                                                  AS clicks,
    SUM(is_last_click)                                          AS conversions,
    SUM(credited)                                               AS attributed_conversions,
    TOTAL(cost)                                                 AS spend,
    TOTAL(CASE WHEN credited = 1 THEN cpo END)                  AS attributed_value,
    1.0 * SUM(click) / COUNT(*)                                 AS ctr,
    1000.0 * TOTAL(cost) / COUNT(*)                             AS ecpm,
    TOTAL(cost) / NULLIF(SUM(click), 0)                         AS cpc,
    TOTAL(cost) / NULLIF(SUM(credited), 0)                      AS cpa,
    TOTAL(CASE WHEN credited = 1 THEN cpo END) / TOTAL(cost)    AS roas
FROM fact_impression
GROUP BY campaign_id, day_key;

CREATE UNIQUE INDEX idx_mart_campaign_daily ON mart_campaign_daily (campaign_id, day_key);
