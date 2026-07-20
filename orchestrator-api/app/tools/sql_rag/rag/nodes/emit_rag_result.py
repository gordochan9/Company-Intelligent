from __future__ import annotations

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import append_trace_entry, emit_audit_event
from app.tools.sql_rag.rag.contracts import public_rag_result
from app.tools.sql_rag.rag.state import STATUS_SUCCESS, RagState


def emit_rag_result(state: RagState) -> RagState:
    validated_output = {
        "document_findings": [
            {
                "finding": item["text"],
                "evidence_refs": [item["evidence_ref"]],
                "source_labels": [item["citation_id"]],
            }
            for item in state.get("validated_evidence", [])
        ],
        "validated_evidence": state.get("validated_evidence", []),
        "validated_citations": state.get("validated_citations", []),
        "retrieval_metadata": {
            "selected_document_count": len(state.get("selected_documents", [])),
            "retrieved_chunk_count": len(state.get("retrieved_chunks", [])),
        },
    }
    result = emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.RAG,
        event_type="rag_result_emitted",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="rag_subgraph",
        node_name="emit_rag_result",
        metadata=state.get("audit_metadata", {}),
    )
    patch: RagState = {
        "rag_status": STATUS_SUCCESS,
        "rag_result": public_rag_result(
            step_id=state["step_id"],
            status=STATUS_SUCCESS,
            validated_output=validated_output,
            limitations=state.get("limitations", []),
            errors=[],
            audit_metadata=state.get("audit_metadata", {}),
        ),
    }
    return append_trace_entry(patch, result.trace_entry)
