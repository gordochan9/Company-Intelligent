from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, StrictStr, field_validator


_IntentModel = Callable[[dict[str, Any]], dict[str, Any] | str]
_SelectorModel = Callable[[dict[str, Any]], dict[str, Any] | str]
_SqlModel = Callable[[dict[str, Any]], dict[str, Any] | str]
_intent_model: _IntentModel | None = None
_selector_model: _SelectorModel | None = None
_sql_model: _SqlModel | None = None


class SqlModelUnavailable(RuntimeError):
    pass


class SqlResourceSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    table_keys: list[StrictStr]
    column_keys: list[StrictStr]
    join_keys: list[StrictStr]

    @field_validator("table_keys", "column_keys", "join_keys")
    @classmethod
    def keys_are_non_empty(cls, value: list[str]) -> list[str]:
        if any(not item for item in value):
            raise ValueError("resource_selection_key_empty")
        return value


def set_sql_intent_model(model: _IntentModel | None) -> None:
    global _intent_model
    _intent_model = model


def set_sql_selector_model(model: _SelectorModel | None) -> None:
    global _selector_model
    _selector_model = model


def set_sql_generation_model(model: _SqlModel | None) -> None:
    global _sql_model
    _sql_model = model


def call_intent_model(payload: dict[str, Any]) -> dict[str, Any] | str:
    if _intent_model is None:
        raise SqlModelUnavailable("No SQL intent model is configured.")
    try:
        return _intent_model(payload)
    except Exception as exc:
        raise SqlModelUnavailable("SQL intent model call failed.") from exc


def call_selector_model(payload: dict[str, Any]) -> dict[str, Any] | str:
    if _selector_model is None:
        raise SqlModelUnavailable("No SQL selector model is configured.")
    try:
        return _selector_model(payload)
    except Exception as exc:
        raise SqlModelUnavailable("SQL selector model call failed.") from exc


def call_sql_model(payload: dict[str, Any]) -> dict[str, Any] | str:
    if _sql_model is None:
        raise SqlModelUnavailable("No SQL generation model is configured.")
    try:
        return _sql_model(payload)
    except Exception as exc:
        raise SqlModelUnavailable("SQL generation model call failed.") from exc


def parse_intent(raw_intent: dict[str, Any] | str | None) -> dict[str, Any]:
    try:
        intent = json.loads(raw_intent) if isinstance(raw_intent, str) else raw_intent
    except json.JSONDecodeError as exc:
        raise ValueError("intent_unreadable") from exc
    if not isinstance(intent, dict) or not _has_semantic_content(intent):
        raise ValueError("intent_unreadable")
    return dict(intent)


def parse_resource_selection(raw_selection: dict[str, Any] | str | None) -> dict[str, list[str]]:
    try:
        selection = json.loads(raw_selection) if isinstance(raw_selection, str) else raw_selection
    except json.JSONDecodeError as exc:
        raise ValueError("resource_selection_unreadable") from exc
    return SqlResourceSelection.model_validate(selection).model_dump()


def resource_selection_output_schema() -> dict[str, Any]:
    return SqlResourceSelection.model_json_schema()


def parse_candidate(raw_candidate: dict[str, Any] | str | None) -> str:
    try:
        candidate = json.loads(raw_candidate) if isinstance(raw_candidate, str) else raw_candidate
    except json.JSONDecodeError as exc:
        raise ValueError("unreadable_candidate_query") from exc
    if not isinstance(candidate, dict) or not isinstance(candidate.get("sql"), str):
        raise ValueError("invalid_candidate_query")
    return candidate["sql"]


def _has_semantic_content(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, dict):
        return any(_has_semantic_content(item) for item in value.values())
    if isinstance(value, list):
        return any(_has_semantic_content(item) for item in value)
    return isinstance(value, (bool, int, float))
