from __future__ import annotations

from app.graphs.main.state import MainGraphState, safe_terminal_context
from app.tools.sql_rag.agent import run_sql_rag_agent


def tool_dispatch(state: MainGraphState) -> MainGraphState:
    selection = state.get("tool_selection") or {}
    selected = selection.get("selected_tools") or []
    if not any(isinstance(item, dict) and item.get("tool") == "sql_rag" for item in selected):
        return {
            "final_answer_context": safe_terminal_context(
                "unsupported",
                reason="No approved tool workflow was selected.",
                limitations=list(selection.get("limitations") or []),
                errors=list(selection.get("errors") or []),
            )
        }
    return run_sql_rag_agent(state)
