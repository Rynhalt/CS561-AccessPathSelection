# RABIT / Bitmap Indexing Implementation Summary

## 1. Executive Summary

The current repository contains a **RABIT-inspired, read-only Group Encoding (GE) implementation integrated into DuckDB table scans as a segment-level pruning path**. It is not a full implementation of the RABIT paper. The implemented engine path builds segment-local GE metadata for eligible integer columns, exposes a `disable_rabit` runtime setting, and uses the metadata during `RowGroup::TemplatedScan` to decide whether the current scan vector/segment can be skipped. The implementation is comparable to the existing segment zonemap and column sketch paths as a pruning mechanism because it runs inside DuckDB scan execution and reports `segments_pruned_by_rabit` plus `vectors_processed`.

The implemented RABIT subset covers the core **Group Encoding query idea**: ordered values are mapped to distinct-value ranks, point bitvectors are stored per distinct value, cumulative group bitvectors are stored per group of value ranks, and a range predicate is evaluated by merging boundary point vectors plus fully covered cumulative group vectors. The code uses sparse row-position lists for point vectors and dense `uint64_t` words for cumulative vectors. It does **not** implement full RABIT update support, delta logs, update buffers, flushing, MVCC/timestamp handling, WAH/RLE/Roaring compression, persistence, table-level/global bitmap indexes, index-only scans, or DuckDB selection-vector filtering.

## 2. Files and Components

### Core DuckDB RABIT Index

- `src/include/duckdb/storage/statistics/rabit_index.hpp`
  - Type: source header, newly added RABIT component.
  - Purpose: declares the GE data structures and query interface.
  - Key classes/functions:
    - `RabitDenseBitVector`
    - `RabitSparsePointBitVector`
    - `RabitGEIndex`
    - `RabitGEIndex::MayHaveMatch(TableFilter &filter) const`
  - Important design evidence:
    ```cpp
    vector<uint32_t> positions;
    vector<uint64_t> words;
    vector<RabitSparsePointBitVector> point;
    vector<RabitDenseBitVector> cumulative;
    ```

- `src/storage/statistics/rabit_index.cpp`
  - Type: source code, newly added RABIT component.
  - Purpose: implements GE construction, range extraction, point-vector merging, and cumulative-vector merging.
  - Key functions:
    - `RabitDenseBitVector::Set`
    - `RabitDenseBitVector::Any`
    - `RabitSparsePointBitVector::Add`
    - `RabitSparsePointBitVector::OrInto`
    - `RabitGEIndex::Build`
    - `RabitGEIndex::ExtractRange`
    - `RabitGEIndex::ExtractConstantRange`
    - `RabitGEIndex::RangeMayHaveMatch`
    - `RabitGEIndex::MergePointRange`
  - Notes: this file contains the actual RABIT/GE algorithm used by DuckDB scans.

- `src/storage/statistics/CMakeLists.txt`
  - Type: build configuration, modified.
  - Purpose: adds `rabit_index.cpp` to `duckdb_storage_statistics`.

### DuckDB Scan Integration

- `src/include/duckdb/storage/table/column_data.hpp`
  - Type: source header, modified.
  - Purpose: stores per-column segment-local RABIT indexes.
  - Key fields/functions:
    - `std::vector<std::shared_ptr<RabitGEIndex>> segment_rabit_indexes`
    - `bool is_rabit_indexed`
    - `ColumnData::CheckRabit(ColumnScanState &state, TableFilter &filter, idx_t index)`
  - Behavior: if the column is not RABIT-indexed, or the requested segment index is missing, `CheckRabit` returns `true`, meaning "do not prune."

- `src/include/duckdb/storage/table/row_group.hpp`
  - Type: source header, modified.
  - Purpose: declares the scan hook:
    - `bool CheckRabitSegments(CollectionScanState &state);`

- `src/storage/table/row_group.cpp`
  - Type: source code, modified.
  - Purpose: integrates RABIT into append-time metadata construction and scan-time pruning.
  - Key functions:
    - `RowGroup::CheckRabitSegments`
    - `RowGroup::TemplatedScan`
    - `RowGroup::sketchAppend`
  - Important behavior:
    - `CheckRabitSegments` checks table filters against the RABIT metadata for the current `state.vector_index`.
    - `TemplatedScan` chooses RABIT first when enabled and available, then sketch, then segment zonemap.
    - `sketchAppend` builds `RabitGEIndex` objects for eligible integer columns.

- `src/include/duckdb/storage/table/scan_state.hpp`
  - Type: source header, modified.
  - Purpose: adds scan options and profiling counters.
  - Key additions:
    - `bool disable_rabit = true;`
    - `atomic<idx_t> segments_pruned_by_rabit;`

- `src/function/table/table_scan.cpp`
  - Type: source code, modified.
  - Purpose: propagates `disable_rabit` into scan options and prints RABIT metrics in `EXPLAIN ANALYZE`.
  - Key output:
    - `segments_pruned_by_rabit`

### Runtime Setting

- `src/include/duckdb/main/client_config.hpp`
  - Type: source header, modified.
  - Purpose: adds session-level client config field:
    - `bool disable_rabit = true;`

- `src/include/duckdb/main/settings.hpp`
  - Type: source header, modified.
  - Purpose: declares `DisableRabitSetting`.
  - Setting name:
    - `disable_rabit`

- `src/main/settings/settings.cpp`
  - Type: source code, modified.
  - Purpose: implements `DisableRabitSetting::SetLocal`, `ResetLocal`, and `GetSetting`.

- `src/main/config.cpp`
  - Type: source code, modified.
  - Purpose: registers `DisableRabitSetting` with DuckDB settings.

### Experiment Automation and Plotting

- `experiments/run_explain_suite.py`
  - Type: Python script, modified.
  - Purpose: runs EXPLAIN ANALYZE workloads and parses metrics.
  - RABIT-related behavior:
    - Adds mode `rowgroup_plus_rabit`.
    - Emits `SET disable_rabit=false` for that mode.
    - Parses `segments_pruned_by_rabit`.
    - Writes `disable_rabit` and `segments_pruned_by_rabit` to CSV.

- `experiments/run_explain_workflow.py`
  - Type: Python script, modified.
  - Purpose: chunked top-level experiment workflow.
  - RABIT-related behavior:
    - Includes `rowgroup_plus_rabit` in `DEFAULT_MODES`.
    - Merges RABIT metrics into per-suite and cumulative CSV outputs.

- `experiments/plot_access_path_analysis.py`
  - Type: Python plotting script, modified.
  - Purpose: plots access-path results.
  - RABIT-related behavior:
    - Adds `RABIT_MODE = "rowgroup_plus_rabit"`.
    - Labels it `RABIT GE`.
    - Uses blue as the RABIT color.
    - Supports combining multiple summary CSV files.

### Documentation and Results

- `experiments/RABIT_GE_PROTOTYPE.md`
  - Type: documentation.
  - Purpose: describes a standalone C++ RABIT GE prototype design.
  - Important caveat: the document references `experiments/rabit_ge_prototype.cpp`, but that source file is **not present** in the current repository snapshot inspected here.

- `experiments/results/rabit_ge_benchmark.csv`
  - Type: result CSV.
  - Purpose: contains benchmark output for a standalone GE prototype.
  - Caveat: the corresponding source/runner for this CSV was not present in the current repository snapshot, so the report should not treat the standalone prototype as fully reproducible from the checked-in files.

- `experiments/results/explain_metrics_runs_rabit.csv`
- `experiments/results/explain_metrics_summary_rabit.csv`
- `experiments/results/explain_metrics_runs_rabit_layout_selectivity.csv`
- `experiments/results/explain_metrics_summary_rabit_layout_selectivity.csv`
- `experiments/results/chunks_rabit/`
  - Type: result CSVs.
  - Purpose: contain DuckDB-integrated RABIT experiment output.
  - Notes: these files show the experiment pipeline can run `rowgroup_plus_rabit` and collect `segments_pruned_by_rabit`.

## 3. Which RABIT Concepts Are Implemented?

| RABIT concept | Implemented? | Evidence | Notes |
| ------------- | ------------ | -------- | ----- |
| Group Encoding | Yes | `RabitGEIndex` stores `point` and `cumulative` vectors in `rabit_index.hpp`. | This is the core implemented concept. |
| Point bitvectors | Yes | `vector<RabitSparsePointBitVector> point`. | One point vector per distinct value rank. |
| Cumulative group bitvectors | Yes | `vector<RabitDenseBitVector> cumulative`. | One dense bitmap per group of value ranks. |
| Boundary point-vector merging | Yes | `RabitGEIndex::MergePointRange`. | Used for left/right boundary groups in range queries. |
| Full-group cumulative-vector merging | Yes | Inner loop in `RabitGEIndex::RangeMayHaveMatch`. | Uses scalar word-wise OR in DuckDB-integrated code. |
| Sparse/compressed point bitvectors | Partially yes | `RabitSparsePointBitVector::positions` stores row IDs. | This is sparse position-list compression, not WAH/RLE/Roaring. |
| Dense/decompressed cumulative bitvectors | Yes | `RabitDenseBitVector::words` stores packed `uint64_t` words. | Cumulative bitvectors are dense and directly ORed. |
| Intermediate result bitvector | Yes | `RabitDenseBitVector result(num_rows)` in `RangeMayHaveMatch`. | Dense result is used only to answer `Any()`. |
| SIMD merging | Not in DuckDB path | No AVX/immintrin usage in `rabit_index.cpp`. | `RABIT_GE_PROTOTYPE.md` describes optional AVX2, but source is absent. |
| Group-size parameter | Partially yes | `RabitGEIndex(..., idx_t group_size = 256)`. | Configurable in constructor, but no SQL/runtime setting currently exposes it. |
| WAH/RLE/Roaring compression | No | No code for those formats. | Sparse row-id lists are the only compressed point representation. |
| Update support | No | No update hooks in RABIT code. | Read-only metadata. |
| Delta log | No | No matching code. | Full RABIT update architecture is absent. |
| Update buffers | No | No matching code. | Absent. |
| Flushing | No | No RABIT flush path. | Absent. |
| MVCC/timestamps | No | No RABIT timestamp/version logic. | DuckDB scan still handles normal transaction visibility separately. |
| DuckDB scan integration | Yes | `RowGroup::CheckRabitSegments`, `TemplatedScan`, `TableScanOptions::disable_rabit`. | Integrated as segment/vector pruning. |
| DuckDB selection vector integration | No | RABIT returns skip/no-skip only. | Surviving vectors still use normal DuckDB filtering. |
| Row-group-local index | No, more segment-local | Stored in `ColumnData::segment_rabit_indexes` and indexed by `state.vector_index`. | Metadata aligns with scan vectors/segments, not whole row groups. |
| Table-level/global index | No | No global row-id bitmap index. | RABIT metadata is not a secondary index. |

## 4. Conceptual Design of the Implemented RABIT Prototype

The implemented DuckDB RABIT path is a **segment-local GE pruning structure**. It is not a table-level bitmap index. For each indexed segment of an eligible integer column, the code builds a `RabitGEIndex` over the values in that segment.

### Value Mapping

`RabitGEIndex::Build` maps actual values to ordered value ranks:

```cpp
distinct_values = values;
std::sort(distinct_values.begin(), distinct_values.end());
distinct_values.erase(std::unique(distinct_values.begin(), distinct_values.end()), distinct_values.end());
```

During build, each row value is mapped to a rank using `std::lower_bound`:

```cpp
auto value_id = std::lower_bound(distinct_values.begin(), distinct_values.end(), values[row])
              - distinct_values.begin();
auto group_id = value_id / group_size;
```

### Point Vectors

Point vectors are sparse row-position lists:

```cpp
class RabitSparsePointBitVector {
public:
    vector<uint32_t> positions;
};
```

`point[value_id]` contains only the row offsets inside that segment whose value has the corresponding value rank.

### Cumulative Group Vectors

Cumulative group vectors are dense packed bitvectors:

```cpp
class RabitDenseBitVector {
public:
    vector<uint64_t> words;
};
```

Each row sets exactly one cumulative group bit:

```cpp
point[value_id].Add(row);
cumulative[group_id].Set(row);
```

### Range Evaluation

For a predicate such as:

```sql
WHERE a BETWEEN low AND high
```

`RabitGEIndex::RangeMayHaveMatch`:

1. Uses `lower_bound` and `upper_bound` on `distinct_values` to map predicate bounds to value-rank bounds.
2. Computes `low_group` and `high_group`.
3. Allocates a dense intermediate `RabitDenseBitVector result(num_rows)`.
4. If the range falls inside one group, merges only point vectors.
5. Otherwise:
   - merges point vectors for the left boundary group,
   - ORs dense cumulative vectors for fully covered middle groups,
   - merges point vectors for the right boundary group.
6. Returns `result.Any()`.

The result is not returned to DuckDB as row IDs or a selection vector. It is used only as a boolean test: "may this segment contain any matching row?"

### Predicate Support

`RabitGEIndex::ExtractConstantRange` supports integer constants for:

- `=`
- `<`
- `<=`
- `>`
- `>=`

`RabitGEIndex::ExtractRange` also supports `CONJUNCTION_AND` by intersecting child ranges. This covers predicates represented as conjunctions such as `a >= low AND a <= high`.

Unsupported filters return `true` from `MayHaveMatch`, which means RABIT does not prune and the normal scan proceeds.

## 5. Build Path / Index Construction

RABIT metadata is built during append in `RowGroup::sketchAppend`, not by a separate `CREATE INDEX` statement and not by a general DuckDB indexing subsystem.

The relevant code is in `src/storage/table/row_group.cpp`:

- For `INT32`/`UINT32` columns:
  - values are copied into `vector<int64_t> rabit_data`;
  - `std::make_shared<RabitGEIndex>(rabit_data)` is pushed into `col_data.segment_rabit_indexes`;
  - `col_data.is_rabit_indexed = true`.

- For `INT64`/`UINT64` columns:
  - the same process is used.

- For `DOUBLE` columns:
  - the code still builds sketch metadata, but no RABIT index is built in the inspected code.

Important build-path caveat: RABIT construction is currently attached to the `sketchAppend` path. That means it is coupled to the existing sketch-oriented append infrastructure and the set of columns chosen for that path. It is not an independent, general-purpose bitmap index build path.

Index granularity:

- The index is per column segment / scan-vector-sized append chunk, stored in `ColumnData::segment_rabit_indexes`.
- It is not a global table index.
- It is not a whole-row-group index.
- Row IDs inside `RabitGEIndex` are local offsets within the indexed segment values passed to the constructor.

Persistence:

- No RABIT serialization/checkpoint path was found.
- The metadata appears to be rebuilt when tables are created/loaded through the modified append path.
- Persistent database reopen behavior for RABIT metadata is not established by the inspected code.

## 6. Query Execution Path

For a query such as:

```sql
SELECT count(*) FROM t WHERE a BETWEEN 3000 AND 3499;
```

the relevant DuckDB-integrated path is:

1. SQL planning produces a physical table scan with pushed-down `TableFilter` entries.
2. Row-group zonemap pruning may occur before segment-level checks if `disable_zonemap=false`.
3. Inside `RowGroup::TemplatedScan`, the scan computes:
   ```cpp
   bool can_rabit = !scan_options.disable_rabit;
   ```
4. If table filters exist and all filtered columns are RABIT-indexed, `can_rabit` remains true.
5. The segment-level pruning priority is:
   ```cpp
   if (can_rabit) {
       check_result = CheckRabitSegments(state);
   } else if (can_sketch) {
       check_result = CheckSketchSegments(state);
   } else if (!scan_options.disable_segment_zonemap) {
       check_result = CheckZonemapSegments(state);
   }
   ```
6. `CheckRabitSegments` calls:
   ```cpp
   GetColumn(base_column_idx).CheckRabit(..., state.vector_index)
   ```
7. `ColumnData::CheckRabit` calls:
   ```cpp
   segment_rabit_indexes[index]->MayHaveMatch(filter)
   ```
8. `MayHaveMatch` extracts an integer range from the filter and asks `RangeMayHaveMatch`.
9. If `RangeMayHaveMatch` returns false, `CheckRabitSegments` increments:
   ```cpp
   metrics->segments_pruned_by_rabit++;
   ```
   and advances the scan.
10. If RABIT cannot prove the segment is empty, DuckDB scans the vector normally and applies the original filter.

This means RABIT is conservative. It can skip a vector/segment only when the GE metadata proves there is no matching value. It does not use the bitmap result as an exact selection mask for qualifying rows.

## 7. Compression / Sparse-Dense Representation

The implementation uses a sparse/dense hybrid representation:

- Point bitvectors:
  - represented as sparse row-position lists;
  - stored in `RabitSparsePointBitVector::positions`;
  - merged by iterating set row positions and setting bits in a dense result.

- Cumulative group bitvectors:
  - represented as dense packed `uint64_t` arrays;
  - stored in `RabitDenseBitVector::words`;
  - merged into the result with scalar word-wise OR.

- Intermediate result:
  - represented as a dense `RabitDenseBitVector`.

This is a meaningful RABIT-inspired representation because it keeps sparse point vectors compact and uses dense bitvectors for cumulative group merging. However, it is not full paper-level compression:

- No WAH compression.
- No RLE compression.
- No Roaring bitmap.
- No density threshold.
- No adaptive sparse-vs-dense choice per bitvector.
- No compressed cumulative representation.

Compression affects memory directly for point vectors because they store only set row offsets. It may also affect latency because boundary point-vector merging only touches matching row positions rather than scanning an entire dense bitmap. The current code does not expose memory counters for RABIT metadata in EXPLAIN output.

## 8. SIMD / Hardware Acceleration

The DuckDB-integrated RABIT code does **not** currently use SIMD intrinsics.

Evidence:

- `src/storage/statistics/rabit_index.cpp` merges cumulative vectors with a scalar loop:
  ```cpp
  for (idx_t word_idx = 0; word_idx < result.words.size(); word_idx++) {
      result.words[word_idx] |= cumulative[group].words[word_idx];
  }
  ```
- No RABIT source file in `src/storage/statistics` includes `immintrin.h`.
- No `_mm256_*` or `_mm512_*` intrinsics were found in the RABIT DuckDB path.

`experiments/RABIT_GE_PROTOTYPE.md` describes an optional AVX2 dense OR path for a standalone prototype, but the referenced `experiments/rabit_ge_prototype.cpp` file is not present in the inspected repository. Therefore, SIMD should not be claimed for the current checked-in DuckDB implementation.

Natural SIMD target:

- The dense cumulative-vector OR loop in `RabitGEIndex::RangeMayHaveMatch`.
- A future implementation could add AVX2/AVX-512 guarded OR routines for `RabitDenseBitVector`.
- It would need compile-time guards or runtime CPU dispatch to avoid illegal instructions on unsupported hardware.

## 9. DuckDB Integration Status

RABIT is integrated into DuckDB as a segment-level pruning path.

### Metadata Location

Metadata is stored in `ColumnData`:

```cpp
std::vector<std::shared_ptr<RabitGEIndex>> segment_rabit_indexes;
bool is_rabit_indexed = false;
```

This is segment-local metadata, not a table-level secondary index.

### Predicate Extraction

Predicate extraction happens in `RabitGEIndex::ExtractRange` and `ExtractConstantRange`. It currently supports integer constant comparisons and conjunctions of supported predicates. Unsupported predicates cause fallback to "may match" rather than unsafe pruning.

### Scan Role

The integrated RABIT path is used for:

- segment/vector pruning: yes;
- row-group pruning: no;
- selection-vector filtering: no;
- full index scan: no;
- index-only scan: no.

Row-group pruning remains zonemap-based. RABIT is evaluated only after a row group survives and only when `disable_rabit=false`.

### Runtime Flag

The relevant setting is:

```sql
SET disable_rabit=false;
```

Default:

```text
disable_rabit = true
```

The final experiment modes in `experiments/run_explain_suite.py` are:

| Mode | Row-group zonemap | Segment zonemap | Sketch | RABIT |
| ---- | ----------------- | --------------- | ------ | ----- |
| `rowgroup_plus_segment_zonemap` | enabled | enabled | disabled | disabled |
| `rowgroup_plus_sketch` | enabled | disabled | enabled | disabled |
| `rowgroup_plus_rabit` | enabled | disabled | disabled | enabled |

This is the intended apples-to-apples comparison: keep row-group zonemap pruning fixed and vary only the segment-level access path.

### Metrics

`segments_pruned_by_rabit` is added to `TableScanMetrics` and printed in `TableScanToString`, so it appears in `EXPLAIN ANALYZE` scan output and is parsed into CSV by the experiment scripts.

## 10. Correctness Checks

### Existing Correctness Evidence

The DuckDB-integrated path is conservative: RABIT only decides whether a segment may contain a match. If it says "may match," DuckDB still scans the vector and applies the original filter. If `MayHaveMatch` is correct, pruning should not change query results.

Manual CLI output from prior testing showed this kind of check:

```sql
CREATE TABLE t AS
SELECT i::BIGINT AS id, (i % 10000)::INTEGER AS a
FROM range(1000000) r(i);

SET disable_sketch=true;
SET disable_rabit=false;
EXPLAIN ANALYZE
SELECT count(*) FROM t WHERE a BETWEEN 3000 AND 3499;
```

The RABIT-enabled run reported `segments_pruned_by_rabit` greater than zero and returned the expected count of `50000` for `1000000` rows and values `3000..3499` out of `0..9999`.

`experiments/results/rabit_ge_benchmark.csv` also contains fields `result_count`, `expected_count`, and `correct`, indicating that some standalone GE benchmark validated results against a full-scan count. However, the source file that generated this benchmark is not present in the inspected repository, so this evidence is less reproducible from the current checkout.

### Missing Automated Tests

No dedicated unit test file was found for `RabitGEIndex`.

Recommended correctness tests:

- Empty range: `low > high`.
- Range below minimum value.
- Range above maximum value.
- Full domain range.
- Equality on present value.
- Equality on absent value.
- `<`, `<=`, `>`, `>=`.
- Conjunction range: `a >= low AND a <= high`.
- Duplicate values.
- High-NDV values.
- Skewed values.
- Segment with zero matching values should prune.
- Segment with at least one matching value should not prune.
- Compare query counts across:
  - RABIT enabled,
  - RABIT disabled,
  - native DuckDB filter path.

## 11. How to Describe This in the Final Report

### RABIT Implementation Description

We implemented a read-only, RABIT-inspired Group Encoding pruning path inside DuckDB scans. For eligible integer columns, the system builds segment-local metadata consisting of sparse point vectors for distinct values and dense cumulative group bitvectors for groups of ordered value ranks. During scan execution, range predicates are mapped onto value-rank intervals. Boundary values are evaluated through sparse point vectors, while fully covered groups are evaluated through dense cumulative group vectors. The resulting metadata is used conservatively to skip scan vectors/segments that cannot contain qualifying tuples.

### RABIT Methodology Paragraph

The RABIT experiment mode is configured as `rowgroup_plus_rabit`: row-group zonemap pruning remains enabled, segment zonemap and sketch pruning are disabled, and RABIT GE segment pruning is enabled. This allows the experiment to compare RABIT against `rowgroup_plus_segment_zonemap` and `rowgroup_plus_sketch` while holding row-group pruning fixed. We measure `segments_pruned_by_rabit`, `vectors_processed`, and `total_time_s` using `EXPLAIN ANALYZE` and the Python experiment runners.

### RABIT Limitations Paragraph

This is not a full RABIT implementation. The current system does not implement WAH/RLE/Roaring compression, adaptive density-based representation selection, SIMD merging in the DuckDB path, update buffers, delta logs, flushing, MVCC-aware bitmap versions, persistence, selection-vector filtering, or index-only scans. RABIT is currently used only as a segment-level pruning mechanism, so surviving vectors are still scanned and filtered by DuckDB's normal execution engine.

### Future Work Paragraph

A fuller RABIT implementation would add configurable group-size tuning, memory/build-time instrumentation, SIMD OR for dense cumulative bitvector merging, and adaptive sparse/dense representation choices. A deeper DuckDB integration would use the RABIT result to construct selection vectors rather than only skip empty vectors. A paper-level implementation would further require update-aware bitmap maintenance, delta logs, background flushing, MVCC/timestamp support, and persistence across database checkpoints.

## 12. Supported Claims vs Claims to Avoid

### Supported Claims

- The current DuckDB code implements a RABIT-inspired Group Encoding segment-pruning path.
- The implementation is read-only.
- Point vectors are stored as sparse row-position lists.
- Cumulative group vectors are stored as dense packed bitvectors.
- Range predicates are evaluated using boundary point vectors and full-group cumulative vectors.
- RABIT is integrated into DuckDB scan execution as a segment/vector pruning method.
- Row-group pruning remains zonemap-based.
- `segments_pruned_by_rabit` is instrumented and appears in `EXPLAIN ANALYZE`.
- The experiment scripts include a `rowgroup_plus_rabit` mode.
- RABIT currently supports integer constant range/equality predicates and conjunctions of supported range predicates.
- RABIT does not currently produce DuckDB selection vectors.

### Claims to Avoid or Qualify

- Avoid: "We implemented full RABIT."
  - Better: "We implemented a read-only RABIT-inspired Group Encoding pruning path."

- Avoid: "RABIT is a full DuckDB index."
  - Better: "RABIT metadata is segment-local and used during table scan pruning."

- Avoid: "RABIT supports updates."
  - No update architecture was found.

- Avoid: "RABIT uses WAH/Roaring compression."
  - The code uses sparse row-position lists for point vectors, not WAH/RLE/Roaring.

- Avoid: "RABIT uses AVX-512."
  - No AVX-512 code was found in the RABIT implementation.

- Avoid: "RABIT SIMD is implemented in DuckDB."
  - The DuckDB RABIT path uses scalar OR for cumulative vectors.

- Avoid: "RABIT returns exact qualifying rows to DuckDB."
  - The current path returns only a may-match boolean for pruning.

- Avoid: "RABIT results are directly index-only scan results."
  - Surviving vectors are still scanned normally.

## 13. Open Questions / Missing Work

- `experiments/RABIT_GE_PROTOTYPE.md` references `experiments/rabit_ge_prototype.cpp`, but that source file is not present in the current repository snapshot.
- `experiments/results/rabit_ge_benchmark.csv` exists, but the source/runner used to generate it is not present, so reproducibility of that standalone benchmark is unclear.
- RABIT metadata construction is coupled to `RowGroup::sketchAppend`, rather than a standalone RABIT build path.
- RABIT currently indexes integer columns in the inspected append path; `DOUBLE` columns are not RABIT-indexed.
- There is no SQL setting for `group_size`; the constructor default is `256`.
- No RABIT metadata memory counter is exposed.
- No RABIT build-time metric is exposed.
- No RABIT query-time internal metric is exposed beyond `segments_pruned_by_rabit` and scan-level `vectors_processed`.
- No dedicated automated tests for `RabitGEIndex` were found.
- No persistence/checkpoint support for RABIT metadata was found.
- No selection-vector integration exists.
- No SIMD implementation exists in the DuckDB-integrated RABIT path.
- Many `experiments/results/chunks_rabit/` files are currently untracked, and RABIT result CSVs are modified in the working tree.

## 14. Recommended Next Steps

### Must Do Before Final Report

- Add a short correctness test script or SQL smoke test that compares RABIT-enabled and RABIT-disabled query counts.
- State clearly in the report that this is a read-only RABIT-inspired GE pruning path, not full RABIT.
- Report RABIT as segment/vector pruning, not as a table-level bitmap index.
- Use the `rowgroup_plus_rabit` experiment mode for apples-to-apples comparison against:
  - `rowgroup_plus_segment_zonemap`
  - `rowgroup_plus_sketch`
- Include `segments_pruned_by_rabit` and `vectors_processed` in final analysis.
- Decide whether `experiments/results/chunks_rabit/` should be ignored or committed.

### Nice to Have

- Add a small C++ or SQL-level test for `RabitGEIndex` edge cases.
- Add a RABIT metadata memory estimate to CSV output.
- Add build-time instrumentation for RABIT metadata construction.
- Add a `rabit_group_size` setting or experiment parameter.
- Restore or commit the standalone prototype source if `experiments/RABIT_GE_PROTOTYPE.md` remains in the report narrative.
- Run group-size sensitivity experiments.

### Future Work

- Add SIMD OR for dense cumulative bitvector merging with scalar fallback.
- Add adaptive sparse/dense representation based on bit density.
- Add DuckDB selection-vector integration so RABIT can provide exact row offsets within surviving vectors.
- Add persistence/checkpoint support for RABIT metadata.
- Add update support with delta logs, update buffers, flushing, and MVCC/timestamp handling.
- Explore table-level/global bitmap indexes if the goal expands beyond scan-vector pruning.
