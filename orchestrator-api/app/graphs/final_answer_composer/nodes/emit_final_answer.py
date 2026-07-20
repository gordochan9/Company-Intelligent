from __future__ import annotations

from app.graphs.final_answer_composer.state import FINAL_STATUS_BY_CONTEXT, FinalAnswerComposerState


def emit_final_answer(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    if state.get("final_status") == "error" and state.get("final_answer"):
        return {
            "final_answer": str(state["final_answer"]),
            "final_status": "error",
            "public_citations": [],
            "public_limitations": list(state.get("limitations") or []),
            "errors": list(state.get("errors") or []),
        }

    context = state.get("final_answer_context") or {}
    final_status = FINAL_STATUS_BY_CONTEXT.get(context.get("status"), "error")
    return {
        "final_answer": str(state.get("parsed_answer_text") or "I cannot produce a safe final answer for this request."),
        "final_status": final_status,
        "public_citations": list(state.get("public_citations") or []),
        "public_limitations": list(state.get("limitations") or []),
        "errors": list(state.get("errors") or []),
    }
