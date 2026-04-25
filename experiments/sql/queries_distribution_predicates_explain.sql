-- Fixed predicate suite for distribution experiment (uniform vs hotspot).
-- Metric collection: run these EXPLAIN ANALYZE queries after creating distribution tables.
-- Workloads required:
--   create_distribution_uniform.sql
--   create_distribution_hotspot.sql
-- Why these queries are in the experiment:
--   Quantify impact of data skew (hotspot) on access-path behavior.
-- Controlled parameters (held constant):
--   Same schema, row count, and predicate forms across both tables.
-- Controlled parameters (varied):
--   Data distribution of a: uniform vs hotspot.
--   Probe type: hotspot-key predicates vs non-hotspot-key predicates.
-- Metrics to collect from EXPLAIN ANALYZE:
--   Total latency; scan timing; rows scanned/output for each probe.
--   If engine counters are enabled: row_groups_skipped, segments_skipped, vectors_processed.

-- Q1
-- Uniform baseline for frequent-key probe: on uniform data, key 5000 should not be special.
EXPLAIN ANALYZE SELECT count(*) AS uniform_eq_hotspot_value FROM t_dist_uniform WHERE a = 5000;

-- Q2
-- Uniform baseline for rare-key probe: on uniform data, key 500000 should behave similarly to key 5000.
EXPLAIN ANALYZE SELECT count(*) AS uniform_eq_nonhotspot_value FROM t_dist_uniform WHERE a = 500000;

-- Q3
-- Uniform baseline for hotspot-band range: checks the same key range used as hotspot in skewed table.
EXPLAIN ANALYZE SELECT count(*) AS uniform_between_hotspot_band FROM t_dist_uniform WHERE a BETWEEN 0 AND 9999;

--Q4
-- Uniform baseline for non-hotspot band: compares a similarly sized range outside hotspot band.
EXPLAIN ANALYZE SELECT count(*) AS uniform_between_nonhotspot_band FROM t_dist_uniform WHERE a BETWEEN 500000 AND 509999;

--Q5
-- Skewed frequent-key probe: key 5000 lies in hotspot; should return many more rows than uniform.
EXPLAIN ANALYZE SELECT count(*) AS hotspot_eq_hotspot_value FROM t_dist_hotspot WHERE a = 5000;

--Q5
-- Skewed rare-key probe: key 500000 lies in tail; should return far fewer rows than hotspot key.
EXPLAIN ANALYZE SELECT count(*) AS hotspot_eq_nonhotspot_value FROM t_dist_hotspot WHERE a = 500000;

--Q6
-- Skewed hotspot-band range: captures dense 0..9999 region where 80% of rows concentrate.
EXPLAIN ANALYZE SELECT count(*) AS hotspot_between_hotspot_band FROM t_dist_hotspot WHERE a BETWEEN 0 AND 9999;

--Q7
-- Skewed non-hotspot band: same-width range in sparse tail, for direct contrast vs hotspot band.
EXPLAIN ANALYZE SELECT count(*) AS hotspot_between_nonhotspot_band FROM t_dist_hotspot WHERE a BETWEEN 500000 AND 509999;
 
