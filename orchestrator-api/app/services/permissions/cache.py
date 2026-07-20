from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass
class PermissionCacheEntry:
    schema: dict[str, Any]
    expires_at: datetime


_CACHE: dict[str, PermissionCacheEntry] = {}


def get_cached_permission_schema(cache_key: str) -> PermissionCacheEntry | None:
    entry = _CACHE.get(cache_key)
    if not entry:
        return None
    return PermissionCacheEntry(schema=deepcopy(entry.schema), expires_at=entry.expires_at)


def store_permission_schema(cache_key: str, schema: dict[str, Any], *, ttl_seconds: int = 300) -> None:
    _CACHE[cache_key] = PermissionCacheEntry(
        schema=deepcopy(schema),
        expires_at=datetime.now(UTC) + timedelta(seconds=ttl_seconds),
    )


def clear_permission_schema_cache() -> None:
    _CACHE.clear()


def force_cache_entry(cache_key: str, schema: dict[str, Any], expires_at: datetime) -> None:
    _CACHE[cache_key] = PermissionCacheEntry(schema=deepcopy(schema), expires_at=expires_at)
