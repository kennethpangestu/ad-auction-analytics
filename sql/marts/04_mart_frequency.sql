-- Performance by how many times the user had already seen the campaign.
-- Answers: where do extra impressions to the same user stop paying off?

CREATE TABLE mart_frequency AS
WITH bucketed AS (
    SELECT
        cost, click, credited, cpo,
        CASE
            WHEN impression_number = 1 THEN 1
            WHEN impression_number = 2 THEN 2
            WHEN impression_number = 3 THEN 3
            WHEN impression_number <= 5 THEN 4
            WHEN impression_number <= 10 THEN 5
            WHEN impression_number <= 20 THEN 6
            WHEN impression_number <= 50 THEN 7
            ELSE 8
        END AS bucket_order
    FROM fact_impression
),
totals AS (SELECT TOTAL(cost) AS spend FROM fact_impression)
SELECT
    bucket_order,
    CASE bucket_order
        WHEN 1 THEN '1' WHEN 2 THEN '2' WHEN 3 THEN '3' WHEN 4 THEN '4-5'
        WHEN 5 THEN '6-10' WHEN 6 THEN '11-20' WHEN 7 THEN '21-50' ELSE '51+'
    END                                             AS impression_number,
    COUNT(*)                                        AS impressions,
    TOTAL(cost)                                     AS spend,
    TOTAL(cost) / (SELECT spend FROM totals)        AS spend_share,
    SUM(credited)                                   AS attributed_conversions,
    1000.0 * TOTAL(cost) / COUNT(*)                 AS ecpm,
    1.0 * SUM(click) / COUNT(*)                     AS ctr,
    1000.0 * SUM(credited) / COUNT(*)               AS attributed_per_1k,
    TOTAL(cost) / NULLIF(SUM(credited), 0)          AS cpa
FROM bucketed
GROUP BY bucket_order
ORDER BY bucket_order;
