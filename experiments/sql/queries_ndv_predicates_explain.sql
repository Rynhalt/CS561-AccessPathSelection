-- Fixed predicate suite for NDV experiment.
-- Metric collection: run these EXPLAIN ANALYZE queries after creating NDV tables.
-- Workloads required:
--   create_ndv_low.sql
--   create_ndv_medium.sql
--   create_ndv_high.sql
-- Why these queries are in the experiment:
--   Separate NDV effects from predicate-class effects (=, <, BETWEEN, conjunctive).
-- Controlled parameters (held constant):
--   Same row count/schema and same predicate classes across NDV tables.
-- Controlled parameters (varied):
--   NDV(a) and predicate class.
-- Metrics to collect from EXPLAIN ANALYZE:
--   Total latency per predicate class; scan timing; rows scanned/output.
--   If engine counters are enabled: row_groups_skipped, segments_skipped, vectors_processed.

-- Low NDV equality probe: many duplicates per key under NDV=100.
EXPLAIN ANALYZE SELECT count(*) AS low_eq FROM t_ndv_low WHERE a = 42;
-- Low NDV less-than probe.
EXPLAIN ANALYZE SELECT count(*) AS low_lt FROM t_ndv_low WHERE a < 20;
-- Low NDV range probe.
EXPLAIN ANALYZE SELECT count(*) AS low_between FROM t_ndv_low WHERE a BETWEEN 20 AND 29;
-- Low NDV conjunctive probe: adds b filter to same a range.
EXPLAIN ANALYZE SELECT count(*) AS low_conjunct FROM t_ndv_low WHERE a BETWEEN 20 AND 29 AND b >= 25.0;

-- Medium NDV equality probe.
EXPLAIN ANALYZE SELECT count(*) AS medium_eq FROM t_ndv_medium WHERE a = 4242;
-- Medium NDV less-than probe.
EXPLAIN ANALYZE SELECT count(*) AS medium_lt FROM t_ndv_medium WHERE a < 2000;
-- Medium NDV range probe.
EXPLAIN ANALYZE SELECT count(*) AS medium_between FROM t_ndv_medium WHERE a BETWEEN 3000 AND 3499;
-- Medium NDV conjunctive probe.
EXPLAIN ANALYZE SELECT count(*) AS medium_conjunct FROM t_ndv_medium WHERE a BETWEEN 3000 AND 3499 AND b >= 25.0;

-- High NDV equality probe: near point-selective regime.
EXPLAIN ANALYZE SELECT count(*) AS high_eq FROM t_ndv_high WHERE a = 424242;
-- High NDV less-than probe.
EXPLAIN ANALYZE SELECT count(*) AS high_lt FROM t_ndv_high WHERE a < 200000;
-- High NDV range probe.
EXPLAIN ANALYZE SELECT count(*) AS high_between FROM t_ndv_high WHERE a BETWEEN 300000 AND 349999;
-- High NDV conjunctive probe.
EXPLAIN ANALYZE SELECT count(*) AS high_conjunct FROM t_ndv_high WHERE a BETWEEN 300000 AND 349999 AND b >= 25.0;
