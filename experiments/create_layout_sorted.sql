-- Fully sorted layout on the primary filter column.
-- Result table shape:
--   t_layout_sorted(id BIGINT, a INTEGER, b DOUBLE), same values as t_base.
--   Rows are globally ordered by a (then id), so nearby rows have similar a.
-- Why this workload:
--   High-clustering case where zonemap/segment pruning should be strongest.
-- Prerequisite: run create_base_uniform.sql first.

DROP TABLE IF EXISTS t_layout_sorted;

CREATE TABLE t_layout_sorted AS
SELECT *
FROM t_base
ORDER BY a, id;

ANALYZE t_layout_sorted;
