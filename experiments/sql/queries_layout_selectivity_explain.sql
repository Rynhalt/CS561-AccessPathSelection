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

-- Random layout at ~0.1% selectivity: baseline for very selective range under poor clustering.
EXPLAIN ANALYZE SELECT count(*) AS random_0_1_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 100999;
-- Random layout at ~1% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_1_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 109999;
-- Random layout at ~5% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_5_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 149999;
-- Random layout at ~10% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_10_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 199999;
-- Random layout at ~20% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_20_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 299999;
-- Random layout at ~50% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS random_50_pct FROM t_layout_random WHERE a BETWEEN 100000 AND 599999;
-- Random layout at ~90% selectivity: near full-scan regime.
EXPLAIN ANALYZE SELECT count(*) AS random_90_pct FROM t_layout_random WHERE a BETWEEN 0 AND 899999;

-- Sorted layout at ~0.1% selectivity: same predicate as above, but with strong clustering.
EXPLAIN ANALYZE SELECT count(*) AS sorted_0_1_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 100999;
-- Sorted layout at ~1% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_1_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 109999;
-- Sorted layout at ~5% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_5_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 149999;
-- Sorted layout at ~10% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_10_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 199999;
-- Sorted layout at ~20% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_20_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 299999;
-- Sorted layout at ~50% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_50_pct FROM t_layout_sorted WHERE a BETWEEN 100000 AND 599999;
-- Sorted layout at ~90% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS sorted_90_pct FROM t_layout_sorted WHERE a BETWEEN 0 AND 899999;

-- Block-sorted layout at ~0.1% selectivity: partial clustering between random and fully sorted.
EXPLAIN ANALYZE SELECT count(*) AS block_0_1_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 100999;
-- Block-sorted layout at ~1% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_1_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 109999;
-- Block-sorted layout at ~5% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_5_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 149999;
-- Block-sorted layout at ~10% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_10_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 199999;
-- Block-sorted layout at ~20% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_20_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 299999;
-- Block-sorted layout at ~50% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_50_pct FROM t_layout_block_sorted WHERE a BETWEEN 100000 AND 599999;
-- Block-sorted layout at ~90% selectivity.
EXPLAIN ANALYZE SELECT count(*) AS block_90_pct FROM t_layout_block_sorted WHERE a BETWEEN 0 AND 899999;
