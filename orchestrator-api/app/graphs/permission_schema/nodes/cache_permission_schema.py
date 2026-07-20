from __future__ import annotations

from app.graphs.permission_schema.state import ACCESS_OK, PermissionSchemaState
from app.services.permissions.cache import store_permission_schema


def cache_permission_schema(state: PermissionSchemaState) -> PermissionSchemaState:
    if state.get("access_status") != ACCESS_OK:
        return {}
    cache_key = state.get("cache_key")
    schema = state.get("user_permission_schema")
    if cache_key and schema:
        store_permission_schema(cache_key, schema)
    return {}
