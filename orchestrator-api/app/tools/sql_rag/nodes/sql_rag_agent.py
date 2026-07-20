from __future__ import annotations

from app.tools.sql_rag.contracts import require_sql_rag_input
from app.tools.sql_rag.state import RESULT_ACCESS_FAILED, STATUS_NOT_STARTED, SqlRagState, fail_state


def sql_rag_agent(state: SqlRagState) -> SqlRagState:
    try:
        require_sql_rag_input(state)
    except PermissionError as exc:
        return fail_state(
            "sql_rag_agent",
            str(exc),
            "SQL/RAG permission context was invalid.",
            status="blocked",
            result_status=RESULT_ACCESS_FAILED,
        )
    except ValueError as exc:
        return fail_state("sql_rag_agent", str(exc), "SQL/RAG input was invalid.", status="invalid_plan")

    return {
        "request_id": str(state["request_id"]),
        "trace_id": str(state.get("trace_id") or ""),
        "session_id": state.get("session_id"),
        "user_question": str(state["user_question"]),
        "messages": list(state.get("messages") or []),
        "conversation_context": dict(state.get("conversation_context") or {}),
        "trusted_user_context": dict(state["trusted_user_context"]),
        "user_permission_schema": dict(state["user_permission_schema"]),
        "tool_selection": dict(state["tool_selection"]),
        "runtime_plan_status": STATUS_NOT_STARTED,
        "runtime_plan": None,
        "current_step": None,
        "current_child_result": None,
        "completed_steps": [],
        "covered_obligation_ids": [],
        "step_results": [],
        "dependency_context": {},
        "limitations": [],
        "errors": [],
        "audit_metadata": {"tool": "sql_rag", "agent_status": "selected"},
        "debug": {},
        "trace": list(state.get("trace") or []),
    }
