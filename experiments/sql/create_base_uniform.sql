-- Base uniform synthetic table for access-path experiments.
-- Result table shape:
--   t_base(id BIGINT, a INTEGER, b DOUBLE), 10,000,000 rows.
--   id is unique and increasing; a cycles 0..999,999 (near-uniform, NDV=1,000,000);
--   b is deterministic pseudo-random-like in [0.00, 99.99].
-- Why this workload:
--   Stable baseline where selectivity on a is predictable and reproducible across runs.

DROP TABLE IF EXISTS t_base;

CREATE TABLE t_base AS
WITH params AS (
    SELECT 1000000::BIGINT AS ndv_a
)
SELECT
    i::BIGINT AS id,
    (i % p.ndv_a)::INTEGER AS a,
    (((i * 48271) % 10000) / 100.0)::DOUBLE AS b
FROM range(10000000) AS r(i)
CROSS JOIN params AS p;

ANALYZE t_base;
