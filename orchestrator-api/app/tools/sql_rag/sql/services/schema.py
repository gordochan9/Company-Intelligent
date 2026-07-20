from __future__ import annotations

import re
from typing import Any


UNSAFE_TEXT_RE = re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/|/mnt/c/Users/|file://|postgres(?:ql)?://|sk-[A-Za-z0-9_-]{8,})", re.IGNORECASE)


def build_filtered_schema(
    *,
    request_id: str,
    step_id: str,
    user_permission_schema: dict[str, Any],
    resources: list[dict[str, Any]],
) -> dict[str, Any]:
    allowed_resources = user_permission_schema["allowed_resources"]
    allowed = set(allowed_resources.get("allowed_structured_resources", []))
    allowed_scopes = set(allowed_resources.get("allowed_scopes", []))
    structured_resources = []
    for resource in resources:
        resource_key = str(resource.get("resource_key") or "")
        if not _resource_is_allowed(resource, allowed, allowed_scopes):
            continue
        table_key = f"table_{len(structured_resources) + 1}"
        columns = []
        for column in resource.get("columns", []):
            columns.append(
                {
                    "column_key": f"{table_key}_col_{len(columns) + 1}",
                    "column_name": str(column.get("column_name") or ""),
                    "data_type": str(column.get("data_type") or "text"),
                    "safe_description": _safe_text(column.get("safe_description")),
                }
            )
        structured_resources.append(
            {
                "table_key": table_key,
                "resource_key": resource_key,
                "runtime_relation_name": str(resource.get("runtime_relation_name") or ""),
                "display_name": _safe_text(resource.get("display_name")),
                "columns": columns,
                "safe_row_samples": [_safe_row(row) for row in resource.get("safe_row_samples", [])],
                "column_profiles": dict(resource.get("column_profiles") or {}),
            }
        )
    return {
        "schema_version": "3.0",
        "request_id": request_id,
        "step_id": step_id,
        "structured_resources": structured_resources,
        "approved_joins": [],
    }


def load_current_approved_joins(filtered_schema: dict[str, Any], joins: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_resource = {resource["resource_key"]: resource for resource in filtered_schema.get("structured_resources", [])}
    column_keys = {
        (resource["resource_key"], column["column_name"]): column["column_key"]
        for resource in filtered_schema.get("structured_resources", [])
        for column in resource.get("columns", [])
    }
    loaded = []
    runtime_map = {}
    for join in joins:
        left_resource = str(join.get("left_resource_key") or "")
        right_resource = str(join.get("right_resource_key") or "")
        left_column = str(join.get("left_column_name") or "")
        right_column = str(join.get("right_column_name") or "")
        if left_resource not in by_resource or right_resource not in by_resource:
            continue
        if (left_resource, left_column) not in column_keys or (right_resource, right_column) not in column_keys:
            continue
        join_key = f"join_{len(loaded) + 1}"
        safe_join = {
            "join_key": join_key,
            "left_table_key": by_resource[left_resource]["table_key"],
            "left_column_key": column_keys[(left_resource, left_column)],
            "right_table_key": by_resource[right_resource]["table_key"],
            "right_column_key": column_keys[(right_resource, right_column)],
            "join_type": join.get("join_type") or "inner",
            "reason": _safe_text(join.get("reason")),
        }
        loaded.append(safe_join)
        runtime_map[join_key] = safe_join
    return loaded, runtime_map


def make_llm_readable_schema(filtered_schema: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": filtered_schema.get("schema_version"),
        "structured_resources": [
            {
                "table_key": resource["table_key"],
                "display_name": resource["display_name"],
                "columns": [
                    {
                        "column_key": column["column_key"],
                        "column_name": column["column_name"],
                        "data_type": column["data_type"],
                        "safe_description": column.get("safe_description", ""),
                    }
                    for column in resource.get("columns", [])
                ],
                "safe_row_samples": resource.get("safe_row_samples", []),
                "column_profiles": resource.get("column_profiles", {}),
            }
            for resource in filtered_schema.get("structured_resources", [])
        ],
        "approved_joins": filtered_schema.get("approved_joins", []),
    }


def _safe_text(value: Any) -> str:
    text = str(value or "")
    return "[REDACTED]" if UNSAFE_TEXT_RE.search(text) else text


def _safe_row(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    return {str(key): _safe_text(value) for key, value in row.items()}


def _resource_is_allowed(resource: dict[str, Any], allowed_resource_keys: set[str], allowed_scopes: set[str]) -> bool:
    resource_key = str(resource.get("resource_key") or "")
    if resource_key in allowed_resource_keys:
        return True
    scope = str(resource.get("permission_scope_key") or "")
    if scope and scope in allowed_scopes:
        return True
    scope_keys = resource.get("scope_keys") or resource.get("permission_scope_keys") or []
    if isinstance(scope_keys, str):
        scope_keys = [scope_keys]
    return any(str(item) in allowed_scopes for item in scope_keys)
