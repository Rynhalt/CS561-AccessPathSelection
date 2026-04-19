-- Uniform distribution variant (same defaults as t_base).
-- Result table shape:
--   t_dist_uniform(id BIGINT, a INTEGER, b DOUBLE), 10,000,000 rows.
--   a is near-uniform over 0..999,999.
-- Why this workload:
--   Baseline distribution for comparison against skewed/hotspot workloads.

DROP TABLE IF EXISTS t_dist_uniform;

CREATE TABLE t_dist_uniform AS
WITH params AS (
    SELECT 10000000::BIGINT AS n_rows, 1000000::BIGINT AS ndv_a
)
SELECT
    i::BIGINT AS id,
    (i % (SELECT ndv_a FROM params))::INTEGER AS a,
    (((i * 48271) % 10000) / 100.0)::DOUBLE AS b
FROM range((SELECT n_rows FROM params)) AS r(i);

ANALYZE t_dist_uniform;
