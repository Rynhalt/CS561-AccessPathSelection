# Experimental Design and Analysis Plan: Access Path Selection in Modified DuckDB

## 1. Core Experimental Philosophy

### Research Question

The experiments should answer:

> Under what data and query conditions does each access path reduce scan work and improve latency?

The access paths are:

- Row-group zonemap pruning
- Segment-level zonemap pruning
- Segment-level column sketch pruning
- Full scan baseline

The system should not only ask “which query is faster?” It should explain **why** it is faster or slower using internal scan metrics.

### Why Synthetic Workloads Are Necessary

Benchmark-style queries are useful for realism, but they usually combine many factors at once:

- predicate selectivity
- data layout
- value distribution
- NDV/cardinality
- predicate type
- projection width
- cache effects

This makes it hard to explain why an access path wins.

Synthetic workloads are necessary because they let us isolate one factor at a time:

- layout experiment: vary physical clustering only
- NDV experiment: vary cardinality only
- distribution experiment: vary skew only
- predicate experiment: vary predicate shape only

This is important because the implementation makes different pruning decisions depending on metadata granularity and predicate type. Row-group zonemap pruning operates before vector scanning, while sketch pruning runs inside row-group scan execution and has extra evaluation overhead.

### Why Variable Isolation Matters

The system has multiple pruning layers:

1. row-group zonemap pruning
2. segment-level sketch pruning if available
3. segment-level zonemap fallback otherwise
4. regular vector scan/filter

If two experimental variables change at once, the result becomes ambiguous. For example:

- If sorted layout is faster than random layout, is it because row-group zonemap pruned more row groups, or because sketch pruned more segments?
- If high-NDV is faster than low-NDV, is it because fewer rows match, or because metadata becomes more selective?
- If sketch is slower despite processing fewer vectors, is that due to sketch overhead or workload selectivity?

Controlled synthetic experiments make these distinctions visible.

### Why Both Latency and Internal Metrics Are Required

Latency alone is insufficient because this implementation can reduce scan work while adding metadata overhead.

The core metrics are:

- `total_time_s`: end-to-end latency from `EXPLAIN ANALYZE`
- `vectors_processed`: actual vector-level scan work
- `row_groups_pruned_by_zonemap`: coarse row-group pruning
- `segments_pruned_by_zonemap`: segment-level min/max pruning
- `segments_pruned_by_sketch`: segment-level sketch pruning

The most important distinction is:

- `vectors_processed` explains scan work avoided
- `total_time_s` explains whether avoided scan work paid off

A method can win on scan work but lose on latency if metadata evaluation overhead is too high.

## 2. Key Performance Dimensions

### 2.1 Physical Layout / Clustering

**Definition:** The relationship between physical row order and predicate column `a`.

Workloads:

- `random`: rows ordered by `hash(id)`
- `sorted`: rows ordered by `a, id`
- `block_sorted`: rows ordered by coarse `a` buckets

**Effect on row-group pruning:**

Row-group zonemap pruning uses row-group-level min/max statistics. If rows are sorted by `a`, row groups contain narrow `a` ranges, so many row groups can be skipped.

Expected:

- sorted/block-sorted: high `row_groups_pruned_by_zonemap`
- random: low or zero row-group pruning

**Effect on segment pruning:**

Segment zonemap uses column-segment statistics. It can only prune if the entire segment’s min/max is outside the predicate. If segment min/max remains wide, segment zonemap will not help much.

**Effect on sketch:**

Sketch pruning can reject segments even when min/max overlaps the predicate, depending on actual values and sketch support. Sketch can therefore help when zonemap metadata is too coarse.

**Effect on `vectors_processed`:**

Better clustering should reduce vectors processed through row-group pruning. Sketch may reduce vectors further inside surviving row groups.

**Effect on latency:**

Latency should improve when fewer vectors are processed, but sketch overhead may reduce or eliminate the speedup.

### 2.2 Predicate Selectivity

**Definition:** Fraction of table rows satisfying the predicate.

Examples:

- `0.1%`, `1%`, `5%`, `10%`, `20%`, `50%`, `90%`

**Effect on row-group pruning:**

Low selectivity enables more pruning if layout is clustered. High selectivity approaches full scan, so row-group pruning becomes less useful.

**Effect on segment pruning:**

Segment pruning is most useful at low-to-medium selectivity. At high selectivity, most segments contain at least one matching value, so pruning opportunities decrease.

**Effect on sketch:**

Sketch can help when selectivity is low enough that many segments contain no matches. At high selectivity, sketch may evaluate many segments but prune few, increasing overhead.

**Effect on `vectors_processed`:**

Expected monotonic trend:

- lower selectivity -> fewer vectors processed
- higher selectivity -> vectors processed approaches full scan

**Effect on latency:**

Latency may decrease with fewer vectors, but only if pruning overhead is less than scan work saved.

### 2.3 NDV / Cardinality

**Definition:** Number of distinct values in predicate column `a`.

Workloads:

- low NDV: 100
- medium NDV: 10,000
- high NDV: 1,000,000

**Effect on row-group pruning:**

With high NDV and deterministic ordering, predicates can isolate smaller value ranges. With low NDV, each value appears many times across the table, so metadata may remain less selective.

**Effect on segment pruning:**

Segment zonemap only stores min/max. If low NDV values are spread throughout segments, min/max overlap is likely and pruning is weak.

**Effect on sketch:**

Sketch should benefit more when many segments do not contain the requested values/ranges, especially in medium/high NDV cases.

**Effect on `vectors_processed`:**

High NDV should often reduce vectors processed more than low NDV for selective predicates.

**Effect on latency:**

High NDV may show stronger latency gains when pruning substantially reduces scan work. Low NDV may show little benefit.

### 2.4 Distribution / Skew

**Definition:** Whether values are uniformly distributed or concentrated in a hotspot.

Workloads:

- uniform
- hotspot: 80% of rows in a narrow `a` range

**Effect on row-group pruning:**

If hotspot values are physically concentrated or have narrow metadata ranges, row-group zonemap may prune non-overlapping regions. If hotspot values are spread widely, pruning weakens.

**Effect on segment pruning:**

Segment pruning depends on whether segments are dominated by hotspot or tail values. Mixed segments reduce zonemap usefulness.

**Effect on sketch:**

Sketch may distinguish absence of tail/hotspot values better than min/max, especially when min/max overlaps but actual membership differs.

**Effect on `vectors_processed`:**

Hotspot predicates may scan many vectors if the hotspot dominates. Non-hotspot predicates may benefit more from pruning.

**Effect on latency:**

Latency depends on whether pruning avoids scan work or only adds overhead on frequent-value predicates.

### 2.5 Predicate Type

**Definition:** Query predicate form.

Examples:

- equality: `a = c`
- range: `a < c`
- bounded range: `a BETWEEN c1 AND c2`
- conjunctive: `a BETWEEN ... AND b >= ...`

**Effect on row-group pruning:**

Zonemap is naturally suited to range predicates because min/max can prove non-overlap.

**Effect on segment pruning:**

Segment zonemap works for predicates where min/max can prove `FILTER_ALWAYS_FALSE`.

**Effect on sketch:**

Current implementation has a limitation: equality sketch pruning returns `NO_PRUNING_POSSIBLE` in `CheckSketchTemplated`. Therefore equality predicates may not benefit from sketch even when conceptually they should.

Conjunctive predicates use sketch bitmask logic and have shown stability issues in some runs.

**Effect on `vectors_processed`:**

Range predicates are the best candidates for sketch-vs-zonemap comparisons. Equality should be treated carefully due to implementation limitations.

**Effect on latency:**

Conjunctive predicates may add overhead and should be analyzed separately from single-predicate filters.

## 3. Canonical Experiment Setups

## Experiment A: Layout Sensitivity Under Selectivity Sweep

### 3.1 Purpose

Test the hypothesis:

> Row-group zonemap pruning is highly sensitive to physical clustering, while sketch pruning can provide additional segment-level pruning inside surviving row groups.

### 3.2 Setup

Dataset:

- `t_layout_random`
- `t_layout_sorted`
- `t_layout_block_sorted`

Generated from same base table:

- 10M rows
- same values
- same schema
- only physical order changes

Queries:

- range predicates on `a`
- selectivity ladder:
  - `0.1%`
  - `1%`
  - `5%`
  - `10%`
  - `20%`
  - `50%`
  - `90%`

Execution modes:

- `none`
- `rowgroup_only`
- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`
- `full`

### 3.3 Why This Setup Is Appropriate

This setup isolates physical layout because table contents are identical across random, sorted, and block-sorted tables. Only row ordering changes.

It is meaningful for this system because row-group zonemap pruning directly depends on row-group min/max ranges. Sorting by `a` should make these ranges tight. Randomizing by `hash(id)` should make ranges wide.

This setup also tests whether sketch pruning adds value after coarse row-group pruning.

### 3.4 Metrics Used

- `vectors_processed`: primary scan-work metric
- `total_time_s`: latency impact
- `row_groups_pruned_by_zonemap`: confirms layout-sensitive coarse pruning
- `segments_pruned_by_sketch`: explains sketch improvement
- `segments_pruned_by_zonemap`: checks whether segment zonemap adds anything

### 3.5 Expected Outcome

Expected:

- Random layout: row-group pruning weak; vectors remain near full scan.
- Sorted/block-sorted: row-group pruning strong at low selectivity.
- `rowgroup_plus_sketch` should often process fewer vectors than `rowgroup_plus_segment_zonemap`.
- Latency may not improve proportionally if sketch overhead is significant.

## Experiment B: Segment-Level Method Comparison Under Fixed Row-Group Pruning

### 3.1 Purpose

Test the hypothesis:

> Given the same row groups surviving coarse pruning, sketch is a stronger segment-level pruning method than segment zonemap.

### 3.2 Setup

Datasets:

- use `layout_selectivity`
- include sorted and block-sorted layouts
- optionally include random layout as negative control

Queries:

- range predicates on `a`
- focus on `0.1%`, `1%`, `5%`, `10%`, `90%`

Execution modes:

- `rowgroup_only`
- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`

### 3.3 Why This Setup Is Appropriate

This is the cleanest segment-level comparison because row-group zonemap is enabled in all three modes.

The comparison isolates the segment-level method:

- `rowgroup_only`: coarse pruning only
- `rowgroup_plus_segment_zonemap`: coarse pruning + segment min/max
- `rowgroup_plus_sketch`: coarse pruning + sketch

Other variables remain fixed:

- same table
- same predicate
- same row-group pruning eligibility
- same scan operator

### 3.4 Metrics Used

- `vectors_processed`: primary metric for scan work avoided
- `total_time_s`: determines if lower scan work improves latency
- `segments_pruned_by_zonemap`: confirms segment zonemap activity
- `segments_pruned_by_sketch`: confirms sketch activity

### 3.5 Expected Outcome

Expected:

- `rowgroup_plus_segment_zonemap` may be close to `rowgroup_only`.
- `rowgroup_plus_sketch` should reduce vectors more often.
- Sketch may not always reduce latency if evaluation overhead dominates.

## Experiment C: NDV Impact on Sketch Effectiveness

### 3.1 Purpose

Test the hypothesis:

> Sketch pruning becomes more useful as NDV increases and predicates become more selective at the segment level.

### 3.2 Setup

Datasets:

- `t_ndv_low`
- `t_ndv_medium`
- `t_ndv_high`

Queries:

- selectivity ladder from `queries_ndv_selectivity_explain.sql`
- focus on `<` range predicates:
  - `1%`
  - `10%`
  - `50%`
  - `90%`

Execution modes:

- `none`
- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`
- `sketch_only`

### 3.3 Why This Setup Is Appropriate

The schema and row count are fixed. Only NDV changes. This isolates how value cardinality affects metadata pruning.

It is meaningful in this implementation because sketch availability and pruning depend on filtered columns having sketches and on sketch evaluation proving no qualifying values. Low NDV may spread frequent values across many segments. Higher NDV may make absence easier to prove.

### 3.4 Metrics Used

- `vectors_processed`: primary scan-work effect
- `total_time_s`: overhead-vs-benefit
- `segments_pruned_by_sketch`: confirms sketch activity
- `row_groups_pruned_by_zonemap`: ensures row-group effects are understood

### 3.5 Expected Outcome

Expected:

- Low NDV: little sketch benefit because each value/range appears broadly.
- Medium/high NDV: sketch reduces vectors more.
- High selectivity (`90%`) should approach full scan and reduce sketch benefit.
- Latency gains are strongest where vector reduction is large.

## Experiment D: Distribution / Skew Sensitivity

### 3.1 Purpose

Test the hypothesis:

> Skew changes pruning effectiveness because hotspot predicates and tail predicates produce different metadata selectivity.

### 3.2 Setup

Datasets:

- `t_dist_uniform`
- `t_dist_hotspot`

Queries:

- equality and range predicates targeting:
  - hotspot values/ranges
  - non-hotspot values/ranges

Execution modes:

- `none`
- `rowgroup_only`
- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`
- `full`

### 3.3 Why This Setup Is Appropriate

The query file contains matched probes for uniform and hotspot tables. This isolates distribution shape while keeping predicate forms and schema fixed.

It reveals behavior specific to this system because zonemap and sketch pruning are sensitive to whether values are concentrated or spread across segments.

### 3.4 Metrics Used

- `vectors_processed`: scan work
- `total_time_s`: observed performance
- `segments_pruned_by_sketch`: sketch effectiveness under skew
- `row_groups_pruned_by_zonemap`: coarse pruning under skew

### 3.5 Expected Outcome

Expected:

- Non-hotspot predicates may benefit more from pruning.
- Hotspot predicates may scan more vectors because many segments contain matching values.
- Sketch may outperform segment zonemap when min/max overlaps but actual membership is sparse.

## Experiment E: Predicate-Type Sensitivity

### 3.1 Purpose

Test the hypothesis:

> Predicate form affects whether sketch and zonemap pruning can fire, and current sketch implementation is weaker for equality predicates.

### 3.2 Setup

Datasets:

- `t_ndv_low`
- `t_ndv_medium`
- `t_ndv_high`

Queries:

- `=`
- `<`
- `BETWEEN`
- conjunctive predicates

Execution modes:

- `none`
- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`
- `full`

### 3.3 Why This Setup Is Appropriate

This setup holds NDV groups fixed while varying predicate class. It exposes implementation-specific pruning behavior.

It is especially important because equality sketch pruning currently appears limited in code, while range predicates are better supported.

### 3.4 Metrics Used

- `vectors_processed`: scan work
- `total_time_s`: overhead
- `segments_pruned_by_sketch`: whether sketch fires
- `runs`: detect missing/failed runs

### 3.5 Expected Outcome

Expected:

- Range predicates should show stronger sketch pruning than equality.
- Equality predicates may not benefit from sketch due to current implementation.
- Conjunctive predicates may be unstable and should be reported carefully.

## 3.5 Focused Comparisons

The experiment space is large. The final report should not compare all modes simultaneously. It should focus on a small number of high-signal comparisons.

### Comparison 1: RowGroup + Sketch vs RowGroup + Segment Zonemap

Modes:

- `rowgroup_plus_sketch`
- `rowgroup_plus_segment_zonemap`

Controlled variation:

- selectivity sweep
- layout: random, sorted, block-sorted
- NDV: at least low/medium/high

Metrics:

- primary: `vectors_processed`
- secondary: `total_time_s`

Why meaningful:

- Both modes keep row-group zonemap enabled.
- The only intended difference is segment-level method.
- This isolates sketch vs segment zonemap under the same coarse pruning.

Behavior revealed:

- Whether sketch reduces scan work more than segment zonemap.
- Whether sketch overhead offsets scan-work reduction.

Interesting results:

- Sketch reduces vectors but latency does not improve.
- Segment zonemap matches sketch at low overhead.
- Sketch overtakes zonemap only at low selectivity or high NDV.

### Comparison 2: RowGroup Only vs RowGroup + Segment Zonemap

Modes:

- `rowgroup_only`
- `rowgroup_plus_segment_zonemap`

Controlled variation:

- layout selectivity sweep
- distribution predicates

Metrics:

- `vectors_processed`
- `segments_pruned_by_zonemap`
- `total_time_s`

Why meaningful:

- Measures the marginal value of segment zonemap after row-group pruning.

Behavior revealed:

- Whether segment zonemap contributes anything beyond row-group zonemap.
- Whether segment zonemap counters correspond to meaningful vector reduction.

Interesting results:

- Segment zonemap prunes segments but vectors barely decrease.
- Segment zonemap has near-zero benefit, indicating row-group pruning dominates.

### Comparison 3: RowGroup Only vs RowGroup + Sketch

Modes:

- `rowgroup_only`
- `rowgroup_plus_sketch`

Controlled variation:

- layout selectivity sweep
- NDV selectivity sweep

Metrics:

- `vectors_processed`
- `segments_pruned_by_sketch`
- `total_time_s`

Why meaningful:

- Measures marginal value of sketch beyond row-group zonemap.

Behavior revealed:

- Whether sketch acts as useful fine-grained pruning.
- Whether sketch overhead is justified.

Interesting results:

- Large vector reduction with small latency gain.
- Large vector reduction with worse latency.
- No vector reduction at high selectivity.

### Comparison 4: Full Zonemap vs Full Scan

Modes:

- `zonemap_only`
- `none`

Controlled variation:

- layout: random vs sorted/block-sorted
- selectivity

Metrics:

- `vectors_processed`
- `row_groups_pruned_by_zonemap`
- `segments_pruned_by_zonemap`
- `total_time_s`

Why meaningful:

- Establishes the baseline value of DuckDB-style zonemap pruning without sketch.

Behavior revealed:

- How much classic metadata pruning helps.
- How much physical layout matters.

Interesting results:

- Sorted layout sharply reduces vectors.
- Random layout behaves like full scan.
- Segment zonemap adds little beyond row-group zonemap.

### Comparison 5: Sketch Only vs Segment Zonemap Only

Modes:

- `sketch_only`
- `segment_zonemap_only`

Controlled variation:

- selectivity sweep
- one sorted/block-sorted layout
- one NDV sweep

Metrics:

- `vectors_processed`
- `segments_pruned_by_sketch`
- `segments_pruned_by_zonemap`
- `total_time_s`

Why meaningful:

- Tests each segment-level method without row-group pruning.
- This is a sanity-check comparison, not the primary report result.

Behavior revealed:

- Whether segment zonemap actually runs.
- Whether sketch can prune where segment zonemap cannot.

Interesting results:

- Segment zonemap prunes few segments but sketch prunes many.
- Sketch has more overhead but much lower scan work.
- Segment zonemap-only approaches full scan.

### Comparison 6: Full System vs Best Baseline

Modes:

- `full`
- `zonemap_only`
- `rowgroup_plus_sketch`

Controlled variation:

- selectivity
- layout
- NDV

Metrics:

- `vectors_processed`
- `total_time_s`

Why meaningful:

- Determines whether the full system behaves like “zonemap + useful sketch” or merely adds overhead.

Behavior revealed:

- Whether sketch improves over zonemap-only.
- Whether full system is dominated by row-group pruning.

Interesting results:

- Full and rowgroup_plus_sketch identical in vectors.
- Full faster or slower depending on overhead.
- Full no better than zonemap-only when sketch does not prune.

## 4. Graph Design

## 4.1 Selectivity Sweep

### Graph A: Latency vs Selectivity

Type:

- line plot

X-axis:

- selectivity percentage

Y-axis:

- `avg_total_time_s`

Series:

- `none`
- `rowgroup_only`
- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`
- `full`

Facet:

- layout or NDV

Insight:

- Shows when pruning improves wall-clock performance.

Pattern to look for:

- sketch lower latency at low selectivity
- latency convergence at high selectivity
- sketch overhead causing higher latency despite lower scan work

### Graph B: Vectors Processed vs Selectivity

Type:

- line plot

X-axis:

- selectivity percentage

Y-axis:

- `avg_vectors_processed`

Series:

- same as above

Insight:

- Shows actual scan work avoided.

Pattern to look for:

- sorted/block-sorted row-group pruning drops sharply
- random layout stays near full scan
- sketch line below segment zonemap line

## 4.2 Layout Sensitivity

### Graph C: Vectors Processed by Layout

Type:

- grouped bar chart

X-axis:

- layout: random, sorted, block-sorted

Y-axis:

- `avg_vectors_processed`

Series:

- `none`
- `rowgroup_only`
- `rowgroup_plus_sketch`

Facet:

- selectivity level

Insight:

- Demonstrates physical layout dependence.

Pattern to look for:

- sorted/block-sorted much lower than random
- sketch improvement inside sorted/block-sorted surviving row groups
- random may show limited zonemap benefit

### Graph D: Row Groups Pruned by Layout

Type:

- grouped bar chart

X-axis:

- layout

Y-axis:

- `avg_row_groups_pruned_by_zonemap`

Series:

- `rowgroup_only`
- `zonemap_only`
- `full`

Insight:

- Confirms that layout effects are caused by row-group zonemap pruning.

Pattern to look for:

- high row-group prunes in sorted/block-sorted
- low row-group prunes in random

## 4.3 NDV Impact

### Graph E: Vectors Processed vs NDV

Type:

- line or grouped bar chart

X-axis:

- NDV level: low, medium, high

Y-axis:

- `avg_vectors_processed`

Series:

- `rowgroup_plus_segment_zonemap`
- `rowgroup_plus_sketch`
- `none`

Facet:

- selectivity level

Insight:

- Shows whether sketch benefits increase with cardinality.

Pattern to look for:

- low NDV near full scan
- medium/high NDV lower vectors with sketch
- high selectivity reducing pruning benefit

### Graph F: Latency vs NDV

Type:

- line or grouped bar chart

X-axis:

- NDV level

Y-axis:

- `avg_total_time_s`

Series:

- same as Graph E

Insight:

- Shows whether scan-work reductions translate into latency reductions.

Pattern to look for:

- sketch faster only where vector reduction is large
- sketch overhead visible at low benefit points

## 4.4 Pruning vs Work

### Graph G: Segments Pruned vs Vectors Processed

Type:

- scatter plot

X-axis:

- `avg_segments_pruned_by_sketch` or `avg_segments_pruned_by_zonemap`

Y-axis:

- `avg_vectors_processed`

Color:

- mode

Shape/facet:

- suite

Insight:

- Shows whether pruning counters correlate with reduced scan work.

Pattern to look for:

- sketch: higher prunes generally lower vectors
- segment zonemap: few prunes, sometimes little vector reduction
- outliers where pruning count is high but vectors remain high

### Graph H: Vectors Processed vs Latency

Type:

- scatter plot

X-axis:

- `avg_vectors_processed`

Y-axis:

- `avg_total_time_s`

Color:

- mode

Facet:

- suite

Insight:

- Separates scan-work reduction from runtime overhead.

Pattern to look for:

- lower vectors but equal/higher latency indicates metadata overhead
- strong positive trend indicates scan work dominates

## 5. Metric Interpretation

### Why `vectors_processed` Is the Most Important Scan-Work Metric

`vectors_processed` is incremented only when a vector survives metadata pruning and proceeds into scan/filter processing.

It directly captures avoided scan work.

This is better than raw prune counters because one prune event may not represent the same amount of skipped work across mechanisms. In current results, one segment-zonemap prune can correspond to a large row-group-sized skip, while sketch prune counts may correspond to different effective units.

### When Latency Is Misleading

Latency includes:

- metadata check overhead
- sketch evaluation overhead
- vector scan/filter time
- profiler overhead
- cache effects

Examples:

- Sketch may reduce vectors but not improve latency if sketch evaluation is expensive.
- Segment zonemap may show similar latency to rowgroup-only because min/max checks are cheap but do not prune much.
- Very small queries may show noisy timings.

### How to Interpret Pruning Counters

Use counters to explain mechanisms, not as the primary performance metric.

- `row_groups_pruned_by_zonemap`: coarse skip mechanism
- `segments_pruned_by_zonemap`: segment min/max skip mechanism
- `segments_pruned_by_sketch`: sketch skip mechanism
- `vectors_processed`: final scan work

Concrete examples:

- High sketch pruning + low vectors + unchanged latency:
  - sketch reduces work but overhead offsets benefit
- Low segment zonemap pruning + same vectors:
  - segment zonemap adds little beyond row-group pruning
- High row-group pruning + low vectors:
  - physical layout enables coarse pruning

## 6. Crossover Analysis

### What Is a Crossover?

A crossover occurs when one access path becomes better than another as workload conditions change.

Primary crossover:

```text
rowgroup_plus_segment_zonemap
vs
rowgroup_plus_sketch
```

### How to Detect Sketch Becomes Better

In graphs:

- `rowgroup_plus_sketch` line falls below `rowgroup_plus_segment_zonemap` in `vectors_processed`.
- If latency also falls below, sketch wins end-to-end.
- If vectors fall but latency does not, sketch wins scan work but not runtime.

Why it happens:

- At low selectivity or higher NDV, sketch can reject many segments.
- Work avoided exceeds sketch evaluation overhead.

### How to Detect Zonemap Dominates

In graphs:

- `rowgroup_plus_segment_zonemap` and `rowgroup_plus_sketch` have similar vectors.
- Segment zonemap latency is lower.
- Sketch prunes few or no segments.

Why it happens:

- Row-group zonemap already removed most irrelevant data.
- Remaining segments mostly contain matches.
- Sketch overhead is not justified.

### What Thresholds to Look For

For each selectivity sweep, identify:

- lowest selectivity where sketch improves latency
- selectivity where sketch and zonemap converge
- selectivity where sketch still reduces vectors but no longer improves latency

Report both:

- scan-work crossover
- latency crossover

They may differ.

## 7. Limitations and Pitfalls

### Instrumentation Limitations

Current metrics do not include:

- predicate checks
- sketch evaluation time
- zonemap evaluation time
- output tuples as a custom counter
- bytes read
- cache misses
- RABIT/bitmap counters

`vectors_processed` is useful but not a full CPU cost model.

### Comparison Fairness Issues

Potential unfairness:

- `full` prioritizes sketch over segment zonemap, so it does not measure both segment methods simultaneously.
- `zonemap_only` includes both row-group and segment zonemap.
- `sketch_only` disables row-group zonemap, so it is not directly comparable to `zonemap_only` for segment-level conclusions.
- Use `rowgroup_plus_segment_zonemap` vs `rowgroup_plus_sketch` for the clean comparison.

### Sketch Limitations

Known from implementation:

- Equality sketch pruning currently returns `NO_PRUNING_POSSIBLE`.
- Sketch support is limited to numeric types: `INT32`, `UINT32`, `INT64`, `UINT64`, `DOUBLE`.
- `DOUBLE` is encoded into order-preserving `uint64_t`.
- Sketches appear to be in-memory `ColumnData` structures; persistence/reopen behavior is uncertain or incomplete.
- Conjunctive predicates have caused segfaults in some runs.

### Stability Issues

Some `ndv_predicates` conjunctive sketch/full modes had fewer than 10 completed runs due to DuckDB segfaults.

These rows should be:

- marked in tables
- excluded from latency-sensitive conclusions if necessary
- discussed as implementation instability

### Segment Zonemap Interpretation

Segment zonemap may prune very little because current segment granularity/statistics are coarse. This does not necessarily mean the counter is wrong. It may mean segment min/max is weak for these layouts.

## 8. Python Visualization Plan

### Expected CSV Schema

Input summary CSV:

```text
suite
query_name
mode
disable_zonemap
disable_segment_zonemap
disable_sketch
runs
avg_total_time_s
avg_row_groups_pruned_by_zonemap
avg_segments_pruned_by_zonemap
avg_segments_pruned_by_sketch
avg_vectors_processed
```

Input run CSV:

```text
suite
query_name
disable_zonemap
disable_segment_zonemap
disable_sketch
mode
run
total_time_s
row_groups_pruned_by_zonemap
segments_pruned_by_zonemap
segments_pruned_by_sketch
vectors_processed
```

### Derived Columns

Create parser-derived columns:

- `layout`: random/sorted/block from query name
- `selectivity`: numeric percent from query name
- `ndv_level`: low/medium/high
- `predicate_type`: eq/lt/between/conjunct
- `distribution`: uniform/hotspot
- `probe_type`: hotspot/nonhotspot

### Plot Structure

Organize plots by experiment:

```text
plots/
  layout/
    latency_vs_selectivity.png
    vectors_vs_selectivity.png
    rowgroups_pruned_by_layout.png

  ndv/
    vectors_vs_ndv.png
    latency_vs_ndv.png

  distribution/
    vectors_by_distribution.png
    latency_by_distribution.png

  focused_comparisons/
    rowgroup_sketch_vs_segment_zonemap_vectors.png
    rowgroup_sketch_vs_segment_zonemap_latency.png
    vectors_vs_latency_scatter.png
    pruning_vs_vectors_scatter.png
```

### Grouping Logic

For layout plots:

- group by `layout`
- x-axis selectivity
- series by mode

For NDV plots:

- group by `ndv_level`
- facet by selectivity or predicate type
- series by mode

For distribution plots:

- group by table distribution and probe type
- compare modes as bars

For focused comparisons:

- filter to only selected modes:
  - `rowgroup_only`
  - `rowgroup_plus_segment_zonemap`
  - `rowgroup_plus_sketch`
  - `none`
  - `full`

### Visualization Rules

Use consistent colors:

```text
none: gray
rowgroup_only: blue
rowgroup_plus_segment_zonemap: orange
rowgroup_plus_sketch: green
zonemap_only: red
sketch_only: purple
full: black
segment_zonemap_only: brown
```

Rules:

- Always show `vectors_processed` and latency separately.
- Do not put all modes on every plot.
- Use log-scale y-axis only if explicitly noted.
- Mark rows with `runs < expected_repetitions`.
- Use clear titles that state the controlled variable.

## 9. Key Insights

1. Row-group zonemap pruning wins when physical layout clusters predicate values.

2. Random layout weakens zonemap pruning because row-group min/max ranges become wide.

3. Segment zonemap adds little beyond row-group zonemap in current workloads.

4. Sketch pruning is generally stronger than segment zonemap for reducing `vectors_processed`.

5. Sketch does not always improve latency because sketch evaluation has overhead.

6. `vectors_processed` is the clearest measure of scan work avoided.

7. Latency must be interpreted alongside internal metrics; lower scan work does not guarantee faster runtime.

8. NDV matters: medium/high NDV can create more sketch pruning opportunities than low NDV.

9. Predicate type matters: range predicates are more informative than equality predicates for current sketch implementation.

10. The cleanest core comparison is `rowgroup_plus_segment_zonemap` vs `rowgroup_plus_sketch`, because it holds row-group pruning constant and isolates the segment-level method.
