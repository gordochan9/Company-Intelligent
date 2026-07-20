from __future__ import annotations

from app.graphs.permission_schema.state import PermissionSchemaState, SCHEMA_VERSION, STATUS_IN_PROGRESS, fail_closed


def request_intake(state: PermissionSchemaState) -> PermissionSchemaState:
    identity = state.get("openwebui_user_identity")
    if not isinstance(identity, dict):
        return fail_closed("missing_identity", "Authenticated identity is required.")
    if not identity.get("email"):
        return fail_closed("missing_identity_email", "Authenticated identity email is required.")
    return {
        "permission_schema_status": STATUS_IN_PROGRESS,
        "access_status": STATUS_IN_PROGRESS,
        "requested_openwebui_identity": {
            "email": identity.get("email"),
            "user_id": identity.get("user_id"),
            "display_name": identity.get("display_name"),
            "auth_source": identity.get("auth_source"),
        },
        "permission_schema_version": state.get("permission_schema_version") or SCHEMA_VERSION,
        "permission_limitations": [],
        "permission_errors": [],
        "tool_capability_cards": [],
        "trace": list(state.get("trace", [])),
        "debug": {},
    }
