# Focused Experimental Report: RowGroup + Segment Zonemap vs RowGroup + Column Sketch

## 1. Core Hypothesis

This experimental plan studies one central comparison:

> **Row-group zonemap pruning held constant, with only the segment-level pruning method changed.**

The two execution modes are:

- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`

The goal is to determine whether column sketches provide meaningful benefit over segment zonemaps once both systems receive the same coarse row-group pruning.

### Hypothesis 1: Sketches Can Reduce More Scan Work Than Segment Zonemaps

Column sketches can reject segments using richer per-segment value information than a min/max zonemap. A segment zonemap can only prune when the predicate range does not overlap the segment min/max range. A sketch can sometimes reject a segment even when the min/max range overlaps the predicate, because the queried values may still be absent from that segment.

In this implementation, that difference should appear as:

- lower `vectors_processed` for `rowgroup_plus_sketch`
- higher `segments_pruned_by_sketch`
- similar `row_groups_pruned_by_zonemap` between both modes

### Hypothesis 2: Lower Scan Work Does Not Always Mean Lower Latency

Sketch pruning adds execution overhead. Even if it reduces `vectors_processed`, the sketch check itself costs CPU time. Therefore, sketch wins only when the work avoided is larger than the sketch evaluation overhead.

This should appear as cases where:

- `rowgroup_plus_sketch` processes fewer vectors
- but `avg_total_time_s` is similar to or worse than `rowgroup_plus_segment_zonemap`

### Hypothesis 3: Sketch Benefit Depends on Selectivity, Layout, NDV, Distribution, and Predicate Type

Sketches are most useful when many surviving row groups contain segments that can be rejected at segment granularity. If row-group zonemaps already prune almost everything, segment-level pruning has little left to do. If data is random and every segment contains many relevant values, neither segment zonemaps nor sketches can prune much.

Predicate support also matters. If a predicate form does not activate the sketch pruning path, sketch mode may behave like row-group-only scanning.

## 2. Experimental Framework

### 2.1 What Is Being Compared

Only two modes should be used in the primary analysis:

| Mode | Row-Group Zonemap | Segment Zonemap | Segment Sketch |
| --- | --- | --- | --- |
| `rowgroup_plus_segment_zonemap` | on | on | off |
| `rowgroup_plus_sketch` | on | off | on |

This is an apples-to-apples comparison because both modes keep row-group zonemap pruning enabled. The only intended difference is the segment-level pruning mechanism.

This avoids mixing two effects:

- coarse row-group pruning
- fine-grained segment pruning

The comparison asks:

> Given the same row groups after coarse pruning, is segment-level sketch pruning better than segment-level zonemap pruning?

### 2.2 Dataset Design

The workloads are synthetic because the system needs controlled variation. Benchmark-style queries are useful for realism, but they make it hard to explain why a pruning method won. Synthetic workloads allow one variable to change at a time while the others are fixed.

The main controlled variables are:

- **Layout**: random, sorted, block-sorted
- **Selectivity**: narrow predicates through broad predicates
- **NDV / cardinality**: low, medium, high number of distinct values
- **Distribution**: uniform vs hotspot/skewed
- **Predicate type**: equality, range, between, conjunctive predicates

Each variable changes the likelihood that a segment can be rejected after row-group pruning.

### 2.3 Why This Setup Is Appropriate

Keeping row-group pruning active in both modes is important because row-group zonemaps are part of the baseline scan path. The experiment should not ask whether coarse pruning matters; it should ask which segment-level method is more useful after coarse pruning has already happened.

This setup is appropriate because:

- `row_groups_pruned_by_zonemap` should be comparable between modes.
- differences in `vectors_processed` can be attributed primarily to segment-level pruning.
- differences in latency can be interpreted as the tradeoff between pruning benefit and metadata-check overhead.
- the comparison directly matches the implementation decision point: segment zonemap fallback vs sketch-based segment pruning.

## 3. Six Core Experiments

## Experiment 1 — Selectivity Sweep

### Purpose

Test how segment-level pruning effectiveness changes as predicate selectivity changes.

### Setup

- Fixed dataset and layout.
- Vary predicate selectivity from approximately `0.1%` to `90%`.
- Compare only:
  - `rowgroup_plus_segment_zonemap`
  - `rowgroup_plus_sketch`

### Why Appropriate

Selectivity controls how many values qualify. Low-selectivity predicates should create more opportunities for pruning. High-selectivity predicates should leave less work to avoid.

Because the dataset is fixed, changes in `vectors_processed` and latency are attributable to predicate selectivity rather than layout, NDV, or distribution changes.

### Metrics

- `avg_vectors_processed`: primary scan-work signal.
- `avg_total_time_s`: end-to-end performance.
- segment pruning counters: diagnostic explanation for why vector counts changed.

### Expected Outcome

Sketch should help most at low to medium selectivity if it can reject segments that segment zonemaps cannot. At high selectivity, both modes should process more vectors, and sketch overhead may dominate.

## Experiment 2 — Layout Sensitivity

### Purpose

Test how physical clustering affects the benefit of segment sketches relative to segment zonemaps.

### Setup

- Compare random, sorted, and block-sorted layouts.
- Use fixed selectivity levels across layouts.
- Compare only:
  - `rowgroup_plus_segment_zonemap`
  - `rowgroup_plus_sketch`

### Why Appropriate

Layout directly affects row-group and segment metadata. Sorted layouts make min/max ranges tighter, which should favor zonemap pruning. Random layouts spread values across segments, which weakens min/max pruning and may expose cases where sketches help.

Because selectivity and predicate structure are fixed, observed differences isolate physical layout effects.

### Metrics

- `avg_vectors_processed`: shows how much scan work survives pruning.
- `avg_total_time_s`: shows whether reduced scan work translates to speed.
- `avg_row_groups_pruned_by_zonemap`: confirms both modes receive the same coarse pruning benefit.

### Expected Outcome

Sorted and block-sorted layouts should reduce scan work through row-group pruning. Sketch may provide extra benefit when row groups survive but many internal segments still do not contain qualifying values. On fully random layouts, sketch may only help if per-segment value absence is still detectable.

## Experiment 3 — NDV / Cardinality

### Purpose

Test how the number of distinct values affects segment-level pruning.

### Setup

- Use low, medium, and high NDV datasets.
- Hold selectivity approximately fixed.
- Compare only:
  - `rowgroup_plus_segment_zonemap`
  - `rowgroup_plus_sketch`

### Why Appropriate

NDV changes how values are distributed inside segments. With low NDV, many segments may contain most queried values, limiting sketch usefulness. With higher NDV, a given predicate may be absent from more segments, increasing sketch pruning opportunities.

The layout and predicate shape should be held constant so that the experiment isolates metadata granularity and value coverage.

### Metrics

- `avg_vectors_processed`: primary indication of segment-level pruning success.
- `avg_total_time_s`: determines whether pruning is worth its cost.
- `avg_segments_pruned_by_sketch` and `avg_segments_pruned_by_zonemap`: explain which method is active.

### Expected Outcome

Sketch should become more useful as NDV increases, especially for range predicates that exclude many values. Segment zonemaps may remain weak if segment min/max ranges are broad despite high NDV.

## Experiment 4 — Distribution / Skew

### Purpose

Test how uneven value distributions affect segment pruning.

### Setup

- Compare uniform and hotspot/skewed datasets.
- Use matched predicates that target:
  - common/hot values
  - less common/cold value regions
- Compare only:
  - `rowgroup_plus_segment_zonemap`
  - `rowgroup_plus_sketch`

### Why Appropriate

Skew changes which values appear repeatedly in many segments. A hotspot value may appear almost everywhere, making it hard for sketches to reject segments. A cold value or cold range may appear sparsely, creating stronger sketch pruning opportunities.

Using matched predicates across uniform and hotspot datasets isolates distribution as the variable.

### Metrics

- `avg_vectors_processed`: shows whether skew changes actual scan work.
- `avg_total_time_s`: shows whether pruning under skew improves latency.
- segment pruning counters: explain whether the effect comes from sketch or zonemap pruning.

### Expected Outcome

Sketch should help more for sparse/cold predicates than for hotspot predicates. For hot predicates, both methods may process many vectors because most segments contain qualifying values.

## Experiment 5 — Predicate Type

### Purpose

Test how predicate form affects whether segment pruning can fire.

### Setup

- Use the same dataset.
- Compare predicate forms:
  - equality
  - less-than / range
  - between
  - optional conjunctive predicates
- Compare only:
  - `rowgroup_plus_segment_zonemap`
  - `rowgroup_plus_sketch`

### Why Appropriate

This exposes implementation-specific behavior. A pruning method may support one predicate form better than another. For example, if sketch pruning is only implemented for certain range-style checks, equality predicates may not benefit even when sketches exist.

Holding the dataset fixed means differences are caused by predicate handling rather than data layout.

### Metrics

- `avg_vectors_processed`: confirms whether the predicate form actually reduces scan work.
- `avg_total_time_s`: captures overhead and execution cost.
- `avg_segments_pruned_by_sketch`: confirms whether sketch pruning activated.

### Expected Outcome

Range and between predicates should be more likely to show sketch pruning. Equality predicates may show little or no sketch benefit if that path does not trigger sketch-based pruning.

## Experiment 6 — Focused Segment-Level Comparison

### Purpose

Directly compare segment zonemap and segment sketch behavior under identical row-group pruning.

### Setup

- Choose one representative dataset where row-group pruning leaves enough surviving row groups for segment-level pruning to matter.
- Run multiple selectivity levels on the same table.
- Compare only:
  - `rowgroup_plus_segment_zonemap`
  - `rowgroup_plus_sketch`

### Why Appropriate

This is the cleanest experiment for the central research question. Row-group pruning is controlled, the table is fixed, and the only changing mechanism is segment-level pruning.

It should be used as the primary figure in the final presentation because it directly answers whether sketches add value over segment zonemaps.

### Metrics

- `avg_vectors_processed`: primary measurement of work avoided.
- `avg_total_time_s`: determines whether work reduction becomes speedup.
- segment pruning counters: verify that the intended access path ran.

### Expected Outcome

Sketch should win when it prunes substantially more vectors. Segment zonemap should win or tie when vector counts are similar, because zonemap checks are cheaper.

## 4. Graph Design

Each experiment should produce exactly two graphs: one for scan work and one for latency. Both graphs should use the same x-axis so the relationship between pruning and runtime is easy to compare.

## Experiment 1 — Selectivity Sweep

### Graph A — Vectors Processed

- **Type**: line plot
- **X-axis**: selectivity
- **Y-axis**: `avg_vectors_processed`
- **Lines**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: how scan work changes as the predicate becomes broader.
- **Expected pattern**: sketch should process fewer vectors at selective predicates; the gap may shrink at high selectivity.

### Graph B — Latency

- **Type**: line plot
- **X-axis**: selectivity
- **Y-axis**: `avg_total_time_s`
- **Lines**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: whether reduced scan work becomes lower query time.
- **Expected pattern**: sketch latency should improve only when pruning benefit exceeds sketch overhead.

## Experiment 2 — Layout Sensitivity

### Graph A — Vectors Processed

- **Type**: grouped bar chart or line plot
- **X-axis**: layout (`random`, `sorted`, `block_sorted`)
- **Y-axis**: `avg_vectors_processed`
- **Lines/bars**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: how physical clustering changes segment-level pruning.
- **Expected pattern**: sorted and block-sorted layouts should reduce vectors; sketch may add benefit inside surviving row groups.

### Graph B — Latency

- **Type**: grouped bar chart or line plot
- **X-axis**: layout
- **Y-axis**: `avg_total_time_s`
- **Lines/bars**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: whether layout-driven pruning affects runtime.
- **Expected pattern**: latency should roughly follow vectors processed, but sketch may be slower when the vector reduction is small.

## Experiment 3 — NDV / Cardinality

### Graph A — Vectors Processed

- **Type**: line plot
- **X-axis**: NDV level (`low`, `medium`, `high`)
- **Y-axis**: `avg_vectors_processed`
- **Lines**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: how value cardinality affects segment pruning.
- **Expected pattern**: sketch should improve as NDV increases if queried values are absent from more segments.

### Graph B — Latency

- **Type**: line plot
- **X-axis**: NDV level
- **Y-axis**: `avg_total_time_s`
- **Lines**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: whether NDV-driven pruning benefit offsets sketch overhead.
- **Expected pattern**: sketch may become faster at medium or high NDV, but may not win at low NDV.

## Experiment 4 — Distribution / Skew

### Graph A — Vectors Processed

- **Type**: grouped bar chart
- **X-axis**: distribution/predicate target (`uniform`, `hotspot_hot`, `hotspot_cold`)
- **Y-axis**: `avg_vectors_processed`
- **Lines/bars**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: whether skew creates or removes pruning opportunities.
- **Expected pattern**: sketch should help more on cold sparse predicates than on hot predicates.

### Graph B — Latency

- **Type**: grouped bar chart
- **X-axis**: distribution/predicate target
- **Y-axis**: `avg_total_time_s`
- **Lines/bars**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: whether skew-sensitive pruning produces speedup.
- **Expected pattern**: sketch should only reduce latency when it sharply lowers vector processing.

## Experiment 5 — Predicate Type

### Graph A — Vectors Processed

- **Type**: grouped bar chart
- **X-axis**: predicate type (`equality`, `range`, `between`, `conjunctive`)
- **Y-axis**: `avg_vectors_processed`
- **Lines/bars**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: which predicate forms activate useful pruning.
- **Expected pattern**: range and between predicates should show clearer sketch benefit than unsupported or weakly supported predicate forms.

### Graph B — Latency

- **Type**: grouped bar chart
- **X-axis**: predicate type
- **Y-axis**: `avg_total_time_s`
- **Lines/bars**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: whether predicate-specific pruning changes runtime.
- **Expected pattern**: if sketch does not prune for a predicate form, segment zonemap should usually tie or win due to lower overhead.

## Experiment 6 — Focused Segment-Level Comparison

### Graph A — Vectors Processed

- **Type**: line plot
- **X-axis**: selectivity or query variant
- **Y-axis**: `avg_vectors_processed`
- **Lines**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: the cleanest direct comparison of segment-level methods.
- **Expected pattern**: sketch should show lower vectors where it has real segment-pruning power.

### Graph B — Latency

- **Type**: line plot
- **X-axis**: same selectivity or query variant
- **Y-axis**: `avg_total_time_s`
- **Lines**: `rowgroup_plus_segment_zonemap`, `rowgroup_plus_sketch`
- **Shows**: whether the direct segment-level scan-work reduction translates to performance.
- **Expected pattern**: sketch wins only at points where vector reduction is large enough to overcome sketch overhead.

## 5. Interpretation

### 5.1 Vectors Processed vs Latency

`vectors_processed` is the best primary measure of scan work in this system because it counts how much data reaches vectorized scan processing after metadata pruning. It is closer to the internal access-path behavior than wall-clock latency.

Latency is still required, but it can be misleading because it includes:

- metadata lookup overhead
- sketch evaluation cost
- query startup cost
- aggregation cost
- cache and scheduling noise
- cluster variability

Therefore:

- if vectors drop and latency drops, sketch is a true win.
- if vectors drop but latency does not, sketch prunes but costs too much.
- if vectors are similar, the cheaper method should usually win.

### 5.2 Key Patterns to Identify

The analysis should classify results into three patterns:

- **Sketch reduces vectors but not latency**: sketch has real pruning power, but overhead cancels the benefit.
- **Sketch reduces both vectors and latency**: sketch is beneficial for this workload.
- **Similar vectors for both modes**: segment zonemap is preferable because it is simpler and cheaper.

This classification makes the results explainable even when latency alone appears noisy.

## 6. Crossover Analysis

A crossover occurs when `rowgroup_plus_sketch` changes from worse or similar to better than `rowgroup_plus_segment_zonemap`.

In the graphs, this appears as:

- the sketch line crossing below the zonemap line in latency
- or the sketch line becoming much lower in `vectors_processed` before latency improves

The interpretation is:

- before the crossover, sketch overhead is larger than the work it avoids.
- after the crossover, sketch pruning avoids enough vector processing to pay for its overhead.

The most important crossover points are likely to occur across:

- selectivity: narrow predicates may favor sketch, broad predicates may not.
- NDV: higher NDV may create more absent values per segment.
- distribution: cold/skewed predicates may give sketch more rejection opportunities.
- layout: sorted layouts may already be handled well by row-group zonemaps, reducing sketch's marginal value.

## 7. Python Visualization Plan

### Input

The plotting script should read the summary CSVs generated by the experiment workflow.

Expected columns:

- `suite`
- `query_name`
- `mode`
- `disable_zonemap`
- `disable_segment_zonemap`
- `disable_sketch`
- `runs`
- `avg_total_time_s`
- `avg_row_groups_pruned_by_zonemap`
- `avg_segments_pruned_by_zonemap`
- `avg_segments_pruned_by_sketch`
- `avg_vectors_processed`

The script should filter to:

- `mode == "rowgroup_plus_segment_zonemap"`
- `mode == "rowgroup_plus_sketch"`

Rows with incomplete repetitions should be marked or excluded from primary plots.

### Plot Generation

Generate one plot group per experiment:

- Experiment 1: selectivity sweep
- Experiment 2: layout sensitivity
- Experiment 3: NDV/cardinality
- Experiment 4: distribution/skew
- Experiment 5: predicate type
- Experiment 6: focused segment-level comparison

Each plot group contains:

- one `vectors_processed` plot
- one `total_time_s` plot

Use consistent method labels:

- `Segment Zonemap`
- `Column Sketch`

Use consistent colors:

- Segment Zonemap: blue
- Column Sketch: orange

### Output

Save plots under a dedicated directory such as:

```text
experiments/plots/focused_segment_comparison/
```

Recommended filenames:

- `experiment_1_selectivity_vectors.png`
- `experiment_1_selectivity_latency.png`
- `experiment_2_layout_vectors.png`
- `experiment_2_layout_latency.png`
- `experiment_3_ndv_vectors.png`
- `experiment_3_ndv_latency.png`
- `experiment_4_distribution_vectors.png`
- `experiment_4_distribution_latency.png`
- `experiment_5_predicate_vectors.png`
- `experiment_5_predicate_latency.png`
- `experiment_6_focused_vectors.png`
- `experiment_6_focused_latency.png`

Plots should be simple:

- no more than two lines or two bars per x-axis group
- clear axis labels
- same y-axis units across related plots when possible
- legends placed consistently
- titles that state the experiment variable and metric

## 8. Key Insights

1. The central comparison should be `rowgroup_plus_segment_zonemap` vs `rowgroup_plus_sketch`, because it controls row-group pruning and isolates the segment-level decision.

2. `vectors_processed` is the primary evidence of scan-work reduction; latency explains whether the reduction was worth the overhead.

3. Sketch is useful only when it rejects segments that segment zonemaps cannot reject after row-group pruning.

4. Segment zonemap is expected to win or tie when vector counts are similar, because its metadata check is cheaper.

5. Layout determines how much work row-group zonemaps remove before segment-level pruning gets a chance to matter.

6. NDV and distribution determine whether queried values are absent from enough segments for sketches to help.

7. Predicate type matters because the sketch path may not support every predicate form equally.

8. The strongest result is not simply "sketch is faster"; the strongest result is identifying when sketch reduces actual scan work and when that work reduction crosses over into a latency win.
