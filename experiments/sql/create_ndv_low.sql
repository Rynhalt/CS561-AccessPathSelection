-- Low-NDV variant for filter column a.
-- Result table shape:
--   t_ndv_low(id BIGINT, a INTEGER, b DOUBLE), 10,000,000 rows.
--   a has only 100 distinct values, so each value repeats very heavily (~100,000x).
-- Why this workload:
--   Tests behavior when predicates are coarse and many rows match each key.
-- Default NDV(a): 100

DROP TABLE IF EXISTS t_ndv_low;

CREATE TABLE t_ndv_low AS
WITH params AS (
    SELECT 100::BIGINT AS ndv_a
)
SELECT
    i::BIGINT AS id,
    (i % p.ndv_a)::INTEGER AS a,
    (((i * 48271) % 10000) / 100.0)::DOUBLE AS b
FROM range(10000000) AS r(i)
CROSS JOIN params AS p;

ANALYZE t_ndv_low;
