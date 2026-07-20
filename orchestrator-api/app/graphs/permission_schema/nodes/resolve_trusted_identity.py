from __future__ import annotations

from app.graphs.permission_schema.state import PermissionSchemaState, fail_closed, should_continue
from app.services.permissions import demo_adapter


def resolve_trusted_identity(state: PermissionSchemaState) -> PermissionSchemaState:
    if not should_continue(state):
        return {}
    try:
        trusted = demo_adapter.confirm_identity(state["requested_openwebui_identity"])
    except Exception:
        return fail_closed("identity_not_confirmed", "Authenticated identity could not be confirmed.")
    return {"trusted_user_context": trusted}
