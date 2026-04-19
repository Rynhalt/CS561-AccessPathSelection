-- Hotspot/skewed distribution variant.
-- Result table shape:
--   t_dist_hotspot(id BIGINT, a INTEGER, b DOUBLE), 10,000,000 rows.
--   80% of rows map into a narrow hotspot a-range; 20% spread over wider range.
-- Why this workload:
--   Captures skew effects where pruning/selectivity differs from uniform assumptions.
-- 80% of rows in a narrow range [0, 9,999], 20% in [10,000, 999,999].

DROP TABLE IF EXISTS t_dist_hotspot;

CREATE TABLE t_dist_hotspot AS
SELECT
    i::BIGINT AS id,
    CASE
        WHEN (i % 10) < 8 THEN (i % 10000)
        ELSE 10000 + (i % 990000)
    END::INTEGER AS a,
    (((i * 48271) % 10000) / 100.0)::DOUBLE AS b
FROM range(10000000) AS r(i);

ANALYZE t_dist_hotspot;
