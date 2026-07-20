from __future__ import annotations

import hashlib
from datetime import date, datetime
from decimal import Decimal

import pytest

from app.tools.sql_rag.sql.services.executor import validate_execution_result
from app.tools.sql_rag.sql.services.validation import validate_read_only_sql


SELECTED = {
    "tables": [{"runtime_relation_name": "finance_table"}],
    "columns": [{"column_name": "amount"}],
    "joins": [],
}


def test_valid_postgresql_is_preserved_without_limit() -> None:
    sql = "SELECT amount FROM finance_table"

    result = validate_read_only_sql(sql, SELECTED)

    assert result == {
        "sql": sql,
        "sql_hash": hashlib.sha256(sql.encode("utf-8")).hexdigest(),
        "statement_count": 1,
        "operation_types": ["Select"],
        "syntax_valid": True,
        "read_only": True,
        "validated": True,
    }


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT * FROM finance_table",
        "SELECT private_column FROM other_table",
        "SELECT name FROM orders JOIN customers ON orders.customer_id = customers.id",
    ],
)
def test_read_only_sql_does_not_validate_resources_columns_stars_or_joins(sql: str) -> None:
    assert validate_read_only_sql(sql, SELECTED)["validated"] is True


@pytest.mark.parametrize(
    "sql",
    [
        "WITH amounts AS (SELECT amount FROM finance_table) SELECT * FROM amounts",
        "SELECT SUM(orders.amount) FROM orders JOIN customers ON orders.customer_id = customers.id WHERE orders.amount > (SELECT AVG(amount) FROM orders)",
        "SELECT amount FROM finance_table UNION SELECT amount FROM other_table",
    ],
)
def test_single_read_only_query_forms_pass(sql: str) -> None:
    result = validate_read_only_sql(sql, SELECTED)

    assert result["sql"] == sql
    assert result["statement_count"] == 1
    assert result["read_only"] is True


def test_multiple_read_only_statements_are_rejected() -> None:
    with pytest.raises(ValueError, match="multiple_sql_statements"):
        validate_read_only_sql("SELECT 1; SELECT 2", SELECTED)


def test_multiple_statements_containing_unsafe_sql_fail_closed() -> None:
    with pytest.raises(ValueError, match="multiple_sql_statements"):
        validate_read_only_sql("SELECT 1; INSERT INTO finance_table (amount) VALUES (1)", SELECTED)


@pytest.mark.parametrize(
    "sql",
    [
        "INSERT INTO finance_table (amount) VALUES (1)",
        "UPDATE finance_table SET amount = 1",
        "DELETE FROM finance_table",
        "MERGE INTO finance_table USING other_table ON TRUE WHEN MATCHED THEN DELETE",
        "TRUNCATE TABLE finance_table",
        "CREATE TABLE other_table (amount numeric)",
        "ALTER TABLE finance_table ADD COLUMN other_column text",
        "DROP TABLE finance_table",
        "COPY finance_table TO '/tmp/export.csv'",
        "CALL refresh_finance()",
        "EXECUTE finance_plan",
        "BEGIN",
        "COMMIT",
        "ROLLBACK",
        "GRANT SELECT ON finance_table TO public",
        "REVOKE SELECT ON finance_table FROM public",
        "SET search_path TO public",
        "ANALYZE finance_table",
    ],
)
def test_non_read_only_ast_is_rejected(sql: str) -> None:
    with pytest.raises(ValueError, match="unsafe_sql_operation"):
        validate_read_only_sql(sql, SELECTED)


def test_invalid_syntax_is_rejected() -> None:
    with pytest.raises(ValueError, match="invalid_sql_syntax"):
        validate_read_only_sql("SELECT FROM", SELECTED)


def test_numeric_sql_is_never_rewritten() -> None:
    sql = "SELECT SUM(amount) AS total_amount FROM finance_table"

    result = validate_read_only_sql(sql, SELECTED)

    assert result["sql"] == sql
    assert "regexp_replace" not in result["sql"]


def test_execution_result_is_json_safe_and_preserves_zero_rows() -> None:
    populated = validate_execution_result(
        {
            "columns": ["total", "day", "created"],
            "rows": [{"total": Decimal("123.450"), "day": date(2026, 7, 15), "created": datetime(2026, 7, 15, 1, 2, 3)}],
        },
        "hash",
    )
    empty = validate_execution_result({"columns": ["total"], "rows": [], "row_count": 0}, "empty-hash")

    assert populated["rows"] == [{"total": "123.450", "day": "2026-07-15", "created": "2026-07-15T01:02:03"}]
    assert populated["execution_metadata"] == {"restricted_reader": False, "rls_enforced": False}
    assert empty["row_count"] == 0
    assert empty["rows"] == []


@pytest.mark.parametrize(
    "result",
    [
        {"columns": "amount", "rows": []},
        {"columns": [1], "rows": []},
        {"columns": ["amount"], "rows": ["not-a-row"]},
        {"columns": ["amount"], "rows": [], "row_count": "0"},
    ],
)
def test_malformed_execution_result_shape_is_rejected(result: dict) -> None:
    with pytest.raises(ValueError, match="malformed_sql_execution_result"):
        validate_execution_result(result, "hash")
