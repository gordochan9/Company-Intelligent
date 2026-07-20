from __future__ import annotations

from app.tools.sql_rag.rag.services.schema import make_llm_readable_schema
from app.tools.sql_rag.rag.state import RagState, fail_state


def read_filtered_rag_schema(state: RagState) -> RagState:
    filtered_schema = state.get("filtered_rag_schema")
    if not isinstance(filtered_schema, dict):
        return fail_state("read_filtered_rag_schema", "missing_filtered_rag_schema", "RAG schema is unavailable.")
    return {"llm_readable_rag_schema": make_llm_readable_schema(filtered_schema)}
