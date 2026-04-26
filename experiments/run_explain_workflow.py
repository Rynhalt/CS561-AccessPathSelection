#!/usr/bin/env python3

import argparse
import csv
import os
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "experiments" / "sql"
WORKER = ROOT / "experiments" / "run_explain_suite.py"
DEFAULT_DUCKDB = ROOT / "build" / "release" / "duckdb"
THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


SUITES = {
    "layout_selectivity": ("create_base_uniform.sql", "create_layout_random.sql", "create_layout_sorted.sql", "create_layout_block_sorted.sql", "queries_layout_selectivity_explain.sql"),
    "ndv_selectivity": ("create_ndv_low.sql", "create_ndv_medium.sql", "create_ndv_high.sql", "queries_ndv_selectivity_explain.sql"),
    "ndv_predicates": ("create_ndv_low.sql", "create_ndv_medium.sql", "create_ndv_high.sql", "queries_ndv_predicates_explain.sql"),
    "distribution_predicates": ("create_distribution_uniform.sql", "create_distribution_hotspot.sql", "queries_distribution_predicates_explain.sql"),
}


PER_RUN_FIELDNAMES = [
    "suite",
    "query_name",
    "disable_zonemap",
    "disable_segment_zonemap",
    "disable_sketch",
    "mode",
    "run",
    "total_time_s",
    "row_groups_pruned_by_zonemap",
    "segments_pruned_by_zonemap",
    "segments_pruned_by_sketch",
    "vectors_processed",
]


SUMMARY_FIELDNAMES = [
    "suite",
    "query_name",
    "mode",
    "disable_zonemap",
    "disable_segment_zonemap",
    "disable_sketch",
    "runs",
    "avg_total_time_s",
    "avg_row_groups_pruned_by_zonemap",
    "avg_segments_pruned_by_zonemap",
    "avg_segments_pruned_by_sketch",
    "avg_vectors_processed",
]


FAILURE_FIELDNAMES = [
    "suite",
    "query_name",
    "mode",
    "run",
    "exit_code",
    "stdout",
    "stderr",
]


def read_sql_file(path):
    return path.read_text(encoding="utf-8")


def split_explain_queries(sql_text):
    statements = []
    current = []
    for line in sql_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("--"):
            continue
        current.append(line)
        if stripped.endswith(";"):
            statement = "\n".join(current).strip()
            current.clear()
            if statement.upper().startswith("EXPLAIN ANALYZE"):
                statements.append(statement)
    if current:
        raise ValueError("Found unterminated SQL statement while parsing query file")
    return statements


def extract_query_name(query_sql, fallback_index):
    import re

    match = re.search(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s+FROM\b", query_sql, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return f"query_{fallback_index:02d}"


def query_names_for_suite(suite_name):
    query_file = SUITES[suite_name][-1]
    query_text = read_sql_file(SQL_DIR / query_file)
    statements = split_explain_queries(query_text)
    return [extract_query_name(statement, idx + 1) for idx, statement in enumerate(statements)]


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def read_csv(path):
    with path.open("r", encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def chunk_is_complete(path, repetitions):
    if not path.exists():
        return False
    return len(read_csv(path)) == repetitions


def suite_output_path(path, suite_name):
    suffix = path.suffix or ".csv"
    return path.with_name(f"{path.stem}_{suite_name}{suffix}")


def thread_limited_env(threads):
    env = os.environ.copy()
    for name in THREAD_ENV_VARS:
        env[name] = str(threads)
    return env


def compute_averages(rows):
    grouped = defaultdict(list)
    for row in rows:
        key = (
            row["suite"],
            row["query_name"],
            row["mode"],
            row["disable_zonemap"],
            row["disable_segment_zonemap"],
            row["disable_sketch"],
        )
        grouped[key].append(row)

    average_rows = []
    numeric_fields = [
        "total_time_s",
        "row_groups_pruned_by_zonemap",
        "segments_pruned_by_zonemap",
        "segments_pruned_by_sketch",
        "vectors_processed",
    ]
    for key, group_rows in sorted(grouped.items()):
        suite, query_name, mode, disable_zonemap, disable_segment_zonemap, disable_sketch = key
        average_row = {
            "suite": suite,
            "query_name": query_name,
            "mode": mode,
            "disable_zonemap": disable_zonemap,
            "disable_segment_zonemap": disable_segment_zonemap,
            "disable_sketch": disable_sketch,
            "runs": str(len(group_rows)),
        }
        for field in numeric_fields:
            values = [float(row[field]) for row in group_rows if row[field] != ""]
            average_row[f"avg_{field}"] = f"{sum(values) / len(values):.6f}" if values else ""
        average_rows.append(average_row)
    return average_rows


def parse_args():
    parser = argparse.ArgumentParser(
        description="Chunked experiment driver that runs one suite/query/mode at a time and merges the CSV outputs."
    )
    parser.add_argument(
        "--duckdb",
        type=Path,
        default=DEFAULT_DUCKDB,
        help=f"Path to DuckDB binary (default: {DEFAULT_DUCKDB})",
    )
    parser.add_argument(
        "--suite",
        action="append",
        choices=sorted(SUITES.keys()),
        help="Suite to run. Repeat to run multiple suites. Defaults to all suites.",
    )
    parser.add_argument(
        "--start-suite",
        choices=list(SUITES.keys()),
        help="Run suites starting from this suite in the default order.",
    )
    parser.add_argument(
        "--skip-completed-suites",
        action="store_true",
        help="Skip suites whose per-suite runs CSV already exists and include those rows in the cumulative CSV.",
    )
    parser.add_argument(
        "--mode",
        action="append",
        choices=[
            "full",
            "zonemap_only",
            "sketch_only",
            "none",
            "rowgroup_only",
            "rowgroup_plus_segment_zonemap",
            "rowgroup_plus_sketch",
        ],
        help="Flag mode to run. Repeat to run multiple modes. Defaults to all modes.",
    )
    parser.add_argument(
        "--query",
        action="append",
        help="Query name to run. Repeat to run multiple queries. Defaults to all queries in the suite.",
    )
    parser.add_argument(
        "--repetitions",
        type=int,
        default=10,
        help="Number of repetitions per query/mode combination (default: 10)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "experiments" / "results" / "explain_metrics_runs.csv",
        help="Per-run CSV output path",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=ROOT / "experiments" / "results" / "explain_metrics_summary.csv",
        help="Per-query/per-mode average CSV output path",
    )
    parser.add_argument(
        "--chunk-dir",
        type=Path,
        default=ROOT / "experiments" / "results" / "chunks",
        help="Directory for durable per-suite/per-query/per-mode chunk CSVs",
    )
    parser.add_argument(
        "--failure-output",
        type=Path,
        default=ROOT / "experiments" / "results" / "explain_metrics_failures.csv",
        help="CSV path for failed chunks when --skip-failed-chunks is set",
    )
    parser.add_argument(
        "--skip-failed-chunks",
        action="store_true",
        help="Continue running after a chunk fails and write failure details to --failure-output.",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="DuckDB execution threads to use for each chunk (default: 1)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    duckdb_bin = args.duckdb.resolve()
    if not duckdb_bin.exists():
        print(f"DuckDB binary not found: {duckdb_bin}", file=sys.stderr)
        return 1
    if not WORKER.exists():
        print(f"Worker script not found: {WORKER}", file=sys.stderr)
        return 1

    selected_suites = list(args.suite or SUITES.keys())
    if args.start_suite:
        if args.suite:
            raise RuntimeError("--start-suite cannot be combined with explicit --suite filters")
        suite_names = list(SUITES.keys())
        selected_suites = suite_names[suite_names.index(args.start_suite) :]
    selected_modes = list(
        args.mode
        or [
            "full",
            "zonemap_only",
            "sketch_only",
            "none",
            "rowgroup_only",
            "rowgroup_plus_segment_zonemap",
            "rowgroup_plus_sketch",
        ]
    )
    all_rows = []
    failure_rows = []

    args.chunk_dir.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="duckdb_experiment_chunks_"):
        requested_queries = set(args.query) if args.query else None
        for suite_name in selected_suites:
            suite_rows = []
            suite_run_output = suite_output_path(args.output, suite_name)
            suite_summary_output = suite_output_path(args.summary_output, suite_name)
            if args.skip_completed_suites and suite_run_output.exists():
                suite_rows = read_csv(suite_run_output)
                all_rows.extend(suite_rows)
                summary_rows = compute_averages(all_rows)
                write_csv(args.output, PER_RUN_FIELDNAMES, all_rows)
                write_csv(args.summary_output, SUMMARY_FIELDNAMES, summary_rows)
                print(f"Skipped completed suite using {suite_run_output}")
                print(f"Updated cumulative rows at {args.output}")
                print(f"Updated cumulative summary at {args.summary_output}")
                continue

            query_names = query_names_for_suite(suite_name)
            if requested_queries is not None:
                query_names = [name for name in query_names if name in requested_queries]
                if not query_names:
                    raise RuntimeError(
                        f"No queries matched the requested filter for suite {suite_name}: {sorted(requested_queries)}"
                    )
            for mode_name in selected_modes:
                for query_name in query_names:
                    chunk_output = args.chunk_dir / f"{suite_name}_{mode_name}_{query_name}_runs.csv"
                    chunk_summary = args.chunk_dir / f"{suite_name}_{mode_name}_{query_name}_summary.csv"
                    if args.skip_completed_suites and chunk_is_complete(chunk_output, args.repetitions):
                        chunk_rows = read_csv(chunk_output)
                        suite_rows.extend(chunk_rows)
                        all_rows.extend(chunk_rows)
                        print(f"Skipped completed chunk using {chunk_output}", file=sys.stderr)
                        continue

                    chunk_rows = []
                    for run_index in range(1, args.repetitions + 1):
                        rep_output = args.chunk_dir / f"{suite_name}_{mode_name}_{query_name}_run_{run_index}_runs.csv"
                        rep_summary = args.chunk_dir / f"{suite_name}_{mode_name}_{query_name}_run_{run_index}_summary.csv"
                        print(
                            f"Running {suite_name} / {query_name} / {mode_name} / run {run_index}",
                            file=sys.stderr,
                        )
                        proc = subprocess.run(
                            [
                                sys.executable,
                                str(WORKER),
                                "--duckdb",
                                str(duckdb_bin),
                                "--suite",
                                suite_name,
                                "--mode",
                                mode_name,
                                "--query",
                                query_name,
                                "--repetitions",
                                "1",
                                "--output",
                                str(rep_output),
                                "--summary-output",
                                str(rep_summary),
                                "--threads",
                                str(args.threads),
                            ],
                            stdout=subprocess.PIPE,
                            stderr=subprocess.PIPE,
                            universal_newlines=True,
                            env=thread_limited_env(args.threads),
                            check=False,
                        )
                        if proc.returncode != 0:
                            if args.skip_failed_chunks:
                                failure_rows.append(
                                    {
                                        "suite": suite_name,
                                        "query_name": query_name,
                                        "mode": mode_name,
                                        "run": str(run_index),
                                        "exit_code": str(proc.returncode),
                                        "stdout": proc.stdout[-2000:],
                                        "stderr": proc.stderr[-2000:],
                                    }
                                )
                                write_csv(args.failure_output, FAILURE_FIELDNAMES, failure_rows)
                                print(
                                    f"Skipped failed chunk {suite_name} / {query_name} / {mode_name} / run {run_index}",
                                    file=sys.stderr,
                                )
                                continue
                            raise RuntimeError(
                                f"Chunk failed for {suite_name} / {query_name} / {mode_name} / run {run_index} "
                                f"with exit code {proc.returncode}\n"
                                f"--- STDOUT ---\n{proc.stdout}\n"
                                f"--- STDERR ---\n{proc.stderr}"
                            )
                        rep_rows = read_csv(rep_output)
                        for row in rep_rows:
                            row["run"] = str(run_index)
                        chunk_rows.extend(rep_rows)

                    if chunk_rows:
                        write_csv(chunk_output, PER_RUN_FIELDNAMES, chunk_rows)
                        write_csv(chunk_summary, SUMMARY_FIELDNAMES, compute_averages(chunk_rows))
                    suite_rows.extend(chunk_rows)
                    all_rows.extend(chunk_rows)

                    suite_summary_rows = compute_averages(suite_rows)
                    write_csv(suite_run_output, PER_RUN_FIELDNAMES, suite_rows)
                    write_csv(suite_summary_output, SUMMARY_FIELDNAMES, suite_summary_rows)

                    summary_rows = compute_averages(all_rows)
                    write_csv(args.output, PER_RUN_FIELDNAMES, all_rows)
                    write_csv(args.summary_output, SUMMARY_FIELDNAMES, summary_rows)

            suite_summary_rows = compute_averages(suite_rows)
            write_csv(suite_run_output, PER_RUN_FIELDNAMES, suite_rows)
            write_csv(suite_summary_output, SUMMARY_FIELDNAMES, suite_summary_rows)

            summary_rows = compute_averages(all_rows)
            write_csv(args.output, PER_RUN_FIELDNAMES, all_rows)
            write_csv(args.summary_output, SUMMARY_FIELDNAMES, summary_rows)
            print(f"Wrote completed suite rows to {suite_run_output}")
            print(f"Wrote completed suite summary to {suite_summary_output}")
            print(f"Updated cumulative rows at {args.output}")
            print(f"Updated cumulative summary at {args.summary_output}")

    summary_rows = compute_averages(all_rows)
    write_csv(args.output, PER_RUN_FIELDNAMES, all_rows)
    write_csv(args.summary_output, SUMMARY_FIELDNAMES, summary_rows)

    print(f"Wrote {len(all_rows)} per-run rows to {args.output}")
    print(f"Wrote {len(summary_rows)} summary rows to {args.summary_output}")
    if failure_rows:
        print(f"Wrote {len(failure_rows)} failed chunks to {args.failure_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
