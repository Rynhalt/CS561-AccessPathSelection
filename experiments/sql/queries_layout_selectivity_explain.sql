-- Fixed query suite for layout experiment (random vs sorted vs block-sorted).
-- Metric collection: run these EXPLAIN ANALYZE queries after creating layout tables.
-- Workloads required:
--   create_base_uniform.sql
--   create_layout_random.sql
--   create_layout_sorted.sql
--   create_layout_block_sorted.sql
-- Why these queries are in the experiment:
--   Isolate the effect of physical layout/clustering on access-path efficiency.
-- Controlled parameters (held constant):
--   Same schema, same row count, same value distribution of a, same predicate form.
-- Controlled parameters (varied):
--   Physical row ordering only: random vs sorted vs block-sorted.
-- Metrics to collect from EXPLAIN ANALYZE:
--   Total latency; scan operator timing; rows scanned/output.
--   If engine counters are enabled: row_groups_skipped, segments_skipped, vectors_processed.

-- Q8
-- Random layout at ~0.1% selectivity: baseline for very selective range under poor clustering.
EXPLAIN ANALYZE SELECT count(*) AS random_0_1_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 100999;
--Q9
-- Random layout at ~1% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_1_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 109999;
--Q10
-- Random layout at ~5% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_5_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 149999;
--Q11
-- Random layout at ~10% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_10_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 199999;
--Q12
-- Random layout at ~20% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_20_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 299999;
--Q13
-- Random layout at ~50% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_50_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 599999;
--Q14
-- Random layout at ~90% selectivity: near full-scan regime.
EXPLAIN ANALYZE SELECT count(*) AS random_90_pct FROM t_layout_random WHERE a BETWEEN 0 AND 899999;

--Q15
-- Sorted layout at ~0.1% selectivity: same predicate as above, but with strong clustering.
EXPLAIN ANALYZE SELECT count(*) AS sorted_0_1_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 100999;
--Q16
-- Sorted layout at ~1% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_1_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 109999;
--Q17
-- Sorted layout at ~5% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_5_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 149999;
--Q18
-- Sorted layout at ~10% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_10_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 199999;
--Q19
-- Sorted layout at ~20% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_20_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 299999;
--Q20
-- Sorted layout at ~50% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_50_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 599999;
--Q21
-- Sorted layout at ~90% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_90_pct FROM t_layout_sorted WHERE a BETWEEN 0 AND 899999;

--Q22
-- Block-sorted layout at ~0.1% selectivity: partial clustering between random and fully sorted.
EXPLAIN ANALYZE SELECT count(*) AS block_0_1_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 100999;
--Q23
-- Block-sorted layout at ~1% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_1_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 109999;
--Q24
-- Block-sorted layout at ~5% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_5_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 149999;
--Q25
-- Block-sorted layout at ~10% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_10_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 199999;
--Q26
-- Block-sorted layout at ~20% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_20_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 299999;
--Q27
-- Block-sorted layout at ~50% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_50_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 599999;
--Q28
-- Block-sorted layout at ~90% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_90_pct FROM t_layout_block_sorted WHERE a BETWEEN 0 AND 899999;
