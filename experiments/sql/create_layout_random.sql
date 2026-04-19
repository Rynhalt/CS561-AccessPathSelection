-- Randomized physical layout derived from t_base.
-- Result table shape:
--   t_layout_random(id BIGINT, a INTEGER, b DOUBLE), same values as t_base.
--   Physical row order is shuffled by hash(id), reducing clustering on a.
-- Why this workload:
--   Acts as low-clustering case where zonemap pruning should be weaker.
-- Prerequisite: run create_base_uniform.sql first.

DROP TABLE IF EXISTS t_layout_random;

CREATE TABLE t_layout_random AS
SELECT *
FROM t_base
ORDER BY hash(id);

ANALYZE t_layout_random;
