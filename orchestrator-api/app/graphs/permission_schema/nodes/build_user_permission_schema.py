from __future__ import annotations

from app.graphs.permission_schema.state import PermissionSchemaState, fail_closed, should_continue
from app.services.permissions.schema_builder import build_user_permission_schema as build_schema


def build_user_permission_schema(state: PermissionSchemaState) -> PermissionSchemaState:
    if not should_continue(state):
        return {}
    try:
        schema = build_schema(
            trusted_user_context=state["trusted_user_context"],
            groups=state.get("resolved_groups", []),
            allowed_resource_map=state["allowed_resource_map"],
            active_dataset_id=state.get("active_dataset_id"),
            source_catalog_version=state.get("source_catalog_version"),
            limitations=state.get("permission_limitations", []),
            errors=state.get("permission_errors", []),
        )
    except Exception:
        return fail_closed("permission_schema_build_failed", "Permission schema could not be built.", trusted_user_context=state.get("trusted_user_context"))
    return {"user_permission_schema": schema, "tool_capability_cards": schema["tool_capability_cards"]}
