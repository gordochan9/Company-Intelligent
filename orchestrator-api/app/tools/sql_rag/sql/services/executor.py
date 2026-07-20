from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from psycopg import Error, OperationalError, errors

from app.db.runtime_store import PostgresRuntimeStore


_Executor = Callable[[str, dict[str, Any]], dict[str, Any]]
_executor: _Executor | None = None


class SqlExecutorUnavailable(RuntimeError):
    pass


class SqlExecutionFailed(RuntimeError):
    pass


def set_sql_executor(executor: _Executor | None) -> None:
    global _executor
    _executor = executor


def execute_validated_sql(validated_sql: dict[str, Any]) -> dict[str, Any]:
    executor = _executor
    try:
        if executor is not None:
            return executor(validated_sql["sql"], validated_sql)
        return PostgresRuntimeStore().execute_read_only_sql(
            validated_sql["sql"],
            list(validated_sql.get("permission_scope_keys") or []),
            list(validated_sql.get("permission_resource_keys") or []),
        )
    except errors.InsufficientPrivilege as exc:
        raise PermissionError("Restricted SQL execution was not allowed.") from exc
    except OperationalError as exc:
        raise SqlExecutorUnavailable("No restricted SQL executor is configured.") from exc
    except Error as exc:
        raise SqlExecutionFailed("SQL execution failed.") from exc
    except RuntimeError as exc:
        if executor is not None:
            raise
        raise SqlExecutorUnavailable("No restricted SQL executor is configured.") from exc


def validate_execution_result(result: dict[str, Any], expected_hash: str) -> dict[str, Any]:
    rows = result.get("rows", [])
    columns = result.get("columns", [])
    row_count = result.get("row_count", len(rows) if isinstance(rows, list) else 0)
    if (
        not isinstance(rows, list)
        or not isinstance(columns, list)
        or any(not isinstance(column, str) for column in columns)
        or any(not isinstance(row, dict) for row in rows)
        or not isinstance(row_count, int)
        or isinstance(row_count, bool)
        or row_count < 0
    ):
        raise ValueError("malformed_sql_execution_result")
    return {
        "rows": [_json_safe_row(row) for row in rows],
        "columns": columns,
        "row_count": row_count,
        "sql_hash": expected_hash,
        "calculation_metadata": dict(result.get("calculation_metadata") or {}),
        "execution_metadata": {
            "restricted_reader": bool(result.get("restricted_reader", False)),
            "rls_enforced": bool(result.get("rls_enforced", False)),
        },
    }


def _json_safe_row(row: Any) -> dict[str, Any]:
    return {str(key): _json_safe_value(value) for key, value in row.items()}


def _json_safe_value(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    return value
