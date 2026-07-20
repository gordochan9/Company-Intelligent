from __future__ import annotations

from app.tools.sql_rag.rag.state import STATUS_INSUFFICIENT, RagState, fail_state


def select_relevant_documents(state: RagState) -> RagState:
    plan = state.get("rag_search_plan") or {}
    key_set = set(plan.get("document_keys", []))
    documents = (state.get("filtered_rag_schema") or {}).get("documents", [])
    selected = [document for document in documents if document["document_key"] in key_set]
    if not selected:
        return fail_state(
            "select_relevant_documents",
            "no_relevant_rag_documents",
            "No relevant permitted RAG documents were selected.",
            status=STATUS_INSUFFICIENT,
        )
    return {"selected_documents": selected, "audit_metadata": {**state.get("audit_metadata", {}), "selected_document_count": len(selected)}}
