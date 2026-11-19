-- How long after the last click do conversions arrive?
-- This sets how long a day's CPA keeps changing after the day ends.

CREATE TABLE mart_conversion_delay AS
WITH bucketed AS (
    SELECT
        CASE
            WHEN hours_to_convert < 1 THEN 1
            WHEN hours_to_convert < 24 THEN 2
            WHEN hours_to_convert < 72 THEN 3
            WHEN hours_to_convert < 168 THEN 4
            WHEN hours_to_convert < 336 THEN 5
            ELSE 6
        END AS bucket_order
    FROM fact_conversion
    WHERE hours_to_convert IS NOT NULL
),
counts AS (SELECT bucket_order, COUNT(*) AS conversions FROM bucketed GROUP BY bucket_order)
SELECT
    bucket_order,
    CASE bucket_order
        WHEN 1 THEN 'under 1 hour' WHEN 2 THEN '1 to 24 hours' WHEN 3 THEN '1 to 3 days'
        WHEN 4 THEN '3 to 7 days' WHEN 5 THEN '7 to 14 days' ELSE '14 to 30 days'
    END AS delay,
    conversions,
    1.0 * conversions / SUM(conversions) OVER () AS share,
    1.0 * SUM(conversions) OVER (ORDER BY bucket_order) / SUM(conversions) OVER () AS cumulative_share
FROM counts
ORDER BY bucket_order;
