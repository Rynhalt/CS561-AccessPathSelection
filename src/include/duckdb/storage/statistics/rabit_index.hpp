//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/storage/statistics/rabit_index.hpp
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/common/common.hpp"
#include "duckdb/common/vector.hpp"
#include "duckdb/planner/table_filter.hpp"

namespace duckdb {

class RabitDenseBitVector {
public:
	explicit RabitDenseBitVector(idx_t num_bits = 0);

	void Set(idx_t row_id);
	bool Any() const;

	vector<uint64_t> words;
};

class RabitSparsePointBitVector {
public:
	void Add(uint32_t row_id);
	void OrInto(RabitDenseBitVector &out) const;

	vector<uint32_t> positions;
};

class RabitGEIndex {
public:
	RabitGEIndex(const vector<int64_t> &values, idx_t group_size = 256);

	bool MayHaveMatch(TableFilter &filter) const;

private:
	struct RangePredicate {
		bool has_low = false;
		bool has_high = false;
		int64_t low = 0;
		int64_t high = 0;
	};

	void Build(const vector<int64_t> &values);
	bool ExtractRange(TableFilter &filter, RangePredicate &range) const;
	bool ExtractConstantRange(TableFilter &filter, RangePredicate &range) const;
	bool RangeMayHaveMatch(int64_t low, int64_t high) const;
	void MergePointRange(RabitDenseBitVector &result, idx_t start_id, idx_t end_id) const;

	idx_t num_rows;
	idx_t group_size;
	vector<int64_t> distinct_values;
	vector<RabitSparsePointBitVector> point;
	vector<RabitDenseBitVector> cumulative;
};

} // namespace duckdb
