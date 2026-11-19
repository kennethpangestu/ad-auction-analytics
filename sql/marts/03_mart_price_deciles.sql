-- Impressions split into ten equal groups by the price paid.
-- Answers: do the most expensive impressions earn their price?

CREATE TABLE mart_price_deciles AS
WITH ranked AS (
    SELECT cost, click, credited, cpo,
           NTILE(10) OVER (ORDER BY cost, impression_id) AS price_decile
    FROM fact_impression
),
totals AS (SELECT TOTAL(cost) AS spend, SUM(credited) AS attributed FROM fact_impression)
SELECT
    price_decile,
    MIN(cost)                                           AS min_price,
    MAX(cost)                                           AS max_price,
    COUNT(*)                                            AS impressions,
    TOTAL(cost)                                         AS spend,
    TOTAL(cost) / (SELECT spend FROM totals)            AS spend_share,
    SUM(credited)                                       AS attributed_conversions,
    1.0 * SUM(credited) / (SELECT attributed FROM totals) AS attributed_share,
    1.0 * SUM(click) / COUNT(*)                         AS ctr,
    1000.0 * SUM(credited) / COUNT(*)                   AS attributed_per_1k,
    TOTAL(cost) / NULLIF(SUM(credited), 0)              AS cpa,
    TOTAL(CASE WHEN credited = 1 THEN cpo END) / TOTAL(cost) AS roas
FROM ranked
GROUP BY price_decile
ORDER BY price_decile;
