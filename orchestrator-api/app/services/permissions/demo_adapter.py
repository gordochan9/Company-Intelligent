from __future__ import annotations

from copy import deepcopy
from typing import Any


IDENTITIES: dict[str, dict[str, Any]] = {
    "admin@demo.com": {
        "user_id": "project3-demo-admin",
        "email": "admin@demo.com",
        "display_name": "Project 3.0 Demo Admin",
        "auth_source": "openwebui",
        "groups": ["operations_admin"],
        "scopes": ["employee_guidelines", "file_server", "finance", "hr"],
    },
    "user@demo.com": {
        "user_id": "project3-demo-user",
        "email": "user@demo.com",
        "display_name": "Project 3.0 Demo User",
        "auth_source": "openwebui",
        "groups": ["standard_employee"],
        "scopes": ["employee_guidelines", "file_server"],
    },
}


def confirm_identity(identity: dict[str, Any]) -> dict[str, Any]:
    email = str(identity.get("email", "")).strip().lower()
    if not email:
        raise ValueError("missing_email")
    record = IDENTITIES.get(email)
    if not record:
        raise PermissionError("identity_not_confirmed")
    if identity.get("auth_source") not in {None, "openwebui"}:
        raise PermissionError("invalid_auth_source")
    return {
        "user_id": record["user_id"],
        "email": record["email"],
        "display_name": record["display_name"],
        "identity_source": "openwebui",
    }


def resolve_groups(trusted_user_context: dict[str, Any]) -> list[str]:
    record = IDENTITIES.get(str(trusted_user_context.get("email", "")).lower())
    if not record:
        raise PermissionError("groups_not_found")
    return list(record["groups"])


def resolve_source_permissions(trusted_user_context: dict[str, Any], groups: list[str]) -> list[dict[str, Any]]:
    record = IDENTITIES.get(str(trusted_user_context.get("email", "")).lower())
    if not record:
        raise PermissionError("permissions_not_found")
    if not groups:
        return []
    return [
        {
            "scope": scope,
            "source_id": f"scope:{scope}",
            "catalog_entry_id": f"catalog:{scope}",
            "rag_namespace": scope,
            "structured_resource": f"structured:{scope}",
            "join_policy_ref": f"join:{scope}",
        }
        for scope in deepcopy(record["scopes"])
    ]
