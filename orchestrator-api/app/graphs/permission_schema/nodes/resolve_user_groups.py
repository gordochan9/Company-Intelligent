from __future__ import annotations

from app.graphs.permission_schema.state import PermissionSchemaState, fail_closed, should_continue
from app.services.permissions import demo_adapter


def resolve_user_groups(state: PermissionSchemaState) -> PermissionSchemaState:
    if not should_continue(state):
        return {}
    try:
        groups = demo_adapter.resolve_groups(state["trusted_user_context"])
    except Exception:
        return fail_closed("group_resolution_failed", "User groups could not be resolved.", trusted_user_context=state.get("trusted_user_context"))
    return {"resolved_groups": groups}
