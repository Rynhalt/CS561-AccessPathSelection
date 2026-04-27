#!/usr/bin/env python3

import argparse
import csv
import os
import re
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Dict, List, Optional, Tuple


ROOT = Path(__file__).resolve().parents[1]
SQL_DIR = ROOT / "experiments" / "sql"
DEFAULT_DUCKDB = ROOT / "build" / "release" / "duckdb"
THREAD_ENV_VARS = (
    "OMP_NUM_THREADS",
    "OPENBLAS_NUM_THREADS",
    "MKL_NUM_THREADS",
    "VECLIB_MAXIMUM_THREADS",
    "NUMEXPR_NUM_THREADS",
)


class Suite(object):
    def __init__(self, name, setup_files, query_file):
        self.name = name
        self.setup_files = setup_files
        self.query_file = query_file


SUITES = {
    "layout_selectivity": Suite(
        name="layout_selectivity",
        setup_files=(
            "create_base_uniform.sql",
            "create_layout_random.sql",
            "create_layout_sorted.sql",
            "create_layout_block_sorted.sql",
        ),
        query_file="queries_layout_selectivity_explain.sql",
    ),
    "ndv_selectivity": Suite(
        name="ndv_selectivity",
        setup_files=("create_ndv_low.sql", "create_ndv_medium.sql", "create_ndv_high.sql"),
        query_file="queries_ndv_selectivity_explain.sql",
    ),
    "ndv_predicates": Suite(
        name="ndv_predicates",
        setup_files=("create_ndv_low.sql", "create_ndv_medium.sql", "create_ndv_high.sql"),
        query_file="queries_ndv_predicates_explain.sql",
    ),
    "distribution_predicates": Suite(
        name="distribution_predicates",
        setup_files=("create_distribution_uniform.sql", "create_distribution_hotspot.sql"),
        query_file="queries_distribution_predicates_explain.sql",
    ),
}


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
    match = re.search(r"\bAS\s+([A-Za-z_][A-Za-z0-9_]*)\s+FROM\b", query_sql, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return f"query_{fallback_index:02d}"


def thread_limited_env(threads):
    env = os.environ.copy()
    for name in THREAD_ENV_VARS:
        env[name] = str(threads)
    return env


def run_duckdb(duckdb_bin, db_path, sql_text, threads):
    sql_text = f"SET threads={threads};\n{sql_text}"
    proc = subprocess.run(
        [str(duckdb_bin), str(db_path)],
        input=sql_text,
        universal_newlines=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=thread_limited_env(threads),
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"DuckDB command failed with exit code {proc.returncode}\n"
            f"--- STDOUT ---\n{proc.stdout}\n"
            f"--- STDERR ---\n{proc.stderr}"
        )
    return proc.stdout


def normalize_output(output):
    return re.sub(r"[^A-Za-z0-9_:.]+", "", output)


def parse_metric(output, label):
    normalized = normalize_output(output)
    match = re.search(re.escape(label) + r":([0-9.]+)", normalized)
    return match.group(1) if match else None


def parse_total_time(output):
    normalized = normalize_output(output)
    match = re.search(r"TotalTime:([0-9.]+)s", normalized)
    return match.group(1) if match else None


def split_explain_outputs(output, expected_count):
    starts = [match.start() for match in re.finditer(r"EXPLAIN ANALYZE", output)]
    if len(starts) != expected_count:
        raise RuntimeError(
            f"Expected {expected_count} EXPLAIN ANALYZE outputs, found {len(starts)}.\n"
            f"First 2000 output characters:\n{output[:2000]}"
        )
    starts.append(len(output))
    return [output[starts[i] : starts[i + 1]] for i in range(expected_count)]


def build_setup_sql(suite):
    return "\n\n".join(read_sql_file(SQL_DIR / filename) for filename in suite.setup_files)


def query_sqls_for_suite(suite, selected_queries=None):
    query_text = read_sql_file(SQL_DIR / suite.query_file)
    statements = split_explain_queries(query_text)
    queries = [(extract_query_name(statement, idx + 1), statement) for idx, statement in enumerate(statements)]
    if selected_queries:
        selected = set(selected_queries)
        queries = [item for item in queries if item[0] in selected]
    return queries


def set_flags_sql(disable_zonemap, disable_segment_zonemap, disable_sketch):
    zonemap = "true" if disable_zonemap else "false"
    segment_zonemap = "true" if disable_segment_zonemap else "false"
    sketch = "true" if disable_sketch else "false"
    return (
        f"SET disable_zonemap={zonemap};\n"
        f"SET disable_segment_zonemap={segment_zonemap};\n"
        f"SET disable_sketch={sketch};"
    )


def run_suite(
    duckdb_bin,
    suite,
    db_path,
    mode_names,
    repetitions,
    selected_queries=None,
    threads=1,
):
    results = []
    queries = query_sqls_for_suite(suite, selected_queries=selected_queries)
    setup_sql = build_setup_sql(suite)
    for mode_name in mode_names:
        disable_zonemap, disable_segment_zonemap, disable_sketch = FLAG_MODES[mode_name]
        flags_sql = set_flags_sql(disable_zonemap, disable_segment_zonemap, disable_sketch)
        sql_parts = [setup_sql]
        query_contexts = []
        for run_index in range(1, repetitions + 1):
            for query_name, query_sql in queries:
                sql_parts.append(flags_sql)
                sql_parts.append(query_sql)
                query_contexts.append(
                    (query_name, disable_zonemap, disable_segment_zonemap, disable_sketch, mode_name, run_index)
                )

        output = run_duckdb(duckdb_bin, db_path, "\n\n".join(sql_parts) + "\n", threads)
        explain_outputs = split_explain_outputs(output, len(query_contexts))

        for output, context in zip(explain_outputs, query_contexts):
            query_name, disable_zonemap, disable_segment_zonemap, disable_sketch, mode_name, run_index = context
            results.append(
                {
                    "suite": suite.name,
                    "query_name": query_name,
                    "disable_zonemap": str(disable_zonemap).lower(),
                    "disable_segment_zonemap": str(disable_segment_zonemap).lower(),
                    "disable_sketch": str(disable_sketch).lower(),
                    "mode": mode_name,
                    "run": str(run_index),
                    "total_time_s": parse_total_time(output) or "",
                    "row_groups_pruned_by_zonemap": parse_metric(output, "row_groups_pruned_by_zonemap") or "",
                    "segments_pruned_by_zonemap": parse_metric(output, "segments_pruned_by_zonemap") or "",
                    "segments_pruned_by_sketch": parse_metric(output, "segments_pruned_by_sketch") or "",
                    "vectors_processed": parse_metric(output, "vectors_processed") or "",
                }
            )
    return results


def write_csv(path, fieldnames, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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
        description="Run EXPLAIN ANALYZE suites through the DuckDB binary and export profiler metrics to CSV."
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
        "--mode",
        action="append",
        choices=sorted(FLAG_MODES.keys()),
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
        default=1,
        help="Number of repetitions per query/mode combination (default: 1)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=ROOT / "experiments" / "results" / "explain_metrics.csv",
        help="Per-run CSV output path",
    )
    parser.add_argument(
        "--summary-output",
        type=Path,
        default=ROOT / "experiments" / "results" / "explain_metrics_summary.csv",
        help="Per-query/per-mode average CSV output path",
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="DuckDB execution threads to use (default: 1)",
    )
    return parser.parse_args()


def main():
    args = parse_args()
    duckdb_bin = args.duckdb.resolve()
    if not duckdb_bin.exists():
        print(f"DuckDB binary not found: {duckdb_bin}", file=sys.stderr)
        return 1

    selected_suites = [SUITES[name] for name in (args.suite or SUITES.keys())]
    mode_names = list(args.mode or FLAG_MODES.keys())
    rows = []

    with TemporaryDirectory(prefix="duckdb_experiments_") as tmpdir:
        tmpdir_path = Path(tmpdir)
        for suite in selected_suites:
            db_path = tmpdir_path / f"{suite.name}.duckdb"
            rows.extend(
                run_suite(
                    duckdb_bin,
                    suite,
                    db_path,
                    mode_names,
                    args.repetitions,
                    selected_queries=args.query,
                    threads=args.threads,
                )
            )

    per_run_fieldnames = [
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
    summary_rows = compute_averages(rows)
    summary_fieldnames = [
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
    write_csv(args.output, per_run_fieldnames, rows)
    write_csv(args.summary_output, summary_fieldnames, summary_rows)

    print(f"Wrote {len(rows)} per-run rows to {args.output}")
    print(f"Wrote {len(summary_rows)} summary rows to {args.summary_output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
