-- Fixed query suite for NDV experiment.
-- Metric collection: run these EXPLAIN ANALYZE queries after creating NDV tables.
-- Workloads required:
--   create_ndv_low.sql
--   create_ndv_medium.sql
--   create_ndv_high.sql
-- Why these queries are in the experiment:
--   Measure how filter-column cardinality (NDV) changes pruning and scan cost.
-- Controlled parameters (held constant):
--   Same row count, same schema, same query shape (count + single predicate).
-- Controlled parameters (varied):
--   NDV(a): 100, 10,000, 1,000,000; selectivity levels within each NDV regime.
-- Metrics to collect from EXPLAIN ANALYZE:
--   Total latency; scan timing; rows scanned/output per query.
--   If engine counters are enabled: row_groups_skipped, segments_skipped, vectors_processed.

-- Low NDV (~1%): a<1 out of 100 values.
EXPLAIN ANALYZE SELECT count(*) AS low_1_pct FROM t_ndv_low WHERE a < 1;
-- Low NDV (~5%): a<5 out of 100 values.
EXPLAIN ANALYZE SELECT count(*) AS low_5_pct FROM t_ndv_low WHERE a < 5;
-- Low NDV (~10%).
EXPLAIN ANALYZE SELECT count(*) AS low_10_pct FROM t_ndv_low WHERE a < 10;
-- Low NDV (~20%).
EXPLAIN ANALYZE SELECT count(*) AS low_20_pct FROM t_ndv_low WHERE a < 20;
-- Low NDV (~50%).
EXPLAIN ANALYZE SELECT count(*) AS low_50_pct FROM t_ndv_low WHERE a < 50;
-- Low NDV (~90%).
EXPLAIN ANALYZE SELECT count(*) AS low_90_pct FROM t_ndv_low WHERE a < 90;

-- Medium NDV (~1%): a<100 out of 10,000 values.
EXPLAIN ANALYZE SELECT count(*) AS medium_1_pct FROM t_ndv_medium WHERE a < 100;
-- Medium NDV (~5%).
EXPLAIN ANALYZE SELECT count(*) AS medium_5_pct FROM t_ndv_medium WHERE a < 500;
-- Medium NDV (~10%).
EXPLAIN ANALYZE SELECT count(*) AS medium_10_pct FROM t_ndv_medium WHERE a < 1000;
-- Medium NDV (~20%).
EXPLAIN ANALYZE SELECT count(*) AS medium_20_pct FROM t_ndv_medium WHERE a < 2000;
-- Medium NDV (~50%).
EXPLAIN ANALYZE SELECT count(*) AS medium_50_pct FROM t_ndv_medium WHERE a < 5000;
-- Medium NDV (~90%).
EXPLAIN ANALYZE SELECT count(*) AS medium_90_pct FROM t_ndv_medium WHERE a < 9000;

-- High NDV (~1%): a<10,000 out of 1,000,000 values.
EXPLAIN ANALYZE SELECT count(*) AS high_1_pct FROM t_ndv_high WHERE a < 10000;
-- High NDV (~5%).
EXPLAIN ANALYZE SELECT count(*) AS high_5_pct FROM t_ndv_high WHERE a < 50000;
-- High NDV (~10%).
EXPLAIN ANALYZE SELECT count(*) AS high_10_pct FROM t_ndv_high WHERE a < 100000;
-- High NDV (~20%).
EXPLAIN ANALYZE SELECT count(*) AS high_20_pct FROM t_ndv_high WHERE a < 200000;
-- High NDV (~50%).
EXPLAIN ANALYZE SELECT count(*) AS high_50_pct FROM t_ndv_high WHERE a < 500000;
-- High NDV (~90%).
EXPLAIN ANALYZE SELECT count(*) AS high_90_pct FROM t_ndv_high WHERE a < 900000;
