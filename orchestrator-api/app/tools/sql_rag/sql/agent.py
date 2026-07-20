from __future__ import annotations

from app.tools.sql_rag.sql.graph import invoke_sql_subgraph
from app.tools.sql_rag.sql.state import SqlState


def run_sql_workflow(step_state: SqlState) -> SqlState:
    return invoke_sql_subgraph(step_state)
