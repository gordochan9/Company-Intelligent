from __future__ import annotations

import pytest

from app.tools.sql_rag.sql.contracts import public_sql_result, require_sql_input
from app.tools.sql_rag.sql.services.llm import parse_intent
from app.tools.sql_rag.sql.state import ALLOWED_SQL_STATUSES, empty_validated_output


def test_sql_input_contract_requires_step_and_permission_context() -> None:
    require_sql_input(
        {
            "request_id": "req",
            "step_id": "step",
            "sql_question": "question",
            "trusted_user_context": {"email": "user@example.test"},
            "user_permission_schema": {"allowed_resources": {"allowed_structured_resources": []}},
        }
    )


def test_sql_public_statuses_are_limited() -> None:
    assert ALLOWED_SQL_STATUSES == {"success", "insufficient_evidence", "validation_failed", "access_failed", "error"}


def test_public_sql_result_shape_is_stable() -> None:
    result = public_sql_result(
        step_id="step_1",
        status="validation_failed",
        validated_output=empty_validated_output(),
        limitations=[],
        errors=[{"code": "invalid_sql", "message": "Invalid SQL."}],
        audit_metadata={"sql_hash": "hash"},
    )

    assert set(result) == {"step_id", "step_type", "status", "validated_output", "limitations", "errors", "audit_metadata"}
    assert result["step_type"] == "sql"
    assert set(result["validated_output"]) == {
        "rows",
        "columns",
        "row_count",
        "sql_hash",
        "calculation_metadata",
        "execution_metadata",
    }


def test_parse_intent_preserves_free_semantic_json_object() -> None:
    raw_intent = {
        "table_keys": ["table_1"],
        "column_keys": ["price"],
        "join_keys": [],
        "semantic": {
            "calculation": "SUM(price)",
            "conditions": ["WHERE status = 'paid'", {"arbitrary": [1, True, None]}],
        },
        "expected_outputs": ["total_sales"],
    }

    assert parse_intent(raw_intent) == raw_intent


@pytest.mark.parametrize(
    "raw_intent",
    [
        {},
        {"goal": "Describe the requested result."},
        {"table_keys": [], "column_keys": [], "join_keys": []},
    ],
)
def test_parse_intent_accepts_missing_or_empty_optional_key_arrays(raw_intent: dict) -> None:
    assert parse_intent(raw_intent) == raw_intent


def test_parse_intent_decodes_json_object_text() -> None:
    assert parse_intent('{"goal":"count rows","metrics":{"shape":"free"}}') == {
        "goal": "count rows",
        "metrics": {"shape": "free"},
    }


@pytest.mark.parametrize("raw_intent", ["not json", "[]", '"scalar"', "1", "true", "null", [], None])
def test_parse_intent_rejects_unreadable_or_non_object_json(raw_intent: object) -> None:
    with pytest.raises(ValueError, match="intent_unreadable"):
        parse_intent(raw_intent)
