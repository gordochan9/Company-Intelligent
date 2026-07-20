from __future__ import annotations

from app.graphs.final_answer_composer.contracts import attach_citations
from app.graphs.final_answer_composer.state import FinalAnswerComposerState
from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import append_trace_entry, emit_audit_event


def attach_public_citations(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    public_citations, unknown = attach_citations(
        list(state.get("adapter_citations") or []),
        list(state.get("parsed_used_citation_ids") or []),
    )
    patch: FinalAnswerComposerState = {"public_citations": public_citations, "unknown_citation_ids": unknown}
    if unknown:
        result = emit_audit_event(
            request_id=state.get("request_id"),
            trace_id=state.get("trace_id"),
            event_category=AuditEventCategory.FINAL_ANSWER,
            event_type="unknown_final_answer_citation_ids",
            status=AuditEventStatus.VALIDATION_FAILED,
            workflow_name="final_answer_composer",
            node_name="attach_public_citations",
            metadata={"unknown_citation_count": len(unknown)},
            restricted_metadata={"unknown_citation_ids": unknown},
        )
        patch = append_trace_entry(patch, result.trace_entry)
    return patch
