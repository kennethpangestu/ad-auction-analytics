-- Build the dimension tables from the cleaned facts.

INSERT INTO dim_date (day_key, week_index, day_of_week)
SELECT DISTINCT day_key, day_key / 7, day_key % 7
FROM fact_impression
ORDER BY day_key;

INSERT INTO dim_campaign (campaign_id, first_day, last_day, active_days, avg_cpo)
SELECT campaign_id, MIN(day_key), MAX(day_key), COUNT(DISTINCT day_key), AVG(cpo)
FROM fact_impression
GROUP BY campaign_id;

INSERT INTO dim_user (user_id, first_seen_ts, last_seen_ts, impressions, campaigns)
SELECT user_id, MIN(ts), MAX(ts), COUNT(*), COUNT(DISTINCT campaign_id)
FROM fact_impression
GROUP BY user_id;
