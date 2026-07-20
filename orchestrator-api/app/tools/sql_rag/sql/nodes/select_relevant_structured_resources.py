from __future__ import annotations

from time import perf_counter
from typing import Any

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus, AuditFailure
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.sql.services.llm import (
    SqlModelUnavailable,
    call_selector_model,
    parse_resource_selection,
    resource_selection_output_schema,
)
from app.tools.sql_rag.sql.state import STATUS_INSUFFICIENT, STATUS_VALIDATION_FAILED, SqlState, fail_state


_MAX_RESTRICTED_KEYS = 100
_MAX_RESTRICTED_KEY_LENGTH = 128

_SELECTOR_SYSTEM_PROMPT = """Return JSON only.
Select the permission-filtered structured resources needed to satisfy the complete semantic SQL intent.
Return exactly table_keys, column_keys, and join_keys arrays matching output_schema, with no extra fields.
Use only logical keys present in filtered_sql_schema.
Select every table and column needed for requested outputs, metrics, filters, grouping, ranking, and relationships.
For each derived metric, include every value, quantity, rate, adjustment, and eligibility input whose schema meaning can change the result, even when the user did not name its storage field.
When identifying, grouping, or ranking an entity, include available human-readable label or name columns and the relationship identifiers needed to connect them; an opaque identifier alone is not a complete requested output.
Approved join keys are optional verified hints, not an authoritative join plan.
Return join_keys as an empty array when no approved join is helpful; multiple helpful approved joins may be returned.
Do not output SQL, join-required status, join conditions, arbitrary relationship objects, reasons, or confidence.
"""


def select_relevant_structured_resources(state: SqlState) -> SqlState:
    started = perf_counter()
    intent = state.get("sql_query_intent") or {}
    readable_schema = state.get("llm_readable_sql_schema") or {}
    model_started = perf_counter()
    try:
        raw_selection = call_selector_model(_selector_payload(intent, readable_schema))
    except SqlModelUnavailable:
        duration_ms = _duration_ms(started)
        model_duration_ms = _duration_ms(model_started)
        metadata = _failed_model_metadata(
            "selector_model_unavailable", "unavailable", "not_started", model_duration_ms
        )
        _emit_selection_event(
            state,
            metadata,
            _empty_restricted_metadata(),
            status=AuditEventStatus.FAILED,
            duration_ms=duration_ms,
            failure_code="sql_selector_model_unavailable",
            failure_reason="SQL resource selector model is unavailable.",
        )
        return fail_state(
            "select_relevant_structured_resources",
            "sql_selector_model_unavailable",
            "SQL resource selector model is unavailable.",
        )
    model_duration_ms = _duration_ms(model_started)
    try:
        selection = parse_resource_selection(raw_selection)
    except (TypeError, ValueError):
        duration_ms = _duration_ms(started)
        metadata = _failed_model_metadata("selector_output_invalid", "succeeded", "invalid", model_duration_ms)
        _emit_selection_event(
            state,
            metadata,
            _empty_restricted_metadata(),
            status=AuditEventStatus.VALIDATION_FAILED,
            duration_ms=duration_ms,
            failure_code="invalid_structured_resource_selection",
            failure_reason="SQL resource selector output is invalid.",
        )
        return fail_state(
            "select_relevant_structured_resources",
            "invalid_structured_resource_selection",
            "SQL resource selector output is invalid.",
            status=STATUS_VALIDATION_FAILED,
        )

    resolved = _resolve_selection(selection, state.get("filtered_sql_schema") or {})
    duration_ms = _duration_ms(started)
    if not resolved["source_columns"]:
        reason = "no_matching_table_and_column_keys" if not resolved["explicit_table_keys"] else "no_matching_column_keys"
        metadata, restricted_metadata = _evaluation_metadata(
            selection, resolved, reason, model_duration_ms=model_duration_ms, selected=False
        )
        _emit_selection_event(
            state,
            metadata,
            restricted_metadata,
            status=AuditEventStatus.INSUFFICIENT_EVIDENCE,
            duration_ms=duration_ms,
            failure_code="no_relevant_structured_resources",
            failure_reason="No permitted structured resources matched the SQL selector output.",
        )
        return fail_state(
            "select_relevant_structured_resources",
            "no_relevant_structured_resources",
            "No permitted structured resources matched the SQL selector output.",
            status=STATUS_INSUFFICIENT,
        )

    metadata, restricted_metadata = _evaluation_metadata(
        selection, resolved, "valid_subset_selected", model_duration_ms=model_duration_ms, selected=True
    )
    _emit_selection_event(
        state,
        metadata,
        restricted_metadata,
        status=AuditEventStatus.SUCCEEDED,
        duration_ms=duration_ms,
    )
    return {
        "selected_resources": {
            "tables": resolved["tables"],
            "columns": resolved["columns"],
            "source_columns": resolved["source_columns"],
            "joins": resolved["joins"],
        },
        "audit_metadata": {
            **state.get("audit_metadata", {}),
            "selected_table_count": len(resolved["tables"]),
            "selected_column_count": len(resolved["columns"]),
        },
    }


def _selector_payload(intent: dict[str, Any], filtered_schema: dict[str, Any]) -> dict[str, Any]:
    output_schema = resource_selection_output_schema()
    available_keys = {
        "table_keys": [item.get("table_key") for item in filtered_schema.get("structured_resources", [])],
        "column_keys": [
            column.get("column_key")
            for item in filtered_schema.get("structured_resources", [])
            for column in item.get("columns", [])
        ],
        "join_keys": [item.get("join_key") for item in filtered_schema.get("approved_joins", [])],
    }
    for field, keys in available_keys.items():
        output_schema["properties"][field]["items"]["enum"] = [key for key in keys if isinstance(key, str)]
    return {
        "system_prompt": _SELECTOR_SYSTEM_PROMPT,
        "payload": {
            "sql_query_intent": intent,
            "filtered_sql_schema": filtered_schema,
            "output_schema": output_schema,
        },
    }


def _resolve_selection(selection: dict[str, list[str]], schema: dict[str, Any]) -> dict[str, Any]:
    resources = [item for item in schema.get("structured_resources", []) if isinstance(item, dict)]
    joins = [item for item in schema.get("approved_joins", []) if isinstance(item, dict)]
    table_keys, duplicate_table_count = _ordered_unique(selection["table_keys"])
    column_keys, duplicate_column_count = _ordered_unique(selection["column_keys"])
    join_keys, duplicate_join_count = _ordered_unique(selection["join_keys"])
    proposed_table_set = set(table_keys)
    proposed_column_set = set(column_keys)
    proposed_join_set = set(join_keys)

    available_table_keys = {item.get("table_key") for item in resources if isinstance(item.get("table_key"), str)}
    column_owner = {
        column.get("column_key"): item.get("table_key")
        for item in resources
        for column in item.get("columns", [])
        if isinstance(column, dict)
        and isinstance(column.get("column_key"), str)
        and isinstance(item.get("table_key"), str)
    }
    available_column_keys = set(column_owner)
    available_join_keys = {item.get("join_key") for item in joins if isinstance(item.get("join_key"), str)}

    explicit_table_keys = proposed_table_set & available_table_keys
    source_column_keys = proposed_column_set & available_column_keys
    owner_table_keys = {column_owner[key] for key in source_column_keys}
    canonical_table_keys = explicit_table_keys | owner_table_keys
    owner_added_table_keys = owner_table_keys - explicit_table_keys

    matched_joins = []
    incomplete_join_keys = set()
    outside_join_keys = set()
    join_endpoint_column_keys = set()
    for join in joins:
        join_key = join.get("join_key")
        if join_key not in proposed_join_set:
            continue
        left_table = join.get("left_table_key")
        right_table = join.get("right_table_key")
        left_column = join.get("left_column_key")
        right_column = join.get("right_column_key")
        if not all(isinstance(value, str) and value for value in (left_table, right_table, left_column, right_column)):
            incomplete_join_keys.add(join_key)
            continue
        if column_owner.get(left_column) != left_table or column_owner.get(right_column) != right_table:
            incomplete_join_keys.add(join_key)
            continue
        if not {left_table, right_table} <= canonical_table_keys:
            outside_join_keys.add(join_key)
            continue
        matched_joins.append(join)
        join_endpoint_column_keys.update((left_column, right_column))

    execution_column_keys = source_column_keys | join_endpoint_column_keys
    selected_tables = []
    selected_columns = []
    source_columns = []
    for resource in resources:
        table_key = resource.get("table_key")
        if table_key not in canonical_table_keys:
            continue
        table_columns = [
            {**column, "table_key": table_key, "resource_key": resource.get("resource_key")}
            for column in resource.get("columns", [])
            if isinstance(column, dict)
        ]
        selected_tables.append(
            {
                "table_key": table_key,
                "resource_key": resource.get("resource_key"),
                "runtime_relation_name": resource.get("runtime_relation_name"),
                "display_name": resource.get("display_name"),
                "columns": table_columns,
            }
        )
        selected_columns.extend(column for column in table_columns if column.get("column_key") in execution_column_keys)
        source_columns.extend(column for column in table_columns if column.get("column_key") in source_column_keys)

    return {
        "tables": selected_tables,
        "columns": selected_columns,
        "source_columns": source_columns,
        "joins": matched_joins,
        "table_keys": table_keys,
        "column_keys": column_keys,
        "join_keys": join_keys,
        "available_table_keys": available_table_keys,
        "available_column_keys": available_column_keys,
        "available_join_keys": available_join_keys,
        "explicit_table_keys": explicit_table_keys,
        "source_column_keys": source_column_keys,
        "canonical_table_keys": canonical_table_keys,
        "owner_added_table_keys": owner_added_table_keys,
        "matched_join_keys": {item["join_key"] for item in matched_joins},
        "incomplete_join_keys": incomplete_join_keys,
        "outside_join_keys": outside_join_keys,
        "duplicate_table_count": duplicate_table_count,
        "duplicate_column_count": duplicate_column_count,
        "duplicate_join_count": duplicate_join_count,
    }


def _evaluation_metadata(
    selection: dict[str, list[str]],
    resolved: dict[str, Any],
    reason: str,
    *,
    model_duration_ms: int,
    selected: bool,
) -> tuple[dict[str, Any], dict[str, Any]]:
    unmatched_tables = set(resolved["table_keys"]) - resolved["available_table_keys"]
    unmatched_columns = set(resolved["column_keys"]) - resolved["available_column_keys"]
    unknown_joins = set(resolved["join_keys"]) - resolved["available_join_keys"]
    metadata = {
        "selector_model_status": "succeeded",
        "selector_model_duration_ms": model_duration_ms,
        "selector_parse_status": "succeeded",
        "selector_output_schema_valid": True,
        "selection_status": "selected" if selected else "failed",
        "selection_gate": "selected" if selected else "catalog_resolution",
        "selection_reason_code": reason,
        "available_table_count": len(resolved["available_table_keys"]),
        "available_column_count": len(resolved["available_column_keys"]),
        "available_join_count": len(resolved["available_join_keys"]),
        "proposed_table_item_count": len(selection["table_keys"]),
        "proposed_column_item_count": len(selection["column_keys"]),
        "proposed_join_item_count": len(selection["join_keys"]),
        "shape_valid_unique_table_key_count": len(resolved["table_keys"]),
        "shape_valid_unique_column_key_count": len(resolved["column_keys"]),
        "shape_valid_unique_join_key_count": len(resolved["join_keys"]),
        "duplicate_table_key_count": resolved["duplicate_table_count"],
        "duplicate_column_key_count": resolved["duplicate_column_count"],
        "duplicate_join_key_count": resolved["duplicate_join_count"],
        "matched_table_key_count": len(resolved["explicit_table_keys"]),
        "explicit_matched_table_key_count": len(resolved["explicit_table_keys"]),
        "owner_table_added_count": len(resolved["owner_added_table_keys"]),
        "unmatched_table_key_count": len(unmatched_tables),
        "matched_column_in_selected_tables_count": len(resolved["source_column_keys"]),
        "unknown_column_key_count": len(unmatched_columns),
        "unmatched_column_key_count": len(unmatched_columns),
        "matched_join_hint_count": len(resolved["matched_join_keys"]),
        "ignored_unknown_join_hint_count": len(unknown_joins),
        "ignored_incomplete_join_hint_count": len(resolved["incomplete_join_keys"]),
        "ignored_outside_selected_tables_join_hint_count": len(resolved["outside_join_keys"]),
        "selected_table_count": len(resolved["tables"]),
        "selected_column_count": len(resolved["columns"]),
        "source_column_count": len(resolved["source_columns"]),
        "approved_join_count": len(resolved["joins"]),
    }
    restricted, truncated = _bounded_restricted_metadata(
        {
            "proposed_table_keys": resolved["table_keys"],
            "matched_table_keys": _catalog_explicit_table_keys(resolved),
            "owner_added_table_keys": _catalog_owner_table_keys(resolved),
            "unmatched_table_keys": [key for key in resolved["table_keys"] if key in unmatched_tables],
            "proposed_column_keys": resolved["column_keys"],
            "matched_column_in_selected_tables_keys": _catalog_column_keys(resolved),
            "unknown_column_keys": [key for key in resolved["column_keys"] if key in unmatched_columns],
            "proposed_join_keys": resolved["join_keys"],
            "matched_join_keys": [item["join_key"] for item in resolved["joins"]],
            "ignored_unknown_join_keys": [key for key in resolved["join_keys"] if key in unknown_joins],
            "ignored_incomplete_join_keys": [key for key in resolved["join_keys"] if key in resolved["incomplete_join_keys"]],
            "ignored_outside_selected_tables_join_keys": [
                key for key in resolved["join_keys"] if key in resolved["outside_join_keys"]
            ],
        }
    )
    metadata["restricted_key_lists_truncated"] = truncated
    return metadata, restricted


def _catalog_table_keys(resolved: dict[str, Any]) -> list[str]:
    return [item["table_key"] for item in resolved["tables"]]


def _catalog_explicit_table_keys(resolved: dict[str, Any]) -> list[str]:
    return [key for key in _catalog_table_keys(resolved) if key in resolved["explicit_table_keys"]]


def _catalog_owner_table_keys(resolved: dict[str, Any]) -> list[str]:
    return [key for key in _catalog_table_keys(resolved) if key in resolved["owner_added_table_keys"]]


def _catalog_column_keys(resolved: dict[str, Any]) -> list[str]:
    return [item["column_key"] for item in resolved["source_columns"]]


def _ordered_unique(keys: list[str]) -> tuple[list[str], int]:
    ordered = []
    seen = set()
    duplicates = 0
    for key in keys:
        if key in seen:
            duplicates += 1
            continue
        seen.add(key)
        ordered.append(key)
    return ordered, duplicates


def _failed_model_metadata(reason: str, model_status: str, parse_status: str, model_duration_ms: int) -> dict[str, Any]:
    return {
        "selector_model_status": model_status,
        "selector_model_duration_ms": model_duration_ms,
        "selector_parse_status": parse_status,
        "selector_output_schema_valid": False,
        "selection_status": "failed",
        "selection_gate": "selector_model",
        "selection_reason_code": reason,
        "proposed_table_item_count": 0,
        "proposed_column_item_count": 0,
        "proposed_join_item_count": 0,
        "shape_valid_unique_table_key_count": 0,
        "shape_valid_unique_column_key_count": 0,
        "shape_valid_unique_join_key_count": 0,
        "duplicate_table_key_count": 0,
        "duplicate_column_key_count": 0,
        "duplicate_join_key_count": 0,
        "matched_table_key_count": 0,
        "explicit_matched_table_key_count": 0,
        "owner_table_added_count": 0,
        "unmatched_table_key_count": 0,
        "matched_column_in_selected_tables_count": 0,
        "unknown_column_key_count": 0,
        "unmatched_column_key_count": 0,
        "matched_join_hint_count": 0,
        "ignored_unknown_join_hint_count": 0,
        "ignored_incomplete_join_hint_count": 0,
        "ignored_outside_selected_tables_join_hint_count": 0,
        "selected_table_count": 0,
        "selected_column_count": 0,
        "source_column_count": 0,
        "approved_join_count": 0,
        "restricted_key_lists_truncated": False,
    }


def _empty_restricted_metadata() -> dict[str, list[str]]:
    return {
        "proposed_table_keys": [],
        "matched_table_keys": [],
        "owner_added_table_keys": [],
        "unmatched_table_keys": [],
        "proposed_column_keys": [],
        "matched_column_in_selected_tables_keys": [],
        "unknown_column_keys": [],
        "proposed_join_keys": [],
        "matched_join_keys": [],
        "ignored_unknown_join_keys": [],
        "ignored_incomplete_join_keys": [],
        "ignored_outside_selected_tables_join_keys": [],
    }


def _bounded_restricted_metadata(values: dict[str, list[str]]) -> tuple[dict[str, list[str]], bool]:
    restricted = {}
    truncated = False
    for field, keys in values.items():
        restricted[field], field_truncated = _bounded_keys(keys)
        truncated = truncated or field_truncated
    return restricted, truncated


def _bounded_keys(keys: list[str]) -> tuple[list[str], bool]:
    truncated = len(keys) > _MAX_RESTRICTED_KEYS
    bounded = []
    for key in keys[:_MAX_RESTRICTED_KEYS]:
        if len(key) > _MAX_RESTRICTED_KEY_LENGTH:
            truncated = True
        bounded.append(key[:_MAX_RESTRICTED_KEY_LENGTH])
    return bounded, truncated


def _emit_selection_event(
    state: SqlState,
    metadata: dict[str, Any],
    restricted_metadata: dict[str, Any],
    *,
    status: AuditEventStatus,
    duration_ms: int,
    failure_code: str | None = None,
    failure_reason: str | None = None,
) -> None:
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="structured_resource_selection_evaluated",
        status=status,
        workflow_name="sql_subgraph",
        node_name="select_relevant_structured_resources",
        failure=AuditFailure(
            failed_workflow="sql_subgraph",
            failed_node="select_relevant_structured_resources",
            failure_code=failure_code,
            failure_reason=failure_reason or "SQL resource selection failed.",
        )
        if failure_code
        else None,
        duration_ms=duration_ms,
        metadata=metadata,
        restricted_metadata=restricted_metadata,
        include_trace_entry=False,
    )


def _duration_ms(started: float) -> int:
    return max(0, round((perf_counter() - started) * 1000))
