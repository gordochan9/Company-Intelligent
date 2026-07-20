from __future__ import annotations

import pytest

from app.tools.sql_rag.rag.agent import run_rag_workflow
from app.tools.sql_rag.rag.services.repository import set_rag_documents
from app.tools.sql_rag.rag.services.search_plan import set_rag_plan_model


@pytest.fixture(autouse=True)
def reset_rag_services():
    set_rag_documents([])
    set_rag_plan_model(None)
    yield
    set_rag_documents([])
    set_rag_plan_model(None)


def _base_state() -> dict:
    return {
        "request_id": "req-rag-security",
        "step_id": "step_1",
        "rag_question": "Find sick leave policy.",
        "step_goal": "Find permitted policy evidence.",
        "trusted_user_context": {"email": "user@demo.com"},
        "user_permission_schema": {
            "allowed_resources": {
                "allowed_scopes": ["employee_guidelines"],
                "allowed_catalog_entry_ids": ["catalog:employee_guidelines"],
                "allowed_rag_namespaces": ["employee_guidelines"],
            }
        },
        "dependency_context": {},
        "trace": [],
    }


def test_missing_permission_schema_returns_error_failure() -> None:
    state = _base_state()
    state.pop("user_permission_schema")

    result = run_rag_workflow(state)

    assert result["rag_result"]["status"] == "error"
    assert result["rag_result"]["errors"][0]["code"] == "missing_rag_input"


def test_malformed_permission_schema_returns_error_failure() -> None:
    state = _base_state()
    state["user_permission_schema"] = {"allowed_resources": {}}

    result = run_rag_workflow(state)

    assert result["rag_result"]["status"] == "error"
    assert result["rag_result"]["errors"][0]["code"] == "malformed_permission_schema"


def test_denied_document_is_not_exposed_in_filtered_schema_or_selected() -> None:
    set_rag_documents(
        [
            {
                "document_ref": "catalog:employee_guidelines",
                "permission_scope_key": "employee_guidelines",
                "title": "Employee Guidelines",
                "safe_path": "Employee Guidelines / policy.md",
                "chunks": [{"text": "Sick leave evidence.", "citation": {"citation_id": "c1"}}],
            },
            {
                "document_ref": "catalog:finance",
                "permission_scope_key": "finance",
                "title": "Finance Restricted",
                "safe_path": "Finance / restricted.md",
                "chunks": [{"text": "Restricted finance evidence.", "citation": {"citation_id": "c2"}}],
            },
        ]
    )
    set_rag_plan_model(lambda _payload: {"document_keys": ["doc_2"], "query_terms": ["finance"]})

    result = run_rag_workflow(_base_state())

    assert result["llm_readable_rag_schema"]["documents"] == [
        {
            "document_key": "doc_1",
            "title": "Employee Guidelines",
            "safe_path": "Employee Guidelines / policy.md",
            "summary": "",
            "keywords": [],
            "headers": [],
            "safe_row_samples": [],
        }
    ]
    assert result["rag_result"]["status"] == "insufficient_evidence"


def test_retrieved_chunk_from_unselected_document_is_rejected() -> None:
    set_rag_documents(
        [
            {
                "document_ref": "catalog:employee_guidelines",
                "permission_scope_key": "employee_guidelines",
                "title": "Employee Guidelines",
                "safe_path": "Employee Guidelines / policy.md",
                "chunks": [{"text": "Sick leave evidence.", "citation": {"citation_id": "c1"}}],
            },
            {
                "document_ref": "catalog:file_server",
                "permission_scope_key": "file_server",
                "title": "File Server",
                "safe_path": "File Server / handbook.md",
                "chunks": [{"text": "Sick leave evidence.", "citation": {"citation_id": "c2"}}],
            },
        ]
    )
    state = _base_state()
    state["user_permission_schema"]["allowed_resources"]["allowed_scopes"].append("file_server")
    state["user_permission_schema"]["allowed_resources"]["allowed_catalog_entry_ids"].append("catalog:file_server")
    state["user_permission_schema"]["allowed_resources"]["allowed_rag_namespaces"].append("file_server")
    set_rag_plan_model(lambda _payload: {"document_keys": ["doc_1"], "query_terms": ["sick"]})

    result = run_rag_workflow(state)

    assert {item["document_ref"] for item in result["validated_evidence"]} == {"catalog:employee_guidelines"}


def test_unsafe_paths_are_redacted_from_llm_schema_and_output() -> None:
    set_rag_documents(
        [
            {
                "document_ref": "catalog:employee_guidelines",
                "permission_scope_key": "employee_guidelines",
                "title": "Employee Guidelines",
                "safe_path": r"C:\Users\Redacted\policy.md",
                "chunks": [{"text": "Sick leave evidence.", "citation": {"citation_id": "c1", "safe_path": r"C:\Users\Redacted\policy.md"}}],
            }
        ]
    )
    set_rag_plan_model(lambda _payload: {"document_keys": ["doc_1"], "query_terms": ["sick"]})

    result = run_rag_workflow(_base_state())

    assert result["llm_readable_rag_schema"]["documents"][0]["safe_path"] == "[REDACTED]"
    assert result["rag_result"]["status"] == "insufficient_evidence"
    assert "C:\\Users" not in repr(result["rag_result"])
