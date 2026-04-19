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
    SELECT 10000000::BIGINT AS n_rows, 10000::BIGINT AS ndv_a
)
SELECT
    i::BIGINT AS id,
    (i % (SELECT ndv_a FROM params))::INTEGER AS a,
    (((i * 48271) % 10000) / 100.0)::DOUBLE AS b
FROM range((SELECT n_rows FROM params)) AS r(i);

ANALYZE t_ndv_medium;
