# Access Path Selection in Modern Columnar DBMSs

This repository contains a modified DuckDB engine for a CS561 final project on
access path selection in a vectorized columnar DBMS.

The final experiments compare three scan modes:

- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`
- `rowgroup_plus_rabit`

In all three modes, row-group zonemap pruning remains enabled. The mode changes
only the segment-level pruning method used after a row group survives.

## Running Experiments

### 1. Request an AVX-512 SCC node

Column sketches use AVX-512 code paths. On BU SCC, request an AVX-512-capable
node before compiling/running experiment by adding flag, "-l avx512" in the fiel "Extra qsub options:"

### 2. Compile DuckDB

From the repository root:

```bash
make release
```
This can take anywhere from 15-30 minutes.
This should produce:

```text
build/release/duckdb
```

### 3. Run the full workflow

After the binary exists, run:

```bash
python3 experiments/run_explain_workflow.py
```

By default this runs:

- all SQL workload suites in `experiments/sql/`
- all three final modes
- 10 repetitions per query/mode
- one DuckDB thread

The workflow writes final CSVs to:

```text
experiments/results/explain_metrics_runs.csv
experiments/results/explain_metrics_summary.csv
```

It also writes per-suite CSVs such as:

```text
experiments/results/explain_metrics_runs_layout_selectivity.csv
experiments/results/explain_metrics_summary_layout_selectivity.csv
```

Generated per-query chunk files are scratch outputs and are ignored by Git.

### 4. Generate plots

The workflow generates plots automatically after a successful run:

```text
plots_with_rabit/
```

To skip plot generation:

```bash
python3 experiments/run_explain_workflow.py --skip-plots
```

To regenerate plots from an existing summary CSV:

```bash
python3 experiments/plot_access_path_analysis.py \
  --summary-csv experiments/results/explain_metrics_summary.csv \
  --output-dir plots_with_rabit
```

## Useful Workflow Options

The experiment can take quite a while, to complete, and in the event it crashes in the middle, you can restart the experiment and resume from already completed suites, using:

```bash
python3 experiments/run_explain_workflow.py --skip-completed-suites
```

Run only one suite:

```bash
python3 experiments/run_explain_workflow.py --suite layout_selectivity
```

Run only one mode:

```bash
python3 experiments/run_explain_workflow.py --mode rowgroup_plus_rabit
```

Use a non-default DuckDB binary:

```bash
python3 experiments/run_explain_workflow.py --duckdb /path/to/duckdb
```


## Important Code Paths

- `src/storage/table/row_group.cpp`
  - scan-time access-path selection
  - row-group zonemap, segment zonemap, sketch, and RABIT pruning hooks
- `src/include/duckdb/storage/statistics/column_sketch.hpp`
  - column sketch implementation
- `src/include/duckdb/storage/statistics/rabit_index.hpp`
  - RABIT-inspired Group Encoding metadata
- `src/storage/statistics/rabit_index.cpp`
  - RABIT GE range checks over sparse point vectors and dense cumulative groups
- `experiments/run_explain_workflow.py`
  - top-level experiment runner
- `experiments/plot_access_path_analysis.py`
  - plot generation from experiment summaries
