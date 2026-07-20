from __future__ import annotations

from app.tools.sql_rag.rag.contracts import require_rag_input
from app.tools.sql_rag.rag.state import STATUS_RUNNING, RagState, fail_state


def rag_intake(state: RagState) -> RagState:
    try:
        require_rag_input(state)
    except ValueError as exc:
        return fail_state("rag_intake", str(exc), "RAG input is missing or malformed.")
    return {
        "request_id": state["request_id"],
        "trace_id": state.get("trace_id", ""),
        "step_id": state["step_id"],
        "rag_question": str(state.get("rag_question") or state.get("step_goal") or ""),
        "step_goal": str(state.get("step_goal") or ""),
        "obligations": list(state.get("obligations") or []),
        "trusted_user_context": dict(state["trusted_user_context"]),
        "user_permission_schema": dict(state["user_permission_schema"]),
        "dependency_context": dict(state.get("dependency_context") or {}),
        "conversation_context": state.get("conversation_context"),
        "filtered_rag_schema": None,
        "llm_readable_rag_schema": None,
        "rag_search_plan": None,
        "raw_rag_search_plan": None,
        "selected_documents": [],
        "retrieved_chunks": [],
        "validated_evidence": [],
        "validated_citations": [],
        "rag_status": STATUS_RUNNING,
        "limitations": [],
        "errors": [],
        "audit_metadata": {},
        "debug": {},
        "failed_node": None,
        "failure_code": None,
        "trace": list(state.get("trace", [])),
    }
