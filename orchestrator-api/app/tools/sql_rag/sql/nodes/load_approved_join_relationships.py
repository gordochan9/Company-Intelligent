from __future__ import annotations

from app.tools.sql_rag.sql.services.repository import list_approved_joins
from app.tools.sql_rag.sql.services.schema import load_current_approved_joins
from app.tools.sql_rag.sql.state import SqlState, fail_state


def load_approved_join_relationships(state: SqlState) -> SqlState:
    schema = state.get("filtered_sql_schema")
    if not isinstance(schema, dict):
        return fail_state("load_approved_join_relationships", "missing_filtered_sql_schema", "SQL schema is unavailable.")
    try:
        all_active_approved_joins = list_approved_joins()
    except RuntimeError:
        return fail_state(
            "load_approved_join_relationships",
            "approved_join_store_unavailable",
            "Approved join store is unavailable.",
        )
    approved_joins, runtime_map = load_current_approved_joins(schema, all_active_approved_joins)
    dropped_denied, dropped_invalid = _drop_counts(schema, all_active_approved_joins)
    schema = {**schema, "approved_joins": approved_joins}
    return {
        "filtered_sql_schema": schema,
        "approved_join_runtime_map": runtime_map,
        "audit_metadata": {
            **state.get("audit_metadata", {}),
            "approved_join_count": len(approved_joins),
            "total_active_approved_join_count": len(all_active_approved_joins),
            "permission_filtered_join_count": len(approved_joins),
            "dropped_denied_join_count": dropped_denied,
            "dropped_invalid_metadata_join_count": dropped_invalid,
        },
    }


def _drop_counts(schema: dict, joins: list[dict]) -> tuple[int, int]:
    resources = {resource["resource_key"]: resource for resource in schema.get("structured_resources", [])}
    columns = {
        (resource["resource_key"], column["column_name"])
        for resource in resources.values()
        for column in resource.get("columns", [])
    }
    denied = invalid = 0
    for join in joins:
        left_resource = str(join.get("left_resource_key") or "")
        right_resource = str(join.get("right_resource_key") or "")
        left_column = str(join.get("left_column_name") or "")
        right_column = str(join.get("right_column_name") or "")
        if not left_resource or not right_resource or not left_column or not right_column:
            invalid += 1
        elif left_resource not in resources or right_resource not in resources:
            denied += 1
        elif (left_resource, left_column) not in columns or (right_resource, right_column) not in columns:
            invalid += 1
    return denied, invalid
