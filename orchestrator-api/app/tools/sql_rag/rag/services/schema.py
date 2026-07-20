from __future__ import annotations

import re
from typing import Any


UNSAFE_TEXT_RE = re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/|/mnt/c/Users/|file://|postgres(?:ql)?://|sk-[A-Za-z0-9_-]{8,})", re.IGNORECASE)


def build_filtered_schema(
    *,
    request_id: str,
    step_id: str,
    user_permission_schema: dict[str, Any],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    resources = user_permission_schema["allowed_resources"]
    allowed_scopes = set(resources.get("allowed_scopes", []))
    allowed_refs = set(resources.get("allowed_catalog_entry_ids", []))
    allowed_namespaces = set(resources.get("allowed_rag_namespaces", []))
    safe_documents = []
    for document in documents:
        document_ref = str(document.get("document_ref") or "")
        scope = str(document.get("permission_scope_key") or "")
        namespace = str(document.get("rag_namespace") or scope)
        if document_ref not in allowed_refs and scope not in allowed_scopes and namespace not in allowed_namespaces:
            continue
        safe_documents.append(
            {
                "document_key": f"doc_{len(safe_documents) + 1}",
                "document_ref": document_ref,
                "permission_scope_key": scope,
                "title": _safe_text(document.get("title")),
                "safe_path": _safe_text(document.get("safe_path")),
                "summary": _safe_text(document.get("summary")),
                "keywords": list(document.get("keywords", [])),
                "headers": [_safe_text(item) for item in document.get("headers", [])],
                "safe_row_samples": [_safe_text(item) for item in document.get("safe_row_samples", [])],
            }
        )
    return {
        "schema_version": "3.0",
        "request_id": request_id,
        "step_id": step_id,
        "documents": safe_documents,
    }


def make_llm_readable_schema(filtered_schema: dict[str, Any]) -> dict[str, Any]:
    documents = []
    for document in filtered_schema.get("documents", []):
        documents.append(
            {
                "document_key": document["document_key"],
                "title": document.get("title"),
                "safe_path": document.get("safe_path"),
                "summary": document.get("summary"),
                "keywords": document.get("keywords", []),
                "headers": document.get("headers", []),
                "safe_row_samples": document.get("safe_row_samples", []),
            }
        )
    return {"schema_version": filtered_schema.get("schema_version"), "documents": documents}


def _safe_text(value: Any) -> str:
    text = str(value or "")
    return "[REDACTED]" if UNSAFE_TEXT_RE.search(text) else text
