//===----------------------------------------------------------------------===//
//                         DuckDB
//
// duckdb/function/table/table_scan.hpp
//
//
//===----------------------------------------------------------------------===//

#pragma once

#include "duckdb/function/table_function.hpp"
#include "duckdb/common/atomic.hpp"
#include "duckdb/function/built_in_functions.hpp"
#include "duckdb/storage/table/scan_state.hpp"

namespace duckdb {
class DuckTableEntry;
class TableCatalogEntry;

struct TableScanBindData : public TableFunctionData {
	explicit TableScanBindData(DuckTableEntry &table)
	    : table(table), is_index_scan(false), is_create_index(false), scan_metrics(make_shared_ptr<TableScanMetrics>()) {
	}

	//! The table to scan
	DuckTableEntry &table;

	//! Whether or not the table scan is an index scan
	bool is_index_scan;
	//! Whether or not the table scan is for index creation
	bool is_create_index;
	//! The row ids to fetch (in case of an index scan)
	vector<row_t> result_ids;
	//! Per-query scan metrics for this table scan operator
	shared_ptr<TableScanMetrics> scan_metrics;

public:
	bool Equals(const FunctionData &other_p) const override {
		auto &other = other_p.Cast<TableScanBindData>();
		return &other.table == &table && result_ids == other.result_ids;
	}
};

//! The table scan function represents a sequential scan over one of DuckDB's base tables.
struct TableScanFunction {
	static void RegisterFunction(BuiltinFunctions &set);
	static TableFunction GetFunction();
	static TableFunction GetIndexScanFunction();
};

} // namespace duckdb
