-- High-NDV variant for filter column a.
-- Result table shape:
--   t_ndv_high(id BIGINT, a INTEGER, b DOUBLE), 10,000,000 rows.
--   a has 1,000,000 distinct values, each repeating ~10x.
-- Why this workload:
--   High-cardinality regime where point/range predicates can be highly selective.
-- Default NDV(a): 1,000,000

DROP TABLE IF EXISTS t_ndv_high;

CREATE TABLE t_ndv_high AS
WITH params AS (
    SELECT 1000000::BIGINT AS ndv_a
)
SELECT
    i::BIGINT AS id,
    (i % p.ndv_a)::INTEGER AS a,
    (((i * 48271) % 10000) / 100.0)::DOUBLE AS b
FROM range(10000000) AS r(i)
CROSS JOIN params AS p;

ANALYZE t_ndv_high;
