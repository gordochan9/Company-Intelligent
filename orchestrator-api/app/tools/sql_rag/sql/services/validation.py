from __future__ import annotations

import hashlib
from typing import Any

from sqlglot import exp, parse
from sqlglot.errors import ParseError


_UNSAFE_EXPRESSION_TYPES = (
    exp.DDL,
    exp.DML,
    exp.Command,
    exp.Copy,
    exp.Drop,
    exp.Alter,
    exp.TruncateTable,
    exp.Execute,
    exp.Grant,
    exp.Revoke,
    exp.Transaction,
    exp.Commit,
    exp.Rollback,
)


class SqlValidationError(ValueError):
    def __init__(self, code: str, metadata: dict[str, Any]) -> None:
        super().__init__(code)
        self.metadata = metadata


def sql_hash(sql: str) -> str:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest()


def count_unbound_sql_parameters(sql: str) -> int:
    try:
        statements = parse(sql.strip(), read="postgres")
    except ParseError:
        return 0
    return sum(
        1
        for statement in statements
        if statement is not None
        for node in statement.walk()
        if isinstance(node, (exp.Parameter, exp.Placeholder))
    )


def validate_read_only_sql(sql: str, selected_resources: dict[str, Any]) -> dict[str, Any]:
    del selected_resources
    normalized = sql.strip()
    metadata: dict[str, Any] = {
        "statement_count": 0,
        "operation_types": [],
        "syntax_valid": False,
        "read_only": False,
    }
    try:
        statements = parse(normalized, read="postgres")
    except ParseError as exc:
        raise SqlValidationError("invalid_sql_syntax", metadata) from exc
    statements = [statement for statement in statements if statement is not None]
    metadata["syntax_valid"] = True
    metadata["statement_count"] = len(statements)
    metadata["operation_types"] = [type(statement).__name__ for statement in statements]
    if not statements:
        raise SqlValidationError("invalid_sql_syntax", metadata)
    if len(statements) > 1:
        raise SqlValidationError("multiple_sql_statements", metadata)
    for statement in statements:
        if not isinstance(statement, (exp.Query, exp.Values)) or any(
            isinstance(node, _UNSAFE_EXPRESSION_TYPES) for node in statement.walk()
        ):
            raise SqlValidationError("unsafe_sql_operation", metadata)
    metadata["read_only"] = True
    return {
        "sql": normalized,
        "sql_hash": sql_hash(normalized),
        **metadata,
        "validated": True,
    }
