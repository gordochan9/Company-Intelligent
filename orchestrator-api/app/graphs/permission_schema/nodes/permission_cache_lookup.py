from __future__ import annotations

from app.graphs.permission_schema.state import PermissionSchemaState, fail_closed, should_continue
from app.services.permissions.cache import get_cached_permission_schema
from app.services.permissions.schema_builder import build_cache_key


def permission_cache_lookup(state: PermissionSchemaState) -> PermissionSchemaState:
    if not should_continue(state):
        return {}
    trusted = state.get("trusted_user_context")
    if not trusted:
        return fail_closed("missing_trusted_identity", "Trusted identity is required before cache lookup.")
    cache_key = build_cache_key(
        trusted,
        active_dataset_id=state.get("active_dataset_id"),
        source_catalog_version=state.get("source_catalog_version"),
        schema_version=state["permission_schema_version"],
    )
    entry = get_cached_permission_schema(cache_key)
    return {
        "cache_key": cache_key,
        "cached_permission_schema": entry.schema if entry else None,
        "cache_validation_result": {"status": "found", "expires_at": entry.expires_at.isoformat()} if entry else {"status": "miss"},
    }
