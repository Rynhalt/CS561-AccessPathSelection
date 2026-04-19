-- Partially clustered (block-sorted) layout.
-- Result table shape:
--   t_layout_block_sorted(id BIGINT, a INTEGER, b DOUBLE), same values as t_base.
--   Rows are ordered by coarse a buckets (width=10,000), then shuffled within bucket.
-- Why this workload:
--   Mid-clustering case between random and fully sorted to study pruning sensitivity.
-- Prerequisite: run create_base_uniform.sql first.

DROP TABLE IF EXISTS t_layout_block_sorted;

CREATE TABLE t_layout_block_sorted AS
WITH params AS (
    SELECT 10000::BIGINT AS a_block_width
)
SELECT *
FROM t_base
ORDER BY (a / (SELECT a_block_width FROM params)), hash(id);

ANALYZE t_layout_block_sorted;
