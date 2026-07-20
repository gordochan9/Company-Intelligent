from __future__ import annotations

from typing import Any

from app.db.runtime_store import PostgresRuntimeStore


_documents: list[dict[str, Any]] | None = None


def set_rag_documents(documents: list[dict[str, Any]]) -> None:
    global _documents
    _documents = [dict(document) for document in documents]


def list_rag_documents() -> list[dict[str, Any]]:
    if _documents is None:
        return PostgresRuntimeStore().list_rag_documents()
    return [dict(document) for document in _documents]


def find_document_chunks(document_refs: set[str], query_terms: list[str]) -> list[dict[str, Any]]:
    documents = list_rag_documents()
    terms = [term.casefold() for term in query_terms if term.strip()]
    chunks: list[dict[str, Any]] = []
    for document in documents:
        document_ref = str(document.get("document_ref") or "")
        if document_ref not in document_refs:
            continue
        for chunk in document.get("chunks", []):
            text = str(chunk.get("text") or "")
            haystack = text.casefold()
            if terms and not any(term in haystack for term in terms):
                continue
            chunks.append({**chunk, "document_ref": document_ref, "title": document.get("title"), "safe_path": document.get("safe_path")})
    return chunks
