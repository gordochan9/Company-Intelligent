from __future__ import annotations

from typing import Any


REQUIRED_INPUT_FIELDS = {
    "request_id",
    "step_id",
    "trusted_user_context",
    "user_permission_schema",
}

REQUIRED_RESOURCE_KEYS = {
    "allowed_structured_resources",
}


def require_sql_input(state: dict[str, Any]) -> None:
    if not state.get("trusted_user_context") or not state.get("user_permission_schema"):
        raise PermissionError("missing_permission_context")
    missing = [field for field in REQUIRED_INPUT_FIELDS if not state.get(field)]
    if missing:
        raise ValueError("missing_sql_input")
    if not (state.get("sql_question") or state.get("step_goal")):
        raise ValueError("missing_sql_question")
    schema = state.get("user_permission_schema")
    if not isinstance(schema, dict):
        raise PermissionError("missing_permission_context")
    resources = schema.get("allowed_resources")
    if not isinstance(resources, dict) or not REQUIRED_RESOURCE_KEYS.issubset(resources):
        raise PermissionError("malformed_permission_context")
    _require_step_contract(state)


def _require_step_contract(state: dict[str, Any]) -> None:
    if not isinstance(state.get("obligations", []), list):
        raise ValueError("missing_sql_input")


def public_sql_result(
    *,
    step_id: str,
    status: str,
    validated_output: dict[str, Any],
    limitations: list[dict[str, Any]],
    errors: list[dict[str, str]],
    audit_metadata: dict[str, Any],
) -> dict[str, Any]:
    return {
        "step_id": step_id,
        "step_type": "sql",
        "status": status,
        "validated_output": validated_output,
        "limitations": limitations,
        "errors": errors,
        "audit_metadata": audit_metadata,
    }
