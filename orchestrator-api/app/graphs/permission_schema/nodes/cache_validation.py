from __future__ import annotations

from datetime import UTC, datetime

from app.graphs.permission_schema.state import PermissionSchemaState, fail_closed, should_continue
from app.services.permissions.schema_builder import validate_permission_schema


def cache_validation(state: PermissionSchemaState) -> PermissionSchemaState:
    if not should_continue(state):
        return {}
    schema = state.get("cached_permission_schema")
    if not schema:
        return {"cache_validation_result": {"status": "miss"}}
    result = state.get("cache_validation_result") or {}
    expires_at = result.get("expires_at")
    if not isinstance(expires_at, str):
        return fail_closed("corrupted_cache", "Cached permission schema is invalid.", access_status="permission_schema_failed")
    if datetime.fromisoformat(expires_at) <= datetime.now(UTC):
        return {"cached_permission_schema": None, "cache_validation_result": {"status": "expired"}}
    try:
        validate_permission_schema(schema, trusted_user_context=state["trusted_user_context"])
    except PermissionError:
        return fail_closed("wrong_identity_cache", "Cached permission schema identity mismatch.", access_status="permission_schema_failed")
    except Exception:
        return fail_closed("corrupted_cache", "Cached permission schema is invalid.", access_status="permission_schema_failed")
    return {
        "access_status": schema["access_status"],
        "user_permission_schema": schema,
        "tool_capability_cards": schema["tool_capability_cards"],
        "permission_limitations": schema["limitations"],
        "permission_errors": schema["errors"],
        "cache_validation_result": {"status": "valid"},
    }
