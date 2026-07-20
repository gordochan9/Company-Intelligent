from __future__ import annotations

from typing import Any

from app.tools.sql_rag.rag.services.schema import UNSAFE_TEXT_RE


def validate_chunks(chunks: list[dict[str, Any]], selected_documents: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    selected_refs = {document["document_ref"] for document in selected_documents}
    evidence = []
    citations = []
    for index, chunk in enumerate(chunks, start=1):
        document_ref = str(chunk.get("document_ref") or "")
        text = str(chunk.get("text") or "")
        if document_ref not in selected_refs or not text.strip() or UNSAFE_TEXT_RE.search(text):
            continue
        citation = dict(chunk.get("citation") or {})
        citation_id = str(citation.get("citation_id") or f"rag_citation_{index}")
        safe_path = str(citation.get("safe_path") or chunk.get("safe_path") or "")
        if UNSAFE_TEXT_RE.search(safe_path):
            continue
        evidence_ref = f"rag_evidence_{index}"
        evidence.append(
            {
                "evidence_ref": evidence_ref,
                "document_ref": document_ref,
                "text": text,
                "citation_id": citation_id,
            }
        )
        citations.append(
            {
                "citation_id": citation_id,
                "title": str(citation.get("title") or chunk.get("title") or ""),
                "safe_location_path": safe_path,
                "evidence_ref": evidence_ref,
            }
        )
    return evidence, citations
