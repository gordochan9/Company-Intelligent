from __future__ import annotations

import hashlib
from datetime import UTC, datetime, timedelta
from typing import Any

from app.graphs.permission_schema.state import ACCESS_OK, SCHEMA_VERSION


ALLOWED_RESOURCE_KEYS = {
    "allowed_scopes",
    "allowed_source_ids",
    "allowed_catalog_entry_ids",
    "allowed_rag_namespaces",
    "allowed_structured_resources",
    "allowed_join_policy_refs",
}


def build_cache_key(
    trusted_user_context: dict[str, Any],
    *,
    active_dataset_id: str | None,
    source_catalog_version: str | None,
    schema_version: str,
) -> str:
    raw = "|".join(
        [
            str(trusted_user_context["email"]).lower(),
            str(active_dataset_id or ""),
            str(source_catalog_version or ""),
            schema_version,
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_allowed_resource_map(permissions: list[dict[str, Any]]) -> dict[str, Any]:
    resources = {key: [] for key in ALLOWED_RESOURCE_KEYS}
    seen_scopes: set[str] = set()
    for item in permissions:
        scope = item.get("scope")
        if not isinstance(scope, str) or not scope.strip():
            raise ValueError("invalid_permission_scope")
        if scope in seen_scopes:
            continue
        seen_scopes.add(scope)
        resources["allowed_scopes"].append(scope)
        resources["allowed_source_ids"].append(item.get("source_id") or f"scope:{scope}")
        resources["allowed_catalog_entry_ids"].append(item.get("catalog_entry_id") or f"catalog:{scope}")
        resources["allowed_rag_namespaces"].append(item.get("rag_namespace") or scope)
        resources["allowed_structured_resources"].append(item.get("structured_resource") or f"structured:{scope}")
        resources["allowed_join_policy_refs"].append(item.get("join_policy_ref") or f"join:{scope}")
    return resources


def permission_snapshot_hash(allowed_resource_map: dict[str, Any]) -> str:
    raw = repr(sorted((key, tuple(value)) for key, value in allowed_resource_map.items()))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def build_tool_capability_cards(allowed_resource_map: dict[str, Any], limitations: list[dict[str, Any]]) -> list[dict[str, Any]]:
    scopes = set(allowed_resource_map.get("allowed_scopes", []))
    return [
        {
            "tool": "sql_rag",
            "enabled": bool(scopes),
            "can_search_documents": bool(scopes),
            "can_query_structured_data": bool(scopes),
            "limitations": [item.get("code", "limited") for item in limitations],
        }
    ]


def build_user_permission_schema(
    *,
    trusted_user_context: dict[str, Any],
    groups: list[str],
    allowed_resource_map: dict[str, Any],
    active_dataset_id: str | None,
    source_catalog_version: str | None,
    limitations: list[dict[str, Any]],
    errors: list[dict[str, str]],
) -> dict[str, Any]:
    now = datetime.now(UTC)
    user_context = {**trusted_user_context, "groups": list(groups)}
    return {
        "schema_version": SCHEMA_VERSION,
        "access_status": ACCESS_OK,
        "active_dataset_id": active_dataset_id,
        "source_catalog_version": source_catalog_version,
        "trusted_user_context": user_context,
        "allowed_resources": allowed_resource_map,
        "tool_capability_cards": build_tool_capability_cards(allowed_resource_map, limitations),
        "generated_at": now.isoformat(),
        "expires_at": (now + timedelta(seconds=300)).isoformat(),
        "permission_snapshot_hash": permission_snapshot_hash(allowed_resource_map),
        "limitations": limitations,
        "errors": errors,
    }


def validate_permission_schema(schema: dict[str, Any], *, trusted_user_context: dict[str, Any]) -> None:
    required = {
        "schema_version",
        "access_status",
        "trusted_user_context",
        "allowed_resources",
        "tool_capability_cards",
        "permission_snapshot_hash",
    }
    missing = required.difference(schema)
    if missing:
        raise ValueError(f"missing_permission_schema_fields:{','.join(sorted(missing))}")
    if schema["schema_version"] != SCHEMA_VERSION:
        raise ValueError("unsupported_permission_schema_version")
    if schema["access_status"] != ACCESS_OK:
        raise ValueError("invalid_permission_schema_status")
    if schema["trusted_user_context"].get("email") != trusted_user_context.get("email"):
        raise PermissionError("cache_identity_mismatch")
    resources = schema["allowed_resources"]
    if set(resources) != ALLOWED_RESOURCE_KEYS:
        raise ValueError("invalid_allowed_resource_keys")
    for card in schema["tool_capability_cards"]:
        serialized = repr(card).lower()
        for forbidden in ("allowed_source", "allowed_catalog", "raw_acl", "source_id", "table_name"):
            if forbidden in serialized:
                raise ValueError("planner_card_leaks_permission_internals")
