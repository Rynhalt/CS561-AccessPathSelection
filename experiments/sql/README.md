# Synthetic SQL Workloads for Access-Path Experiments

This folder is organized so each experiment is reproducible as a fixed set of:
- workload creation files (`create_*.sql`)
- fixed query files (`queries_*_explain.sql`)

The goal is to isolate one parameter at a time and measure access-path behavior (latency, scan timing, rows scanned/output, and your internal counters when enabled).

All workload generation scripts default to `N = 10,000,000` rows.

## What Is Controlled vs Varied

Across experiments, we keep these stable unless explicitly varied:
- schema: `id BIGINT, a INTEGER, b DOUBLE`
- row count: 10M
- deterministic data generation
- query forms used inside each experiment set

This makes differences in `EXPLAIN ANALYZE` attributable to the intended parameter change.

## Experiment Grouping

### 1) Layout x Selectivity Experiment

Files asociated with this experiment:
- `create_base_uniform.sql`
- `create_layout_random.sql`
- `create_layout_sorted.sql`
- `create_layout_block_sorted.sql`
- `queries_layout_selectivity_explain.sql`

Controlled parameter purpose:
- Varied: physical layout only (`random`, `sorted`, `block-sorted`).
- Held constant: value distribution of `a`, row count, predicate family (range filters), schema.

This experiment:
- Isolates how clustering affects pruning efficiency.
- Same selectivity probes are run on each layout, so we can directly compare whether speedups come from skipping more work (and, later, from counter movement).

What query file does:
- `queries_layout_selectivity_explain.sql` runs fixed range predicates from very selective to near full-scan.
- This reveals where layout-sensitive pruning helps most.

### 2) NDV (Cardinality) Experiment

Files associated with this experiment:
- `create_ndv_low.sql`
- `create_ndv_medium.sql`
- `create_ndv_high.sql`
- `queries_ndv_selectivity_explain.sql`
- `queries_ndv_predicates_explain.sql`

Controlled parameter purpose:
- Varied: cardinality of filter column `a` (NDV = 100, 10,000, 1,000,000).
- Held constant: row count, schema, deterministic generation style, query families.

This experiment:
- isolates how key cardinality changes selectivity behavior and pruning opportunities.
- We can compare whether the same predicate class behaves differently when each key is very frequent (low NDV) vs sparse (high NDV).

What query files do:
- `queries_ndv_selectivity_explain.sql`: fixed selectivity ladder inside each NDV regime.
- `queries_ndv_predicates_explain.sql`: fixed predicate classes (`=`, `<`, `BETWEEN`, conjunctive) across NDV regimes.

### 3) Distribution (Uniform vs Hotspot) Experiment

Files associated with this experiment:
- `create_distribution_uniform.sql`
- `create_distribution_hotspot.sql`
- `queries_distribution_predicates_explain.sql`

Controlled parameter purpose:
- Varied: distribution shape of `a` (uniform vs hotspot skew).
- Held constant: schema, row count, predicate forms, table construction style.

This experiment:
- Isolates skew effects: frequent keys/ranges vs tail keys/ranges.
- This is useful for understanding when observed latency differences come from data concentration rather than just total table size.

What query file does:
- `queries_distribution_predicates_explain.sql` runs matched probes for hotspot and non-hotspot values/ranges on both tables.
- This gives direct side-by-side evidence of skew impact.

## Reproducibility Notes

- `ANALYZE` is included in every creation file so optimizer stats are present.
- Data generation is deterministic; reruns recreate the same data distributions.
- Query suites are fixed and documented per-query to avoid ad-hoc drift.
- If comparing access paths, keep session flags and DuckDB build constant across runs.
