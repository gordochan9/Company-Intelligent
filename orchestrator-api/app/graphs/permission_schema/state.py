from __future__ import annotations

from typing import Any, TypedDict


SCHEMA_VERSION = "3.0"
ACCESS_OK = "ok"
ACCESS_DENIED = "denied"
ACCESS_FAILED = "access_failed"
ACCESS_SCHEMA_FAILED = "permission_schema_failed"
STATUS_IN_PROGRESS = "in_progress"


class PermissionSchemaState(TypedDict, total=False):
    request_id: str
    trace_id: str
    openwebui_user_identity: dict[str, Any]
    active_dataset_id: str | None
    source_catalog_version: str | None
    permission_schema_version: str
    requested_openwebui_identity: dict[str, Any]
    permission_schema_status: str
    access_status: str
    trusted_user_context: dict[str, Any] | None
    cache_key: str | None
    cached_permission_schema: dict[str, Any] | None
    cache_validation_result: dict[str, Any] | None
    resolved_groups: list[str]
    raw_share_drive_permissions: list[dict[str, Any]]
    allowed_resource_map: dict[str, Any] | None
    user_permission_schema: dict[str, Any] | None
    tool_capability_cards: list[dict[str, Any]]
    permission_limitations: list[dict[str, Any]]
    permission_errors: list[dict[str, str]]
    trace: list[dict[str, Any]]
    debug: dict[str, Any]


def safe_error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def fail_closed(
    code: str,
    message: str,
    *,
    access_status: str = ACCESS_FAILED,
    trusted_user_context: dict[str, Any] | None = None,
) -> PermissionSchemaState:
    return {
        "permission_schema_status": "failed",
        "access_status": access_status,
        "trusted_user_context": trusted_user_context,
        "user_permission_schema": None,
        "tool_capability_cards": [],
        "permission_limitations": [],
        "permission_errors": [safe_error(code, message)],
    }


def should_continue(state: PermissionSchemaState) -> bool:
    return state.get("access_status", STATUS_IN_PROGRESS) == STATUS_IN_PROGRESS
