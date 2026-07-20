from __future__ import annotations

from typing import Any

from app.db.runtime_store import PostgresRuntimeStore


_resources: list[dict[str, Any]] | None = None
_joins: list[dict[str, Any]] | None = None


def set_structured_resources(resources: list[dict[str, Any]]) -> None:
    global _resources
    _resources = [dict(resource) for resource in resources]


def set_approved_joins(joins: list[dict[str, Any]]) -> None:
    global _joins
    _joins = [dict(join) for join in joins]


def list_structured_resources() -> list[dict[str, Any]]:
    if _resources is None:
        return PostgresRuntimeStore().list_structured_resources()
    return [dict(resource) for resource in _resources]


def list_approved_joins() -> list[dict[str, Any]]:
    if _joins is None:
        return PostgresRuntimeStore().list_approved_joins()
    return [dict(join) for join in _joins]
