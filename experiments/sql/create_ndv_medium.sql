-- Medium-NDV variant for filter column a.
-- Result table shape:
--   t_ndv_medium(id BIGINT, a INTEGER, b DOUBLE), 10,000,000 rows.
--   a has 10,000 distinct values, each repeating ~1,000x.
-- Why this workload:
--   Middle ground between low/high NDV to show where pruning transitions happen.
-- Default NDV(a): 10,000

DROP TABLE IF EXISTS t_ndv_medium;

CREATE TABLE t_ndv_medium AS
WITH params AS (
    SELECT 10000::BIGINT AS ndv_a
)
SELECT
    i::BIGINT AS id,
    (i % p.ndv_a)::INTEGER AS a,
    (((i * 48271) % 10000) / 100.0)::DOUBLE AS b
FROM range(10000000) AS r(i)
CROSS JOIN params AS p;

ANALYZE t_ndv_medium;
