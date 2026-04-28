# Final Codebase and Experiment Summary

Project: **Access Path Selection in Modern Columnar DBMSs**

Scope note: this report focuses on the customized DuckDB implementation and the synthetic workload experiments in this repository. Per the current instruction, the RABIT / bitmap prototype is not analyzed here. I did search for RABIT/bitmap-specific project files and did not find an integrated DuckDB RABIT implementation in this repository.

## 1. Executive Summary

The final project state is a customized DuckDB fork for studying scan-pruning access paths in a columnar DBMS. The DuckDB-side comparison focuses on zonemap pruning and column-sketch pruning. The implementation adds runtime flags, scan-level instrumentation, generalized sketch construction for synthetic workloads, and Python experiment runners that execute fixed SQL workloads under controlled access-path modes.

The most defensible final comparison is **row-group zonemap + segment zonemap** versus **row-group zonemap + column sketch**. This holds row-group pruning fixed and compares only the column-segment-level method. The results in `experiments/results/explain_metrics_summary.csv` show that sketch pruning often reduces `vectors_processed` more than segment zonemaps, especially under medium/high NDV and selective predicates. However, latency only improves when the scan work saved is large enough to offset sketch-evaluation overhead. Predicate-type results also show that vector reduction and latency can diverge.

## 2. Repository / Codebase Overview

### Core DuckDB Source Files

| Path | Purpose | Status |
| --- | --- | --- |
| `src/include/duckdb/storage/table/scan_state.hpp` | Adds `TableScanOptions` flags and `TableScanMetrics` counters used during scans. | Project-modified DuckDB source |
| `src/function/table/table_scan.cpp` | Propagates client flags into scan state and prints scan metrics in `SEQ_SCAN` extra info. | Project-modified DuckDB source |
| `src/storage/table/row_group.cpp` | Implements row-group zonemap pruning, segment zonemap pruning, segment sketch pruning, vector counting, and sketch append construction. | Project-modified DuckDB source |
| `src/include/duckdb/storage/table/row_group.hpp` | Declares `CheckZonemapSegments`, `CheckSketchSegments`, and `sketchAppend`. | Project-modified DuckDB source |
| `src/storage/table/row_group_collection.cpp` | Routes append into regular append or sketch-aware append. | Project-modified DuckDB source |
| `src/storage/data_table.cpp` | Chooses sketchable numeric columns during normal append and calls `row_groups->sketchAppend`. | Project-modified DuckDB source |
| `src/storage/local_storage.cpp` | Applies the same sketchable-column selection for local storage append. | Project-modified DuckDB source |
| `src/include/duckdb/storage/table/column_data.hpp` | Adds per-column `segment_sketches`, `is_sketched`, and `vector_sels`; declares `CheckSketch`. | Project-modified DuckDB source |
| `src/storage/table/standard_column_data.cpp` | Implements `StandardColumnData::CheckSketch`. | Project-modified DuckDB source |
| `src/include/duckdb/storage/statistics/numeric_stats.hpp` | Declares numeric sketch checking. | Project-modified DuckDB source |
| `src/storage/statistics/numeric_stats.cpp` | Implements sketch pruning for numeric predicates and order-preserving DOUBLE encoding. | Project-modified DuckDB source |
| `src/planner/filter/constant_filter.cpp` | Routes constant numeric filters to `NumericStats::CheckSketch`. | Project-modified DuckDB source |
| `src/planner/filter/conjunction_filter.cpp` | Extends conjunction filters to use sketch-aware checks and merge selection masks. | Project-modified DuckDB source |
| `src/include/duckdb/planner/table_filter.hpp` | Adds virtual `CheckSketchStatistics`. | Project-modified DuckDB source |
| `src/include/duckdb/main/client_config.hpp` | Adds client config booleans for access-path flags. | Project-modified DuckDB source |
| `src/include/duckdb/main/settings.hpp` | Declares SQL-visible settings: `disable_sketch`, `disable_zonemap`, `disable_segment_zonemap`. | Project-modified DuckDB source |
| `src/main/settings/settings.cpp` | Implements setting get/set/reset logic. | Project-modified DuckDB source |
| `src/main/query_profiler.cpp` | Refreshes operator `extra_info` before profiler rendering so scan metrics appear in `EXPLAIN ANALYZE`. | Project-modified DuckDB source |

### Experiment and Reporting Files

| Path | Purpose | Status |
| --- | --- | --- |
| `experiments/sql/*.sql` | Synthetic workload creation and fixed `EXPLAIN ANALYZE` query suites. | Project-added experiment assets |
| `experiments/run_explain_suite.py` | Runs one or more suites through the DuckDB CLI, parses profiler metrics, writes per-run and summary CSVs. | Project-added experiment runner |
| `experiments/run_explain_workflow.py` | Chunked workflow driver that runs suite/query/mode/run chunks, supports resuming/skipping completed work, and merges CSV outputs. | Project-added experiment runner |
| `experiments/plot_access_path_analysis.py` | Reads summary CSVs and generates final plots focused on `rowgroup_plus_segment_zonemap` vs `rowgroup_plus_sketch`. | Project-added plotting script |
| `experiments/results/explain_metrics_runs.csv` | Cumulative per-run metrics. | Generated result |
| `experiments/results/explain_metrics_summary.csv` | Cumulative per-query/per-mode averages. Preferred result file for final analysis. | Generated result |
| `experiments/results/explain_metrics_summary_{suite}.csv` | Per-suite summary CSVs. | Generated result |
| `experiments/results/explain_metrics_failures.csv` | Failed chunks, mainly from instability around some conjunctive sketch/full runs. | Generated diagnostic result |
| `plots/*/*.svg` | Generated final plots. | Generated figures |
| `experiments/ACCESS_PATH_EXPERIMENT_ANALYSIS_REPORT.md` | Presentation-oriented analysis report using actual CSV outputs. | Project-added documentation |
| `experiments/EXPERIMENT_DESIGN_AND_ANALYSIS.md` | Broader experimental design document. | Project-added documentation |
| `final_report_codebase_summary.md` | This file. | Project-added documentation |

## 3. DuckDB Storage and Scan Model Used in This Project

The relevant storage/execution hierarchy is:

```text
Table
  -> RowGroup                         horizontal chunk of rows
       -> ColumnData for column a
            -> ColumnSegment
            -> ColumnSegment
            -> ...
       -> ColumnData for column b
            -> ColumnSegment
            -> ...

Scan execution
  -> reads stored column segments
  -> produces runtime vectors
  -> applies filters and operators on vectors
```

Code-grounding:

- `RowGroup` stores `vector<shared_ptr<ColumnData>> columns` in `src/include/duckdb/storage/table/row_group.hpp`.
- `ColumnData` stores `ColumnSegmentTree data` in `src/include/duckdb/storage/table/column_data.hpp`.
- `ColumnSegment` is defined in `src/include/duckdb/storage/table/column_segment.hpp` and inherits `start`, `count`, `next`, and `index` from `SegmentBase`.
- `SegmentTree` is described as maintaining all segments of a specific column and searching by row number in `src/include/duckdb/storage/table/segment_tree.hpp`.

Important project constants/interpretation:

- A row group is a horizontal chunk of rows.
- In this setup, one full row group is approximately `122,880` rows.
- DuckDB vectors are runtime execution batches, not storage units.
- One vector is up to `2,048` rows (`STANDARD_VECTOR_SIZE`).
- `122,880 / 2,048 = 60`, so one full row group corresponds to about 60 vector-sized chunks.
- In the fixed-width numeric synthetic workloads, column segments are effectively around vector-sized, so one column in a full row group commonly has about 60 column segments. The exact count is stored in the column's `ColumnSegmentTree`, and each segment has its own `segment->count`.

Why this matters:

- **Row-group pruning** skips a whole row group: roughly 122,880 rows across all columns.
- **Segment-level pruning** skips smaller per-column storage pieces inside a surviving row group.
- **Vectors processed** counts runtime scan batches that survive pruning. Lower `vectors_processed` means less vectorized scan work reached the normal scan/filter path.

## 4. Access Path Logic in DuckDB

### Row-Group Zonemap Pruning

Relevant files/functions:

- `src/storage/table/row_group.cpp`
- `RowGroup::InitializeScan`
- `RowGroup::InitializeScanWithOffset`
- `RowGroup::CheckZonemap`

`InitializeScan` and `InitializeScanWithOffset` call `CheckZonemap` before scanning a row group. If it returns false, the row group is skipped and `row_groups_pruned_by_zonemap` is incremented.

Core logic:

```cpp
if (filters) {
    if (!CheckZonemap(*filters, column_ids, state.GetOptions())) {
        metrics->row_groups_pruned_by_zonemap++;
        return false;
    }
}
```

`RowGroup::CheckZonemap` explicitly respects `disable_zonemap`:

```cpp
if (options.disable_zonemap) {
    return true;
}
```

Therefore, `disable_zonemap=true` disables row-group zonemap pruning.

### Segment-Level Zonemap Pruning

Relevant function:

- `RowGroup::CheckZonemapSegments`

This function checks filter columns against segment statistics through:

```cpp
GetColumn(base_column_idx).CheckZonemap(state.column_scans[column_idx], *entry.second)
```

If the segment cannot contain qualifying values, it increments:

```cpp
metrics->segments_pruned_by_zonemap++;
```

Then it advances `state.vector_index` toward the next vector that might need scanning.

### Segment-Level Column Sketch Pruning

Relevant functions:

- `RowGroup::CheckSketchSegments`
- `StandardColumnData::CheckSketch`
- `ConstantFilter::CheckSketchStatistics`
- `ConjunctionAndFilter::CheckSketchStatistics`
- `NumericStats::CheckSketch`

`CheckSketchSegments` calls:

```cpp
GetColumn(base_column_idx).CheckSketch(state.column_scans[column_idx], *entry.second, state.vector_index)
```

If sketch metadata proves the current segment cannot contain qualifying values, it increments:

```cpp
metrics->segments_pruned_by_sketch++;
```

and advances the scan.

### Final Scan Flow

The final scan flow is:

1. SQL query is planned into a physical table scan.
2. Table scan local state receives runtime flags from `ClientConfig` in `table_scan.cpp`.
3. `RowGroup::InitializeScan` checks row-group zonemaps first.
4. If the row group is skipped, no segment-level method is used.
5. If the row group survives, `RowGroup::TemplatedScan` evaluates segment-level pruning.
6. Segment-level method is:
   - sketch, if sketch is enabled and all filtered columns have sketches, or
   - segment zonemap fallback, if sketch is not usable and segment zonemap is not disabled.
7. Remaining data is processed as execution vectors.

The key decision in `RowGroup::TemplatedScan`:

```cpp
bool can_sketch = !scan_options.disable_sketch;
...
if (can_sketch) {
    check_result = CheckSketchSegments(state);
} else if (!scan_options.disable_segment_zonemap) {
    check_result = CheckZonemapSegments(state);
}
```

Crucial clarification:

- Row-group pruning is zonemap-based.
- Column sketches are not used for row-group pruning.
- Column sketches are used at the column-segment level.
- The final experiments fix row-group pruning and compare segment-level zonemap versus segment-level sketch.

## 5. Runtime Flags and Configuration Changes

### `disable_sketch`

- Defined in `src/include/duckdb/main/settings.hpp` as `DisableSketchSetting`.
- Stored in `ClientConfig` as `bool disable_sketch = false`.
- Copied into `TableScanOptions.disable_sketch` in `src/function/table/table_scan.cpp`.
- Default: `false`.
- CLI usage:

```sql
SET disable_sketch = true;
SET disable_sketch = false;
```

Effect:

- `true`: prevents sketch segment pruning from being selected.
- `false`: allows sketch pruning if filtered columns have sketch metadata.
- If sketch is disabled, scan can fall back to segment zonemap unless `disable_segment_zonemap=true`.

### `disable_zonemap`

- Defined in `src/include/duckdb/main/settings.hpp` as `DisableZonemapSetting`.
- Stored in `ClientConfig` as `bool disable_zonemap = false`.
- Copied into `TableScanOptions.disable_zonemap`.
- Default: `false`.
- CLI usage:

```sql
SET disable_zonemap = true;
SET disable_zonemap = false;
```

Effect:

- `true`: disables row-group zonemap pruning in `RowGroup::CheckZonemap`.
- It does **not** directly control segment-level zonemap pruning in the final flag design.

### `disable_segment_zonemap`

- Defined in `src/include/duckdb/main/settings.hpp` as `DisableSegmentZonemapSetting`.
- Stored in `ClientConfig` as `bool disable_segment_zonemap = false`.
- Copied into `TableScanOptions.disable_segment_zonemap`.
- Default: `false`.
- CLI usage:

```sql
SET disable_segment_zonemap = true;
SET disable_segment_zonemap = false;
```

Effect:

- `true`: disables segment-level zonemap fallback in `RowGroup::TemplatedScan`.
- This enables the clean comparison where row-group pruning remains on but segment zonemap is off and sketch is on.

### Experimental Modes

`experiments/run_explain_suite.py` defines:

```python
FLAG_MODES = {
    "full": (False, False, False),
    "zonemap_only": (False, False, True),
    "segment_zonemap_only": (True, False, True),
    "sketch_only": (True, True, False),
    "none": (True, True, True),
    "rowgroup_only": (False, True, True),
    "rowgroup_plus_segment_zonemap": (False, False, True),
    "rowgroup_plus_sketch": (False, True, False),
}
```

The tuple is:

```text
(disable_zonemap, disable_segment_zonemap, disable_sketch)
```

The main final comparison is:

```text
rowgroup_plus_segment_zonemap = row-group zonemap on, segment zonemap on, sketch off
rowgroup_plus_sketch          = row-group zonemap on, segment zonemap off, sketch on
```

This holds row-group pruning fixed.

Caveat: the current cumulative `experiments/results/explain_metrics_summary.csv` contains seven modes and does not include `segment_zonemap_only`; only a small smoke-test CSV exists for that mode.

## 6. Column Sketch Availability and Final Fix

### Original Issue

Early experiments suggested sketches might not be running or not helping. The root cause was that the BU DISC lab implementation we started from did not make column sketches generally available for arbitrary synthetic tables and columns. Sketches were effectively available for the TPC-H `lineitem` table and only a subset of columns:

```text
l_quantity
l_extendedprice
l_discount
l_tax
l_shipdate
```

Queries involving other tables or other filter columns would not have sketch metadata available and would therefore fall back to zonemap-based pruning. This made early experiments misleading: a query could be run in a nominal "sketch" configuration while the scan path was not actually using sketch pruning for the predicate column.

The final scan code also shows the runtime condition that caused this fallback:

- Sketch pruning is only selected if `can_sketch` remains true in `RowGroup::TemplatedScan`.
- `can_sketch` requires table filters to exist and every filtered column to satisfy `col_data.is_sketched`.
- If any filtered column lacks sketch metadata, the scan falls back to segment zonemap, unless segment zonemap is disabled.

Final logic:

```cpp
bool can_sketch = !scan_options.disable_sketch;
if (can_sketch && table_filters) {
    for (auto &entry : table_filters->filters) {
        auto &col_data = GetColumn(column);
        if (!col_data.is_sketched) {
            can_sketch = false;
            break;
        }
    }
} else if (can_sketch && !table_filters) {
    can_sketch = false;
}
```

The important fix is that sketch eligibility now depends on **filtered columns**, not all scanned/projected columns. That is correct for pruning because only predicate columns need sketch metadata.

### Generalized Sketch Construction

Sketch construction is now routed through normal append paths:

- `src/storage/data_table.cpp`
- `src/storage/local_storage.cpp`
- `src/storage/table/row_group_collection.cpp`
- `src/storage/table/row_group.cpp`

Both `DataTable::Append` and `LocalStorage::Append` now identify sketchable numeric columns:

```cpp
if (physical_type == PhysicalType::INT32 || physical_type == PhysicalType::UINT32 ||
    physical_type == PhysicalType::INT64 || physical_type == PhysicalType::UINT64 ||
    physical_type == PhysicalType::DOUBLE) {
    sketch_col_idxs.push_back(NumericCast<int>(col_idx));
}
```

If any sketchable columns exist, append calls `row_groups->sketchAppend`.

`RowGroup::sketchAppend` appends the data and builds one sketch per appended segment/vector for eligible column types:

- `INT32` / `UINT32` -> `ColumnSketchWrapper<uint32_t, uint8_t>`
- `INT64` / `UINT64` -> `ColumnSketchWrapper<uint64_t, uint8_t>`
- `DOUBLE` -> order-preserving `uint64_t` encoding, then `ColumnSketchWrapper<uint64_t, uint8_t>`

Relevant snippet for DOUBLE:

```cpp
all_data.push_back(EncodeOrderedDouble(sdata[i]));
auto sketch = std::make_shared<ColumnSketchWrapper<uint64_t, uint8_t>>(all_data);
```

This avoids making `ColumnSketchWrapper` generic over floating point directly. `src/include/duckdb/storage/statistics/column_sketch.hpp` defines `ColumnSketchWrapper` and `BaseColumnSketch`; `NumericStats::CheckSketch` also encodes DOUBLE constants before probing sketches.

### Final Claim

The final system can force/enable column-sketch segment pruning on the synthetic workloads used in the final experiments. This is verified by:

- code paths that build sketches for numeric columns during append,
- `is_sketched` checks in `RowGroup::TemplatedScan`,
- nonzero `segments_pruned_by_sketch` values in the CSV outputs, and
- lower `vectors_processed` under `rowgroup_plus_sketch` for many workloads.

Caveat: sketch persistence across database restarts/checkpoints is not fully established from the inspected code. The experiments create and query tables in the same workflow, so the append-built sketch metadata is available for those runs.

## 7. Instrumentation and Metrics

Metrics are defined in `TableScanMetrics` in `src/include/duckdb/storage/table/scan_state.hpp`:

```cpp
atomic<idx_t> row_groups_pruned_by_zonemap;
atomic<idx_t> segments_pruned_by_zonemap;
atomic<idx_t> segments_pruned_by_sketch;
atomic<idx_t> vectors_processed;
```

### `row_groups_pruned_by_zonemap`

- Incremented in `RowGroup::InitializeScan` and `InitializeScanWithOffset`.
- Means a whole row group was skipped by row-group zonemap statistics.
- Appears in `SEQ_SCAN` extra info and CSVs.
- Important because it measures coarse pruning.

### `segments_pruned_by_zonemap`

- Incremented in `RowGroup::CheckZonemapSegments`.
- Means a segment-level zonemap check skipped a column segment / vector-sized scan range.
- In the final focused modes, this is often zero, indicating segment zonemap adds little beyond row-group pruning for these workloads.

### `segments_pruned_by_sketch`

- Incremented in `RowGroup::CheckSketchSegments`.
- Means a segment-level sketch check skipped a segment / vector-sized scan range.
- High values generally correspond to lower `vectors_processed`, but latency may still depend on overhead.

### `vectors_processed`

- Incremented in `RowGroup::TemplatedScan` after segment pruning and transaction visibility checks, before vector scanning.
- Means an execution vector reached scan/filter processing.
- One vector is up to `2,048` rows.
- This is the main internal measure of remaining scan work.

### Display and Parsing

`src/function/table/table_scan.cpp` formats these counters in `TableScanToString`, so they appear on `SEQ_SCAN` in `EXPLAIN ANALYZE`.

`src/main/query_profiler.cpp` refreshes operator `extra_info` both at `EndQuery` and during rendering:

```cpp
const_cast<QueryProfiler *>(this)->RefreshExtraInfo(*root);
Render(*root, ss);
```

This was necessary because counters could be updated correctly but displayed as zero if extra info was rendered before it was refreshed.

The Python parser normalizes box-drawing output before matching labels. This is important because long labels wrap in ASCII profiler output.

## 8. Workload Generation

All final DuckDB workloads are SQL files under `experiments/sql/`.

### Base Schema

Most synthetic tables use:

```sql
id BIGINT,
a  INTEGER,
b  DOUBLE
```

with `10,000,000` rows. `a` is the main filter column. `b` is used for conjunctive predicates.

Base generation:

```sql
i::BIGINT AS id,
(i % ndv_a)::INTEGER AS a,
(((i * 48271) % 10000) / 100.0)::DOUBLE AS b
```

Synthetic data is used because it provides precise, repeatable control over selectivity, cardinality, layout, distribution, and predicate type.

### Layout Sensitivity

Files:

- `create_base_uniform.sql`
- `create_layout_random.sql`
- `create_layout_sorted.sql`
- `create_layout_block_sorted.sql`
- `queries_layout_selectivity_explain.sql`

Tables:

- `t_base`: 10M rows, `a` cycles over 1,000,000 values.
- `t_layout_random`: same values as base, ordered by `hash(id)`.
- `t_layout_sorted`: same values, ordered by `a, id`.
- `t_layout_block_sorted`: same values, ordered by coarse `a` buckets of width 10,000, then `hash(id)`.

Queries:

- Range predicates over `a`.
- Selectivity levels: approximately `0.1%`, `1%`, `5%`, `10%`, `20%`, `50%`, `90%`.

### NDV / Cardinality

Files:

- `create_ndv_low.sql`
- `create_ndv_medium.sql`
- `create_ndv_high.sql`
- `queries_ndv_selectivity_explain.sql`

Tables:

- `t_ndv_low`: 10M rows, `NDV(a)=100`, each value repeats about 100,000 times.
- `t_ndv_medium`: 10M rows, `NDV(a)=10,000`, each value repeats about 1,000 times.
- `t_ndv_high`: 10M rows, `NDV(a)=1,000,000`, each value repeats about 10 times.

Queries:

- `a < threshold`
- Selectivities: `1%`, `5%`, `10%`, `20%`, `50%`, `90%`.

### Predicate Type

File:

- `queries_ndv_predicates_explain.sql`

Predicate classes:

- equality, e.g. `a = 4242`
- less-than, e.g. `a < 2000`
- between, e.g. `a BETWEEN 3000 AND 3499`
- conjunctive, e.g. `a BETWEEN 3000 AND 3499 AND b >= 25.0`

These run across low, medium, and high NDV tables.

### Distribution / Skew

Files:

- `create_distribution_uniform.sql`
- `create_distribution_hotspot.sql`
- `queries_distribution_predicates_explain.sql`

Tables:

- `t_dist_uniform`: uniform-like `a` over 0..999,999.
- `t_dist_hotspot`: 80% of rows in `a` range `[0, 9999]`, 20% over `[10000, 999999]`.

Queries include equality and between probes both inside and outside the hotspot region.

## 9. Experiment Runner Scripts

### `experiments/run_explain_suite.py`

Purpose:

- Run one or more fixed SQL suites with a chosen DuckDB binary.
- Create workload tables.
- Run `EXPLAIN ANALYZE` queries under access-path modes.
- Parse latency and scan metrics.
- Write per-run and summary CSVs.

Default DuckDB binary:

```text
build/release/duckdb
```

Example:

```bash
python3 experiments/run_explain_suite.py --suite ndv_selectivity --mode rowgroup_plus_sketch --repetitions 10
```

The script sends SQL to the CLI and prepends:

```sql
SET threads=<threads>;
```

For each mode/query/run it emits:

```sql
SET disable_zonemap=...;
SET disable_segment_zonemap=...;
SET disable_sketch=...;
EXPLAIN ANALYZE ...
```

### `experiments/run_explain_workflow.py`

Purpose:

- Chunked/resumable top-level workflow.
- Runs one suite/query/mode/run at a time by invoking `run_explain_suite.py`.
- Writes durable chunk CSVs under `experiments/results/chunks`.
- Merges per-suite and cumulative CSVs.
- Supports `--skip-completed-suites` and `--skip-failed-chunks`.

Example:

```bash
python3 experiments/run_explain_workflow.py --skip-completed-suites --threads 1
```

Threading:

- Scripts set DuckDB `threads`.
- They also set environment variables like `OMP_NUM_THREADS`, `OPENBLAS_NUM_THREADS`, etc., to avoid using more CPUs than requested on a shared cluster.

## 10. CSV Outputs and Result Files

Primary result files:

| Path | Type | Description |
| --- | --- | --- |
| `experiments/results/explain_metrics_runs.csv` | Raw/per-run | One row per suite/query/mode/run. |
| `experiments/results/explain_metrics_summary.csv` | Summary | Average per suite/query/mode. Preferred input for plots/report. |
| `experiments/results/explain_metrics_runs_layout_selectivity.csv` | Raw/per-run | Layout suite only. |
| `experiments/results/explain_metrics_summary_layout_selectivity.csv` | Summary | Layout suite only. |
| `experiments/results/explain_metrics_runs_ndv_selectivity.csv` | Raw/per-run | NDV/selectivity suite only. |
| `experiments/results/explain_metrics_summary_ndv_selectivity.csv` | Summary | NDV/selectivity suite only. |
| `experiments/results/explain_metrics_runs_ndv_predicates.csv` | Raw/per-run | NDV predicate suite only. |
| `experiments/results/explain_metrics_summary_ndv_predicates.csv` | Summary | NDV predicate suite only. |
| `experiments/results/explain_metrics_runs_distribution_predicates.csv` | Raw/per-run | Distribution suite only. |
| `experiments/results/explain_metrics_summary_distribution_predicates.csv` | Summary | Distribution suite only. |
| `experiments/results/explain_metrics_failures.csv` | Diagnostics | Failed chunks and stderr/stdout. |
| `experiments/results/segment_zm_smoke_*.csv` | Smoke test | Small segment-zonemap-only smoke result, not part of main cumulative analysis. |

Raw CSV columns:

```text
suite, query_name, disable_zonemap, disable_segment_zonemap, disable_sketch,
mode, run, total_time_s, row_groups_pruned_by_zonemap,
segments_pruned_by_zonemap, segments_pruned_by_sketch, vectors_processed
```

Summary CSV columns:

```text
suite, query_name, mode, disable_zonemap, disable_segment_zonemap,
disable_sketch, runs, avg_total_time_s,
avg_row_groups_pruned_by_zonemap, avg_segments_pruned_by_zonemap,
avg_segments_pruned_by_sketch, avg_vectors_processed
```

Current `explain_metrics_summary.csv` contains:

- 413 summary rows.
- Suites: `layout_selectivity` (147), `ndv_selectivity` (126), `ndv_predicates` (84), `distribution_predicates` (56).
- Modes: `full`, `none`, `rowgroup_only`, `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`, `sketch_only`, `zonemap_only`.

## 11. Plotting / Graph Generation Scripts

### `experiments/plot_access_path_analysis.py`

Input:

```text
experiments/results/explain_metrics_summary.csv
```

Output:

```text
plots/selectivity/{vectors_processed,latency}.svg
plots/layout/{vectors_processed,latency}.svg
plots/ndv/{vectors_processed,latency}.svg
plots/distribution/{vectors_processed,latency}.svg
plots/predicate/{vectors_processed,latency}.svg
plots/focused/{vectors_processed,latency}.svg
```

Libraries:

- Primary path: pandas + matplotlib.
- Fallback path: standard-library SVG generation when those packages are unavailable.

Filtering:

```python
MODES = ("rowgroup_plus_segment_zonemap", "rowgroup_plus_sketch")
```

Aggregation logic:

- Layout plot: averages all selectivity queries per layout.
- NDV plot: averages all selectivity queries per NDV level.
- Distribution plot: averages all distribution queries per distribution. Caveat: this mixes hotspot-region and non-hotspot-region probes.
- Predicate plot: averages low/medium/high NDV for each predicate type.
- Focused plot: medium-NDV selectivity points kept separate.
- Selectivity plot: block-sorted selectivity points kept separate.

Graph choices:

- Numeric selectivity x-axes use line charts.
- Categorical x-axes use grouped bar charts.
- Latency is plotted as milliseconds (`avg_total_time_ms`) after converting from `avg_total_time_s`.

## 12. Final DuckDB Experiments and Findings

### Layout Sensitivity

#### Purpose

Test how physical layout affects pruning.

#### Setup

- Same logical table contents.
- Layouts: random, sorted, block-sorted.
- Range predicates over `a`.
- Selectivities: `0.1%`, `1%`, `5%`, `10%`, `20%`, `50%`, `90%`.
- Graph averages the selectivity queries into one value per layout.

#### Modes Compared

- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`

#### Observed Result

Average vectors:

- random: segment zonemap `4883.0`, sketch `4185.6`
- sorted: segment zonemap `1268.6`, sketch `601.3`
- block-sorted: segment zonemap `1268.6`, sketch `601.3`

Average latency:

- random: segment zonemap `0.0514s`, sketch `0.0595s`
- sorted: segment zonemap `0.0081s`, sketch `0.0043s`
- block-sorted: segment zonemap `0.0081s`, sketch `0.0045s`

#### Interpretation

Sketch reduces vectors in all layouts, but random layout shows overhead dominance: fewer vectors do not guarantee lower latency. Sorted and block-sorted layouts create more useful pruning opportunities, and sketch wins on latency there.

### NDV / Cardinality

#### Purpose

Test whether sketches become more useful as `a` has more distinct values.

#### Setup

- Tables: `t_ndv_low`, `t_ndv_medium`, `t_ndv_high`.
- Row count: 10M each.
- NDV(a): 100, 10,000, 1,000,000.
- Queries: `a < threshold` at 1%, 5%, 10%, 20%, 50%, 90%.
- Graph averages selectivity queries into one value per NDV level.

#### Observed Result

Average vectors:

- low NDV: segment zonemap `4883.0`, sketch `4883.0`
- medium NDV: segment zonemap `4883.0`, sketch `2344.3`
- high NDV: segment zonemap `1980.0`, sketch `1441.8`

Average latency:

- low NDV: segment zonemap `0.0276s`, sketch `0.0344s`
- medium NDV: segment zonemap `0.0199s`, sketch `0.0145s`
- high NDV: segment zonemap `0.0076s`, sketch `0.0059s`

#### Interpretation

Low NDV gives sketch no vector reduction and worse latency. Medium/high NDV make value absence more informative at segment granularity, so sketch reduces scan work and improves latency.

### Selectivity / Crossover Analysis

#### Purpose

Find where sketch changes from win to tie to loss as selectivity broadens.

#### Setup

- Table: `t_ndv_medium`.
- Rows: 10M.
- Schema: `id BIGINT`, `a INTEGER`, `b DOUBLE`.
- NDV(a): 10,000.
- Data: `a = i % 10000`.
- Predicate family: `a < threshold`.
- Selectivity levels: 1%, 5%, 10%, 20%, 50%, 90%.

#### Observed Result

Medium-NDV focused results:

| Selectivity | Segment Zonemap vectors | Sketch vectors | Segment Zonemap latency | Sketch latency |
| --- | ---: | ---: | ---: | ---: |
| 1% | 4883 | 1048 | 0.01930s | 0.00763s |
| 5% | 4883 | 1243 | 0.01933s | 0.00899s |
| 10% | 4883 | 1485 | 0.01941s | 0.01092s |
| 20% | 4883 | 1969 | 0.01974s | 0.01416s |
| 50% | 4883 | 3438 | 0.02042s | 0.02028s |
| 90% | 4883 | 4883 | 0.02115s | 0.02503s |

#### Interpretation

Sketch clearly wins from 1% through 20%, ties around 50%, and loses at 90%. This is the cleanest evidence for the access-path tradeoff: sketches help when they prune many vectors, but hurt when they add overhead without pruning.

### Predicate Type

#### Purpose

Test which predicate forms activate useful sketch pruning.

#### Setup

- Tables: low/medium/high NDV.
- Predicate types: equality, less-than, between, conjunctive.
- Graph averages across NDV levels for each predicate type.

#### Observed Result

Average vectors:

- equality: segment zonemap `3635.3`, sketch `3635.3`
- less-than: segment zonemap `3755.3`, sketch `2612.7`
- between: segment zonemap `3715.3`, sketch `2460.3`
- conjunctive: segment zonemap `3715.3`, sketch `2460.3`

Average latency:

- equality: segment zonemap `0.0169s`, sketch `0.0099s`
- less-than: segment zonemap `0.0176s`, sketch `0.0250s`
- between: segment zonemap `0.0234s`, sketch `0.0359s`
- conjunctive: segment zonemap `0.0450s`, sketch `0.0740s`

#### Interpretation

Equality does not reduce vectors under sketch. This matches `NumericStats::CheckSketchTemplated`, which returns `NO_PRUNING_POSSIBLE` for `COMPARE_EQUAL`. Range-style predicates reduce vectors, but sketch latency can still be worse due to overhead. The conjunctive results should be qualified because some sketch/full conjunctive chunks had failures/incomplete repetitions.

### Distribution / Skew

#### Purpose

Test uniform versus hotspot distribution.

#### Setup

- `t_dist_uniform`: uniform-like.
- `t_dist_hotspot`: 80% of rows in `a` range `[0,9999]`.
- Equality and range probes inside and outside hotspot region.

#### Observed Result

Average vectors:

- uniform: segment zonemap `900.0`, sketch `467.0`
- hotspot: segment zonemap `3941.0`, sketch `2598.5`

Average latency:

- uniform: segment zonemap `0.0040s`, sketch `0.0017s`
- hotspot: segment zonemap `0.0204s`, sketch `0.0135s`

#### Interpretation

Sketch helps in the aggregate. However, the current plot averages hotspot-region and non-hotspot-region probes together, so it should not be used to claim behavior specifically inside the hot region. For final presentation, layout, NDV, predicate type, and crossover are cleaner.

### Overall Finding

The central access-path lesson is:

> Column sketch can reduce `vectors_processed` more than segment zonemap, but it only improves latency when the scan work saved exceeds sketch evaluation overhead.

## 13. RABIT / Bitmap Python Prototype

Ignored per current instruction. No DuckDB-integrated RABIT implementation was found during repository inspection. Any RABIT/bitmap results should be described separately as algorithmic prototype results, not as direct DuckDB engine-level comparisons.

## 14. Final Project Narrative for Report

Recommended final LaTeX structure:

1. **Introduction**
   - Update midway framing to focus on access-path selection and controlled segment-level comparison.
   - State that RABIT, if discussed, is separate from DuckDB-integrated experiments.

2. **Background**
   - Explain zonemaps, sketches, row groups, column segments, vectors.
   - Emphasize that vectors are runtime execution batches, not storage units.

3. **DuckDB Storage and Scan Architecture**
   - Include the hierarchy: table -> row group -> column data -> column segments -> runtime vectors.
   - Include constants: 122,880 rows per row group, 2,048 rows per vector, about 60 vector-sized chunks per full row group.

4. **System Modifications**
   - Runtime flags.
   - Segment-level sketch generalization.
   - Scan metrics and profiler display.
   - Query profiler refresh fix.

5. **Experimental Methodology**
   - Synthetic workload generation.
   - 10M-row schema.
   - Controlled variables: layout, selectivity, NDV, distribution, predicate type.
   - Main modes: row-group + segment zonemap vs row-group + sketch.

6. **DuckDB Experiments**
   - Include figures for layout, NDV, predicate type, and crossover.
   - Use `vectors_processed` and latency together.
   - Qualify averaged graphs.

7. **RABIT Prototype Evaluation**
   - Omit if not part of final scope, or explicitly separate from DuckDB engine results.

8. **Discussion**
   - Sketch reduces scan work but has overhead.
   - Segment zonemap counters are often near zero in focused modes.
   - Equality sketch pruning is currently limited.
   - Synthetic workloads reveal causal behavior better than TPC-H-only testing.

9. **Conclusion**
   - Controlled access-path selection is necessary.
   - Sketch helps in medium/high NDV and selective regimes.
   - Access-path selection should consider both pruning power and overhead.

10. **Future Work**
    - Persist sketches robustly.
    - Improve equality sketch pruning.
    - Split distribution results by hot vs cold target.
    - Add planner cost model for choosing segment zonemap vs sketch.

## 15. Claims That Are Supported vs Not Supported

### Supported Claims

- Row-group pruning is zonemap-based in this project.
- Column sketches are used at the column-segment level, not row-group level.
- Runtime flags can force controlled access-path modes.
- `vectors_processed` measures scan work that survived pruning.
- Sketch can reduce `vectors_processed` more than segment zonemap.
- Sketch can reduce vectors but still lose on latency due to overhead.
- Medium-NDV selective predicates are a strong sketch case.
- Low NDV is a weak sketch case.
- Equality predicates do not currently show sketch vector reduction in the final results.
- The Python runners export both latency and internal scan metrics.

### Claims to Avoid or Qualify

- Avoid: "Column sketch is always faster."
- Avoid: "Sketch is better whenever it prunes more vectors."
- Avoid: "Row-group pruning uses sketches."
- Avoid: "Vectors are storage units."
- Avoid: "The distribution graph proves behavior inside the hotspot region." It averages hot and non-hot probes.
- Qualify: "Segment zonemap does not work." Better: in these focused synthetic results, segment-zonemap counters are often zero or near zero.
- Qualify: "Sketches are persistent." The inspected code clearly builds sketches during append; persistence across reopened databases is not fully established here.
- Qualify: "segment_zonemap_only was fully evaluated." The runner supports it, but the main cumulative CSV does not include it.

## 16. Open Questions / Missing Evidence

- Sketch persistence across checkpoint/reopen is unclear from inspected code.
- The main cumulative CSV lacks the `segment_zonemap_only` mode despite the runner supporting it.
- Some conjunctive chunks failed or had fewer repetitions; see `experiments/results/explain_metrics_failures.csv`.
- The distribution plot averages different probe targets and should be split before making hot-region-specific claims.
- `NumericStats::CheckSketchTemplated` returns `NO_PRUNING_POSSIBLE` for equality; equality sketch behavior is therefore limited.
- The current repository has uncommitted/generated plot changes and this report file.
- No RABIT integration was found in this DuckDB source tree.

## Final Report Update Checklist

- Replace midway TPC-H-centered discussion with synthetic workload methodology.
- Add a DuckDB storage/scan architecture figure:
  - table -> row groups -> column data -> column segments -> runtime vectors.
- Add a table of runtime flags:
  - `disable_zonemap`
  - `disable_segment_zonemap`
  - `disable_sketch`
- Add implementation section with file/function references:
  - `RowGroup::CheckZonemap`
  - `RowGroup::CheckZonemapSegments`
  - `RowGroup::CheckSketchSegments`
  - `RowGroup::TemplatedScan`
  - `TableScanToString`
- Explain the sketch availability fix:
  - numeric sketch construction during append,
  - filtered-column eligibility,
  - DOUBLE encoding.
- Add metrics section:
  - row groups pruned,
  - segments pruned by zonemap,
  - segments pruned by sketch,
  - vectors processed,
  - latency.
- Include final plots:
  - layout vectors/latency,
  - NDV vectors/latency,
  - predicate type vectors/latency,
  - focused crossover vectors/latency.
- State the main conclusion:
  - sketch can reduce scan work, but latency wins only when pruning benefit exceeds overhead.
- Qualify unsupported claims:
  - no row-group sketch pruning,
  - no direct RABIT/DuckDB comparison,
  - no claim that sketch is always faster.
