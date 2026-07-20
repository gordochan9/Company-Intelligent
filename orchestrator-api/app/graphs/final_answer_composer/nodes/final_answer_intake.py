from __future__ import annotations

from app.graphs.final_answer_composer.state import STATUS_RUNNING, FinalAnswerComposerState


def final_answer_intake(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    return {
        "request_id": str(state.get("request_id") or ""),
        "trace_id": str(state.get("trace_id") or ""),
        "composer_status": STATUS_RUNNING,
        "errors": [],
        "limitations": [],
        "public_citations": [],
        "unknown_citation_ids": [],
        "trace": list(state.get("trace") or []),
    }
