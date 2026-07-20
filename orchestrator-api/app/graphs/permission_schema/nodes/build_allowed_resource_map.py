from __future__ import annotations

from app.graphs.permission_schema.state import PermissionSchemaState, fail_closed, should_continue
from app.services.permissions.schema_builder import build_allowed_resource_map as build_resources


def build_allowed_resource_map(state: PermissionSchemaState) -> PermissionSchemaState:
    if not should_continue(state):
        return {}
    try:
        allowed_resource_map = build_resources(state.get("raw_share_drive_permissions", []))
    except Exception:
        return fail_closed("invalid_source_metadata", "Allowed source metadata is invalid.", trusted_user_context=state.get("trusted_user_context"))
    if not allowed_resource_map["allowed_scopes"]:
        return fail_closed("no_allowed_sources", "No allowed sources are available for this identity.", access_status="denied", trusted_user_context=state.get("trusted_user_context"))
    return {"allowed_resource_map": allowed_resource_map}
