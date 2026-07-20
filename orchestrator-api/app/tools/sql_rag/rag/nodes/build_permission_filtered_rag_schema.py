from __future__ import annotations

from app.tools.sql_rag.rag.services.repository import list_rag_documents
from app.tools.sql_rag.rag.services.schema import build_filtered_schema
from app.tools.sql_rag.rag.state import STATUS_INSUFFICIENT, RagState, fail_state


def build_permission_filtered_rag_schema(state: RagState) -> RagState:
    try:
        documents = list_rag_documents()
    except RuntimeError:
        return fail_state(
            "build_permission_filtered_rag_schema",
            "rag_runtime_store_unavailable",
            "RAG runtime store is unavailable.",
        )
    schema = build_filtered_schema(
        request_id=state["request_id"],
        step_id=state["step_id"],
        user_permission_schema=state["user_permission_schema"],
        documents=documents,
    )
    if not schema["documents"]:
        return fail_state(
            "build_permission_filtered_rag_schema",
            "no_allowed_rag_documents",
            "No permitted RAG documents are available for this step.",
            status=STATUS_INSUFFICIENT,
        )
    return {"filtered_rag_schema": schema, "audit_metadata": {"rag_schema_document_count": len(schema["documents"])}}
