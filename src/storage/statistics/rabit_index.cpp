//===----------------------------------------------------------------------===//
//                         DuckDB
//
// storage/statistics/rabit_index.cpp
//
//===----------------------------------------------------------------------===//

#include "duckdb/storage/statistics/rabit_index.hpp"

#include "duckdb/common/enums/expression_type.hpp"
#include "duckdb/common/limits.hpp"
#include "duckdb/planner/filter/conjunction_filter.hpp"
#include "duckdb/planner/filter/constant_filter.hpp"

namespace duckdb {

RabitDenseBitVector::RabitDenseBitVector(idx_t num_bits) : words((num_bits + 63) / 64, 0) {
}

void RabitDenseBitVector::Set(idx_t row_id) {
	words[row_id >> 6] |= (uint64_t(1) << (row_id & 63));
}

bool RabitDenseBitVector::Any() const {
	for (auto word : words) {
		if (word != 0) {
			return true;
		}
	}
	return false;
}

void RabitSparsePointBitVector::Add(uint32_t row_id) {
	positions.push_back(row_id);
}

void RabitSparsePointBitVector::OrInto(RabitDenseBitVector &out) const {
	for (auto row_id : positions) {
		out.Set(row_id);
	}
}

RabitGEIndex::RabitGEIndex(const vector<int64_t> &values, idx_t group_size_p)
    : num_rows(values.size()), group_size(group_size_p) {
	if (group_size == 0) {
		group_size = 1;
	}
	Build(values);
}

void RabitGEIndex::Build(const vector<int64_t> &values) {
	distinct_values = values;
	std::sort(distinct_values.begin(), distinct_values.end());
	distinct_values.erase(std::unique(distinct_values.begin(), distinct_values.end()), distinct_values.end());

	const auto cardinality = distinct_values.size();
	const auto num_groups = (cardinality + group_size - 1) / group_size;
	point.resize(cardinality);
	cumulative.reserve(num_groups);
	for (idx_t i = 0; i < num_groups; i++) {
		cumulative.emplace_back(num_rows);
	}

	for (idx_t row = 0; row < values.size(); row++) {
		auto value_id = UnsafeNumericCast<idx_t>(
		    std::lower_bound(distinct_values.begin(), distinct_values.end(), values[row]) - distinct_values.begin());
		auto group_id = value_id / group_size;
		point[value_id].Add(UnsafeNumericCast<uint32_t>(row));
		cumulative[group_id].Set(row);
	}
}

bool RabitGEIndex::MayHaveMatch(TableFilter &filter) const {
	RangePredicate range;
	if (!ExtractRange(filter, range)) {
		return true;
	}
	if (!range.has_low) {
		range.low = NumericLimits<int64_t>::Minimum();
	}
	if (!range.has_high) {
		range.high = NumericLimits<int64_t>::Maximum();
	}
	return RangeMayHaveMatch(range.low, range.high);
}

bool RabitGEIndex::ExtractRange(TableFilter &filter, RangePredicate &range) const {
	if (filter.filter_type == TableFilterType::CONSTANT_COMPARISON) {
		return ExtractConstantRange(filter, range);
	}
	if (filter.filter_type != TableFilterType::CONJUNCTION_AND) {
		return false;
	}
	auto &conjunction = filter.Cast<ConjunctionAndFilter>();
	bool found = false;
	for (auto &child : conjunction.child_filters) {
		RangePredicate child_range;
		if (!ExtractRange(*child, child_range)) {
			continue;
		}
		found = true;
		if (child_range.has_low && (!range.has_low || child_range.low > range.low)) {
			range.has_low = true;
			range.low = child_range.low;
		}
		if (child_range.has_high && (!range.has_high || child_range.high < range.high)) {
			range.has_high = true;
			range.high = child_range.high;
		}
	}
	return found;
}

bool RabitGEIndex::ExtractConstantRange(TableFilter &filter, RangePredicate &range) const {
	auto &constant_filter = filter.Cast<ConstantFilter>();
	const auto &constant = constant_filter.constant;
	int64_t value;
	switch (constant.type().InternalType()) {
	case PhysicalType::INT8:
	case PhysicalType::INT16:
	case PhysicalType::INT32:
	case PhysicalType::INT64:
		value = constant.GetValue<int64_t>();
		break;
	case PhysicalType::UINT8:
	case PhysicalType::UINT16:
	case PhysicalType::UINT32:
		value = UnsafeNumericCast<int64_t>(constant.GetValue<uint64_t>());
		break;
	default:
		return false;
	}

	switch (constant_filter.comparison_type) {
	case ExpressionType::COMPARE_EQUAL:
		range.has_low = true;
		range.has_high = true;
		range.low = value;
		range.high = value;
		return true;
	case ExpressionType::COMPARE_LESSTHAN:
		if (value == NumericLimits<int64_t>::Minimum()) {
			range.has_low = true;
			range.has_high = true;
			range.low = 1;
			range.high = 0;
			return true;
		}
		range.has_high = true;
		range.high = value - 1;
		return true;
	case ExpressionType::COMPARE_LESSTHANOREQUALTO:
		range.has_high = true;
		range.high = value;
		return true;
	case ExpressionType::COMPARE_GREATERTHAN:
		if (value == NumericLimits<int64_t>::Maximum()) {
			range.has_low = true;
			range.has_high = true;
			range.low = 1;
			range.high = 0;
			return true;
		}
		range.has_low = true;
		range.low = value + 1;
		return true;
	case ExpressionType::COMPARE_GREATERTHANOREQUALTO:
		range.has_low = true;
		range.low = value;
		return true;
	default:
		return false;
	}
}

bool RabitGEIndex::RangeMayHaveMatch(int64_t low, int64_t high) const {
	if (low > high || distinct_values.empty()) {
		return false;
	}
	auto low_it = std::lower_bound(distinct_values.begin(), distinct_values.end(), low);
	auto high_it = std::upper_bound(distinct_values.begin(), distinct_values.end(), high);
	if (low_it == distinct_values.end() || high_it == distinct_values.begin()) {
		return false;
	}
	--high_it;
	if (low_it > high_it) {
		return false;
	}

	RabitDenseBitVector result(num_rows);
	auto low_id = UnsafeNumericCast<idx_t>(low_it - distinct_values.begin());
	auto high_id = UnsafeNumericCast<idx_t>(high_it - distinct_values.begin());
	auto low_group = low_id / group_size;
	auto high_group = high_id / group_size;
	if (low_group == high_group) {
		MergePointRange(result, low_id, high_id);
		return result.Any();
	}

	auto left_end = MinValue<idx_t>(high_id, ((low_group + 1) * group_size) - 1);
	MergePointRange(result, low_id, left_end);
	for (idx_t group = low_group + 1; group < high_group; group++) {
		for (idx_t word_idx = 0; word_idx < result.words.size(); word_idx++) {
			result.words[word_idx] |= cumulative[group].words[word_idx];
		}
	}
	auto right_start = high_group * group_size;
	MergePointRange(result, right_start, high_id);
	return result.Any();
}

void RabitGEIndex::MergePointRange(RabitDenseBitVector &result, idx_t start_id, idx_t end_id) const {
	for (idx_t value_id = start_id; value_id <= end_id; value_id++) {
		point[value_id].OrInto(result);
	}
}

} // namespace duckdb
