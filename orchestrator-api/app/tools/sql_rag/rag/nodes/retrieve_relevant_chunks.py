from __future__ import annotations

from app.tools.sql_rag.rag.services.repository import find_document_chunks
from app.tools.sql_rag.rag.state import STATUS_INSUFFICIENT, RagState, fail_state


def retrieve_relevant_chunks(state: RagState) -> RagState:
    selected_refs = {document["document_ref"] for document in state.get("selected_documents", [])}
    query_terms = list((state.get("rag_search_plan") or {}).get("query_terms", []))
    chunks = find_document_chunks(selected_refs, query_terms)
    if not chunks:
        return fail_state(
            "retrieve_relevant_chunks",
            "no_relevant_rag_chunks",
            "No relevant RAG evidence was found in selected documents.",
            status=STATUS_INSUFFICIENT,
        )
    return {"retrieved_chunks": chunks, "audit_metadata": {**state.get("audit_metadata", {}), "retrieved_chunk_count": len(chunks)}}
