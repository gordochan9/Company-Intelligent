from __future__ import annotations

from app.tools.sql_rag.rag.services.evidence import validate_chunks
from app.tools.sql_rag.rag.state import STATUS_INSUFFICIENT, RagState, fail_state


def validate_rag_evidence(state: RagState) -> RagState:
    evidence, citations = validate_chunks(state.get("retrieved_chunks", []), state.get("selected_documents", []))
    if not evidence:
        return fail_state(
            "validate_rag_evidence",
            "no_valid_rag_evidence",
            "Retrieved RAG evidence was not sufficient or citation-safe.",
            status=STATUS_INSUFFICIENT,
        )
    return {
        "validated_evidence": evidence,
        "validated_citations": citations,
        "audit_metadata": {
            **state.get("audit_metadata", {}),
            "validated_evidence_count": len(evidence),
            "citation_count": len(citations),
        },
    }
