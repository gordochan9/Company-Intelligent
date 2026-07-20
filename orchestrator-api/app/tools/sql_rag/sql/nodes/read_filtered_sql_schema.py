from __future__ import annotations

from app.tools.sql_rag.sql.services.schema import make_llm_readable_schema
from app.tools.sql_rag.sql.state import SqlState, fail_state


def read_filtered_sql_schema(state: SqlState) -> SqlState:
    schema = state.get("filtered_sql_schema")
    if not isinstance(schema, dict):
        return fail_state("read_filtered_sql_schema", "missing_filtered_sql_schema", "SQL schema is unavailable.")
    readable = make_llm_readable_schema(schema)
    readable["approved_join_policy"] = "optional_verified_hints"
    return {"llm_readable_sql_schema": readable}
