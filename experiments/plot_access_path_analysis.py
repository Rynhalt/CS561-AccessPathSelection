#!/usr/bin/env python3
"""Generate focused access-path comparison plots.

Primary path: pandas + matplotlib.
Fallback path: standard-library SVG output when plotting packages are unavailable.
"""

import argparse
import csv
import os
import re
from collections import defaultdict


ZONEMAP_MODE = "rowgroup_plus_segment_zonemap"
SKETCH_MODE = "rowgroup_plus_sketch"
MODES = (ZONEMAP_MODE, SKETCH_MODE)

LABELS = {
    ZONEMAP_MODE: "Segment Zonemap",
    SKETCH_MODE: "Column Sketch",
}

COLORS = {
    ZONEMAP_MODE: "#e67e22",  # orange
    SKETCH_MODE: "#2ca02c",   # green
}


def pct_from_token(token):
    return float(token.replace("_", "."))


def parse_layout_query(query_name):
    match = re.match(r"^(random|sorted|block)_(.+)_pct$", query_name)
    if not match:
        return None, None
    layout = match.group(1)
    if layout == "block":
        layout = "block_sorted"
    return layout, pct_from_token(match.group(2))


def parse_ndv_selectivity_query(query_name):
    match = re.match(r"^(low|medium|high)_(.+)_pct$", query_name)
    if not match:
        return None, None
    return match.group(1), pct_from_token(match.group(2))


def parse_ndv_predicate_query(query_name):
    match = re.match(r"^(low|medium|high)_(eq|lt|between|conjunct)$", query_name)
    if not match:
        return None, None
    return match.group(1), match.group(2)


def parse_distribution_query(query_name):
    match = re.match(r"^(uniform|hotspot)_(eq|between)_(hotspot|nonhotspot)_(value|band)$", query_name)
    if not match:
        return None, None, None
    return match.group(1), match.group(2), match.group(3)


def normalize_mode_label(mode):
    return LABELS.get(mode, mode)


def ensure_dirs(output_dir):
    for subdir in ("selectivity", "layout", "ndv", "distribution", "predicate", "focused"):
        os.makedirs(os.path.join(output_dir, subdir), exist_ok=True)


def try_pandas_matplotlib(summary_csv, output_dir):
    import pandas as pd
    import matplotlib.pyplot as plt

    ensure_dirs(output_dir)
    df = pd.read_csv(summary_csv)
    df = df[df["mode"].isin(MODES)].copy()

    def add_layout_fields(frame):
        parsed = frame["query_name"].apply(parse_layout_query)
        frame = frame.copy()
        frame["layout"] = parsed.apply(lambda x: x[0])
        frame["selectivity"] = parsed.apply(lambda x: x[1])
        return frame

    def add_ndv_sel_fields(frame):
        parsed = frame["query_name"].apply(parse_ndv_selectivity_query)
        frame = frame.copy()
        frame["ndv"] = parsed.apply(lambda x: x[0])
        frame["selectivity"] = parsed.apply(lambda x: x[1])
        return frame

    def add_ndv_pred_fields(frame):
        parsed = frame["query_name"].apply(parse_ndv_predicate_query)
        frame = frame.copy()
        frame["ndv"] = parsed.apply(lambda x: x[0])
        frame["predicate"] = parsed.apply(lambda x: x[1])
        return frame

    def add_dist_fields(frame):
        parsed = frame["query_name"].apply(parse_distribution_query)
        frame = frame.copy()
        frame["distribution"] = parsed.apply(lambda x: x[0])
        frame["predicate"] = parsed.apply(lambda x: x[1])
        frame["target"] = parsed.apply(lambda x: x[2])
        return frame

    def ordered_values(values, preferred=None):
        vals = list(dict.fromkeys(values))
        if preferred:
            return [v for v in preferred if v in vals]
        return sorted(vals)

    def plot_lines(data, x_col, y_col, title, xlabel, ylabel, path, preferred_x=None, latency=False):
        fig, ax = plt.subplots(figsize=(9.5, 5.6))
        x_values = ordered_values(data[x_col], preferred_x)
        x_lookup = {x: i for i, x in enumerate(x_values)}
        numeric_x = all(isinstance(x, (int, float)) for x in x_values)
        axis_x_values = ([0.0] + [x for x in x_values if x != 0.0]) if numeric_x else x_values
        plot_y_col = y_col
        if latency:
            data = data.copy()
            plot_y_col = "_latency_ms"
            data[plot_y_col] = data[y_col] * 1000.0
        for mode in MODES:
            sub = data[data["mode"] == mode].copy()
            if numeric_x:
                sub["_xpos"] = sub[x_col]
            else:
                sub["_xpos"] = sub[x_col].map(x_lookup)
            sub = sub.sort_values("_xpos")
            ax.plot(
                sub["_xpos"],
                sub[plot_y_col],
                marker="o",
                linewidth=2,
                label=normalize_mode_label(mode),
                color=COLORS[mode],
            )
        ax.set_title(title, fontsize=22)
        ax.set_xlabel(xlabel, fontsize=19, labelpad=14)
        ax.set_ylabel(ylabel, fontsize=19, labelpad=14)
        if numeric_x:
            ax.set_xlim(left=0)
            ax.set_xticks(axis_x_values)
            ax.set_xticklabels([str(x) for x in axis_x_values], fontsize=16)
        else:
            ax.set_xticks(range(len(x_values)))
            ax.set_xticklabels([str(x) for x in x_values], fontsize=16)
        ax.tick_params(axis="y", labelsize=16)
        ax.ticklabel_format(style="plain", axis="y")
        ax.grid(True, alpha=0.25)
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=16)
        fig.tight_layout()
        fig.savefig(path, dpi=170)
        plt.close(fig)

    def plot_grouped_bars(data, x_col, y_col, title, xlabel, ylabel, path, preferred_x=None, latency=False):
        fig, ax = plt.subplots(figsize=(9.5, 5.6))
        x_values = ordered_values(data[x_col], preferred_x)
        plot_y_col = y_col
        if latency:
            data = data.copy()
            plot_y_col = "_latency_ms"
            data[plot_y_col] = data[y_col] * 1000.0
        width = 0.36
        for mode_index, mode in enumerate(MODES):
            sub = data[data["mode"] == mode].set_index(x_col)
            ys = [sub.loc[x, plot_y_col] for x in x_values]
            xs = [i + (-width / 2 if mode_index == 0 else width / 2) for i in range(len(x_values))]
            ax.bar(xs, ys, width=width, label=normalize_mode_label(mode), color=COLORS[mode])
        ax.set_title(title, fontsize=22)
        ax.set_xlabel(xlabel, fontsize=19, labelpad=14)
        ax.set_ylabel(ylabel, fontsize=19, labelpad=14)
        ax.set_xticks(range(len(x_values)))
        ax.set_xticklabels([str(x) for x in x_values], fontsize=16, rotation=15, ha="right")
        ax.tick_params(axis="y", labelsize=16)
        ax.ticklabel_format(style="plain", axis="y")
        ax.grid(True, axis="y", alpha=0.25)
        ax.set_ylim(bottom=0)
        ax.legend(fontsize=16)
        fig.tight_layout()
        fig.savefig(path, dpi=170)
        plt.close(fig)

    layout = add_layout_fields(df[df["suite"] == "layout_selectivity"])
    block = layout[layout["layout"] == "block_sorted"]
    selectivity_order = [0.0, 0.1, 1.0, 5.0, 10.0, 20.0, 50.0, 90.0]
    plot_lines(block, "selectivity", "avg_vectors_processed", "Experiment 1: Selectivity vs Vectors Processed", "Selectivity (%)", "avg_vectors_processed", os.path.join(output_dir, "selectivity", "vectors_processed.png"), selectivity_order)
    plot_lines(block, "selectivity", "avg_total_time_s", "Experiment 1: Selectivity vs Latency", "Selectivity (%)", "avg_total_time_ms", os.path.join(output_dir, "selectivity", "latency.png"), selectivity_order, True)

    layout_avg = layout.groupby(["layout", "mode"], as_index=False)[["avg_vectors_processed", "avg_total_time_s"]].mean()
    layout_avg["layout"] = pd.Categorical(layout_avg["layout"], ["random", "sorted", "block_sorted"], ordered=True)
    layout_avg = layout_avg.sort_values("layout")
    layout_order = ["random", "sorted", "block_sorted"]
    plot_grouped_bars(layout_avg, "layout", "avg_vectors_processed", "Experiment 2: Layout vs Vectors Processed", "Physical Layout", "avg_vectors_processed", os.path.join(output_dir, "layout", "vectors_processed.png"), layout_order)
    plot_grouped_bars(layout_avg, "layout", "avg_total_time_s", "Experiment 2: Layout vs Latency", "Physical Layout", "avg_total_time_ms", os.path.join(output_dir, "layout", "latency.png"), layout_order, True)

    ndv = add_ndv_sel_fields(df[df["suite"] == "ndv_selectivity"])
    ndv_avg = ndv.groupby(["ndv", "mode"], as_index=False)[["avg_vectors_processed", "avg_total_time_s"]].mean()
    ndv_avg["ndv"] = pd.Categorical(ndv_avg["ndv"], ["low", "medium", "high"], ordered=True)
    ndv_avg = ndv_avg.sort_values("ndv")
    ndv_order = ["low", "medium", "high"]
    plot_grouped_bars(ndv_avg, "ndv", "avg_vectors_processed", "Experiment 3: NDV vs Vectors Processed", "NDV Level", "avg_vectors_processed", os.path.join(output_dir, "ndv", "vectors_processed.png"), ndv_order)
    plot_grouped_bars(ndv_avg, "ndv", "avg_total_time_s", "Experiment 3: NDV vs Latency", "NDV Level", "avg_total_time_ms", os.path.join(output_dir, "ndv", "latency.png"), ndv_order, True)

    dist = add_dist_fields(df[df["suite"] == "distribution_predicates"])
    dist_avg = dist.groupby(["distribution", "mode"], as_index=False)[["avg_vectors_processed", "avg_total_time_s"]].mean()
    dist_avg["distribution"] = pd.Categorical(dist_avg["distribution"], ["uniform", "hotspot"], ordered=True)
    dist_avg = dist_avg.sort_values("distribution")
    dist_order = ["uniform", "hotspot"]
    plot_grouped_bars(dist_avg, "distribution", "avg_vectors_processed", "Experiment 4: Distribution vs Vectors Processed", "Distribution", "avg_vectors_processed", os.path.join(output_dir, "distribution", "vectors_processed.png"), dist_order)
    plot_grouped_bars(dist_avg, "distribution", "avg_total_time_s", "Experiment 4: Distribution vs Latency", "Distribution", "avg_total_time_ms", os.path.join(output_dir, "distribution", "latency.png"), dist_order, True)

    pred = add_ndv_pred_fields(df[df["suite"] == "ndv_predicates"])
    pred_avg = pred.groupby(["predicate", "mode"], as_index=False)[["avg_vectors_processed", "avg_total_time_s"]].mean()
    pred_avg["predicate"] = pd.Categorical(pred_avg["predicate"], ["eq", "lt", "between", "conjunct"], ordered=True)
    pred_avg = pred_avg.sort_values("predicate")
    pred_order = ["eq", "lt", "between", "conjunct"]
    plot_grouped_bars(pred_avg, "predicate", "avg_vectors_processed", "Experiment 5: Predicate Type vs Vectors Processed", "Predicate Type", "avg_vectors_processed", os.path.join(output_dir, "predicate", "vectors_processed.png"), pred_order)
    plot_grouped_bars(pred_avg, "predicate", "avg_total_time_s", "Experiment 5: Predicate Type vs Latency", "Predicate Type", "avg_total_time_ms", os.path.join(output_dir, "predicate", "latency.png"), pred_order, True)

    focused = ndv[(ndv["ndv"] == "medium")].copy()
    plot_lines(focused, "selectivity", "avg_vectors_processed", "Experiment 6: Medium-NDV Focused Segment Comparison", "Selectivity (%)", "avg_vectors_processed", os.path.join(output_dir, "focused", "vectors_processed.png"), [0.0, 1.0, 5.0, 10.0, 20.0, 50.0, 90.0])
    plot_lines(focused, "selectivity", "avg_total_time_s", "Experiment 6: Medium-NDV Focused Segment Latency", "Selectivity (%)", "avg_total_time_ms", os.path.join(output_dir, "focused", "latency.png"), [0.0, 1.0, 5.0, 10.0, 20.0, 50.0, 90.0], True)


def read_rows(summary_csv):
    with open(summary_csv, newline="") as f:
        rows = list(csv.DictReader(f))
    cleaned = []
    for row in rows:
        if row["mode"] not in MODES:
            continue
        for col in ("avg_total_time_s", "avg_vectors_processed"):
            row[col] = float(row[col])
        row["runs"] = int(float(row["runs"]))
        cleaned.append(row)
    return cleaned


def mean_records(rows, group_keys):
    groups = defaultdict(list)
    for row in rows:
        groups[tuple(row[k] for k in group_keys)].append(row)
    out = []
    for key, vals in groups.items():
        rec = dict(zip(group_keys, key))
        rec["avg_vectors_processed"] = sum(v["avg_vectors_processed"] for v in vals) / len(vals)
        rec["avg_total_time_s"] = sum(v["avg_total_time_s"] for v in vals) / len(vals)
        out.append(rec)
    return out


def format_tick(value, latency=False):
    if latency:
        if value >= 10:
            return "%.1f" % value
        return "%.2f" % value
    return "%s" % format(int(round(value)), ",")


def write_svg_plot(records, x_key, y_key, title, xlabel, ylabel, output_path, line_plot=False, preferred_x=None, latency=False):
    width, height = 1200, 760
    left, right, top, bottom = 155, 70, 80, 155
    plot_w = width - left - right
    plot_h = height - top - bottom
    data_x_values = list(dict.fromkeys(r[x_key] for r in records))
    x_values = list(data_x_values)
    if preferred_x:
        x_values = [x for x in preferred_x if x in data_x_values or (line_plot and isinstance(x, (int, float)) and x == 0)]
    else:
        x_values = sorted(x_values, key=lambda x: (str(type(x)), x))
    scale = 1000.0 if latency else 1.0
    y_values = [r[y_key] * scale for r in records]
    y_min = 0.0
    y_max = max(y_values + [1.0])
    if latency:
        y_max = y_max * 1.08
    else:
        y_min = 0.0
        y_max *= 1.08

    def x_pos(x, mode_index=0):
        if len(x_values) <= 1:
            return left + plot_w / 2
        if not line_plot:
            return left + (x_values.index(x) + 0.5) / len(x_values) * plot_w
        return left + x_values.index(x) / (len(x_values) - 1) * plot_w

    def y_pos(y):
        if y_max <= y_min:
            return top + plot_h
        return top + plot_h - ((y - y_min) / (y_max - y_min)) * plot_h

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="{width/2}" y="44" text-anchor="middle" font-family="Arial" font-size="30" font-weight="600">{title}</text>',
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top+plot_h}" stroke="#333"/>',
        f'<line x1="{left}" y1="{top+plot_h}" x2="{left+plot_w}" y2="{top+plot_h}" stroke="#333"/>',
        f'<text x="34" y="{top + plot_h/2}" transform="rotate(-90 34 {top + plot_h/2})" text-anchor="middle" font-family="Arial" font-size="24">{ylabel}</text>',
        f'<text x="{left + plot_w/2}" y="{height - 42}" text-anchor="middle" font-family="Arial" font-size="24">{xlabel}</text>',
    ]

    for tick in range(6):
        y = y_min + tick / 5 * (y_max - y_min)
        py = y_pos(y)
        parts.append(f'<line x1="{left}" y1="{py:.1f}" x2="{left+plot_w}" y2="{py:.1f}" stroke="#ddd"/>')
        parts.append(f'<text x="{left-14}" y="{py+7:.1f}" text-anchor="end" font-family="Arial" font-size="20">{format_tick(y, latency)}</text>')

    for x in x_values:
        px = x_pos(x)
        parts.append(f'<text x="{px:.1f}" y="{top+plot_h+46}" text-anchor="middle" font-family="Arial" font-size="20">{x}</text>')

    for mode_index, mode in enumerate(MODES):
        sub = [r for r in records if r["mode"] == mode]
        sub.sort(key=lambda r: x_values.index(r[x_key]))
        if line_plot:
            points = " ".join(f'{x_pos(r[x_key], mode_index):.1f},{y_pos(r[y_key] * scale):.1f}' for r in sub)
            parts.append(f'<polyline points="{points}" fill="none" stroke="{COLORS[mode]}" stroke-width="4"/>')
            for r in sub:
                parts.append(f'<circle cx="{x_pos(r[x_key], mode_index):.1f}" cy="{y_pos(r[y_key] * scale):.1f}" r="6" fill="{COLORS[mode]}"/>')
        else:
            bar_w = min(95, plot_w / max(1, len(x_values)) * 0.26)
            offset = -bar_w * 0.58 if mode_index == 0 else bar_w * 0.58
            for r in sub:
                cx = x_pos(r[x_key], mode_index) + offset
                py = y_pos(r[y_key] * scale)
                parts.append(f'<rect x="{cx - bar_w / 2:.1f}" y="{py:.1f}" width="{bar_w:.1f}" height="{top + plot_h - py:.1f}" fill="{COLORS[mode]}"/>')

    legend_x = left + plot_w - 330
    for i, mode in enumerate(MODES):
        y = top + 36 + i * 38
        parts.append(f'<rect x="{legend_x}" y="{y-22}" width="24" height="24" fill="{COLORS[mode]}"/>')
        parts.append(f'<text x="{legend_x+34}" y="{y}" font-family="Arial" font-size="22">{LABELS[mode]}</text>')

    parts.append("</svg>")
    with open(output_path, "w") as f:
        f.write("\n".join(parts))


def fallback_svg(summary_csv, output_dir):
    ensure_dirs(output_dir)
    rows = read_rows(summary_csv)

    layout = []
    for row in rows:
        if row["suite"] != "layout_selectivity":
            continue
        layout_name, sel = parse_layout_query(row["query_name"])
        if layout_name is None:
            continue
        row = dict(row)
        row["layout"] = layout_name
        row["selectivity"] = sel
        layout.append(row)

    selectivity_order = [0.0, 0.1, 1.0, 5.0, 10.0, 20.0, 50.0, 90.0]
    block = [r for r in layout if r["layout"] == "block_sorted"]
    write_svg_plot(block, "selectivity", "avg_vectors_processed", "Experiment 1: Selectivity vs Vectors Processed", "Selectivity (%)", "avg_vectors_processed", os.path.join(output_dir, "selectivity", "vectors_processed.svg"), True, selectivity_order)
    write_svg_plot(block, "selectivity", "avg_total_time_s", "Experiment 1: Selectivity vs Latency", "Selectivity (%)", "avg_total_time_ms", os.path.join(output_dir, "selectivity", "latency.svg"), True, selectivity_order, True)

    layout_avg = mean_records(layout, ["layout", "mode"])
    layout_order = ["random", "sorted", "block_sorted"]
    write_svg_plot(layout_avg, "layout", "avg_vectors_processed", "Experiment 2: Layout vs Vectors Processed", "Physical Layout", "avg_vectors_processed", os.path.join(output_dir, "layout", "vectors_processed.svg"), False, layout_order)
    write_svg_plot(layout_avg, "layout", "avg_total_time_s", "Experiment 2: Layout vs Latency", "Physical Layout", "avg_total_time_ms", os.path.join(output_dir, "layout", "latency.svg"), False, layout_order, True)

    ndv = []
    for row in rows:
        if row["suite"] != "ndv_selectivity":
            continue
        ndv_name, sel = parse_ndv_selectivity_query(row["query_name"])
        if ndv_name is None:
            continue
        row = dict(row)
        row["ndv"] = ndv_name
        row["selectivity"] = sel
        ndv.append(row)
    ndv_avg = mean_records(ndv, ["ndv", "mode"])
    ndv_order = ["low", "medium", "high"]
    write_svg_plot(ndv_avg, "ndv", "avg_vectors_processed", "Experiment 3: NDV vs Vectors Processed", "NDV Level", "avg_vectors_processed", os.path.join(output_dir, "ndv", "vectors_processed.svg"), False, ndv_order)
    write_svg_plot(ndv_avg, "ndv", "avg_total_time_s", "Experiment 3: NDV vs Latency", "NDV Level", "avg_total_time_ms", os.path.join(output_dir, "ndv", "latency.svg"), False, ndv_order, True)

    dist = []
    for row in rows:
        if row["suite"] != "distribution_predicates":
            continue
        distribution, pred, target = parse_distribution_query(row["query_name"])
        if distribution is None:
            continue
        row = dict(row)
        row["distribution"] = distribution
        row["predicate"] = pred
        row["target"] = target
        dist.append(row)
    dist_avg = mean_records(dist, ["distribution", "mode"])
    dist_order = ["uniform", "hotspot"]
    write_svg_plot(dist_avg, "distribution", "avg_vectors_processed", "Experiment 4: Distribution vs Vectors Processed", "Distribution", "avg_vectors_processed", os.path.join(output_dir, "distribution", "vectors_processed.svg"), False, dist_order)
    write_svg_plot(dist_avg, "distribution", "avg_total_time_s", "Experiment 4: Distribution vs Latency", "Distribution", "avg_total_time_ms", os.path.join(output_dir, "distribution", "latency.svg"), False, dist_order, True)

    pred = []
    for row in rows:
        if row["suite"] != "ndv_predicates":
            continue
        ndv_name, predicate = parse_ndv_predicate_query(row["query_name"])
        if ndv_name is None:
            continue
        row = dict(row)
        row["ndv"] = ndv_name
        row["predicate"] = predicate
        pred.append(row)
    pred_avg = mean_records(pred, ["predicate", "mode"])
    pred_order = ["eq", "lt", "between", "conjunct"]
    write_svg_plot(pred_avg, "predicate", "avg_vectors_processed", "Experiment 5: Predicate Type vs Vectors Processed", "Predicate Type", "avg_vectors_processed", os.path.join(output_dir, "predicate", "vectors_processed.svg"), False, pred_order)
    write_svg_plot(pred_avg, "predicate", "avg_total_time_s", "Experiment 5: Predicate Type vs Latency", "Predicate Type", "avg_total_time_ms", os.path.join(output_dir, "predicate", "latency.svg"), False, pred_order, True)

    focused = [r for r in ndv if r["ndv"] == "medium"]
    focused_order = [0.0, 1.0, 5.0, 10.0, 20.0, 50.0, 90.0]
    write_svg_plot(focused, "selectivity", "avg_vectors_processed", "Experiment 6: Medium-NDV Focused Segment Comparison", "Selectivity (%)", "avg_vectors_processed", os.path.join(output_dir, "focused", "vectors_processed.svg"), True, focused_order)
    write_svg_plot(focused, "selectivity", "avg_total_time_s", "Experiment 6: Medium-NDV Focused Segment Latency", "Selectivity (%)", "avg_total_time_ms", os.path.join(output_dir, "focused", "latency.svg"), True, focused_order, True)


def main():
    parser = argparse.ArgumentParser(description="Plot focused access-path experiment results.")
    parser.add_argument("--summary-csv", default="experiments/results/explain_metrics_summary.csv")
    parser.add_argument("--output-dir", default="plots")
    args = parser.parse_args()

    try:
        try_pandas_matplotlib(args.summary_csv, args.output_dir)
        print("Wrote PNG plots with pandas/matplotlib to %s" % args.output_dir)
    except ImportError as exc:
        print("pandas/matplotlib unavailable (%s); writing SVG fallback plots" % exc)
        fallback_svg(args.summary_csv, args.output_dir)
        print("Wrote SVG plots to %s" % args.output_dir)


if __name__ == "__main__":
    main()
