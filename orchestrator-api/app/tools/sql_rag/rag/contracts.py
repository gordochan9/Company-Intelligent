from __future__ import annotations

from typing import Any


REQUIRED_INPUT_FIELDS = {
    "request_id",
    "step_id",
    "trusted_user_context",
    "user_permission_schema",
}

REQUIRED_RESOURCE_KEYS = {
    "allowed_scopes",
    "allowed_catalog_entry_ids",
    "allowed_rag_namespaces",
}


def require_rag_input(state: dict[str, Any]) -> None:
    missing = [field for field in REQUIRED_INPUT_FIELDS if not state.get(field)]
    if missing:
        raise ValueError("missing_rag_input")
    if not (state.get("rag_question") or state.get("step_goal")):
        raise ValueError("missing_rag_question")
    schema = state.get("user_permission_schema")
    if not isinstance(schema, dict):
        raise ValueError("malformed_permission_schema")
    resources = schema.get("allowed_resources")
    if not isinstance(resources, dict) or not REQUIRED_RESOURCE_KEYS.issubset(resources):
        raise ValueError("malformed_permission_schema")
    if not isinstance(state.get("obligations", []), list):
        raise ValueError("missing_rag_input")


def public_rag_result(
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
        "step_type": "rag",
        "status": status,
        "validated_output": validated_output,
        "limitations": limitations,
        "errors": errors,
        "audit_metadata": audit_metadata,
    }
