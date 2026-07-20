from __future__ import annotations

from app.tools.sql_rag.graph import invoke_sql_rag_tool_graph
from app.tools.sql_rag.state import SqlRagState


def run_sql_rag_agent(main_state: SqlRagState) -> dict:
    result = invoke_sql_rag_tool_graph(main_state)
    return {
        "tool_results": result.get("tool_results", []),
        "final_answer_context": result.get("final_answer_context"),
        "trace": result.get("trace", []),
    }
