from __future__ import annotations

from app.graphs.permission_schema.state import ACCESS_DENIED, PermissionSchemaState, fail_closed, should_continue
from app.services.permissions import demo_adapter


def resolve_share_drive_permissions(state: PermissionSchemaState) -> PermissionSchemaState:
    if not should_continue(state):
        return {}
    try:
        permissions = demo_adapter.resolve_source_permissions(
            state["trusted_user_context"],
            state.get("resolved_groups", []),
        )
    except Exception:
        return fail_closed("permission_resolution_failed", "Source permissions could not be resolved.", trusted_user_context=state.get("trusted_user_context"))
    if not permissions:
        return fail_closed(
            "no_allowed_sources",
            "No allowed sources are available for this identity.",
            access_status=ACCESS_DENIED,
            trusted_user_context=state.get("trusted_user_context"),
        )
    return {"raw_share_drive_permissions": permissions}
