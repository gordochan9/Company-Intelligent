from __future__ import annotations

from app.graphs.permission_schema.state import PermissionSchemaState, fail_closed, should_continue
from app.services.permissions.schema_builder import validate_permission_schema as validate_schema


def validate_permission_schema(state: PermissionSchemaState) -> PermissionSchemaState:
    if not should_continue(state):
        return {}
    try:
        validate_schema(state["user_permission_schema"], trusted_user_context=state["trusted_user_context"])
    except Exception:
        return fail_closed("permission_schema_validation_failed", "Permission schema validation failed.", access_status="permission_schema_failed", trusted_user_context=state.get("trusted_user_context"))
    return {"access_status": "ok"}
