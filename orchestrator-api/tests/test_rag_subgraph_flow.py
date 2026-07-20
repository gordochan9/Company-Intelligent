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


def _permission_schema() -> dict:
    return {
        "schema_version": "3.0",
        "allowed_resources": {
            "allowed_scopes": ["employee_guidelines"],
            "allowed_catalog_entry_ids": ["catalog:employee_guidelines"],
            "allowed_rag_namespaces": ["employee_guidelines"],
        },
    }


def _state(question: str = "What does the HR policy say about sick leave?") -> dict:
    return {
        "request_id": "req-rag",
        "trace_id": "trace-rag",
        "step_id": "step_1",
        "rag_question": question,
        "step_goal": "Find policy evidence.",
        "trusted_user_context": {"email": "user@demo.com"},
        "user_permission_schema": _permission_schema(),
        "obligations": [{"obligation_id": "o1", "description": "Find policy evidence."}],
        "dependency_context": {},
        "conversation_context": {},
        "trace": [],
    }


def _documents() -> list[dict]:
    return [
        {
            "document_ref": "catalog:employee_guidelines",
            "permission_scope_key": "employee_guidelines",
            "rag_namespace": "employee_guidelines",
            "title": "Employee Guidelines",
            "safe_path": "Employee Guidelines / policy.md",
            "summary": "Guidance for sick leave and remote work.",
            "keywords": ["sick leave", "remote work"],
            "headers": ["Sick leave"],
            "safe_row_samples": [],
            "chunks": [
                {
                    "text": "Employees may use sick leave when they are ill and should notify their manager.",
                    "citation": {
                        "citation_id": "c1",
                        "title": "Employee Guidelines",
                        "safe_path": "Employee Guidelines / policy.md",
                    },
                }
            ],
        }
    ]


def test_valid_rag_step_returns_success_with_evidence_and_citations() -> None:
    set_rag_documents(_documents())
    set_rag_plan_model(lambda _payload: {"document_keys": ["doc_1"], "query_terms": ["sick leave"], "reason": "Policy document."})

    result = run_rag_workflow(_state())

    rag_result = result["rag_result"]
    assert rag_result["status"] == "success"
    assert rag_result["step_type"] == "rag"
    assert rag_result["validated_output"]["validated_evidence"][0]["citation_id"] == "c1"
    assert rag_result["validated_output"]["validated_citations"] == [
        {
            "citation_id": "c1",
            "title": "Employee Guidelines",
            "safe_location_path": "Employee Guidelines / policy.md",
            "evidence_ref": "rag_evidence_1",
        }
    ]


def test_rag_plan_model_receives_bounded_prompt() -> None:
    captured: dict = {}

    def model(payload: dict) -> dict:
        captured.update(payload)
        return {"document_keys": ["doc_1"], "query_terms": ["sick leave"], "reason": "Policy document."}

    set_rag_documents(_documents())
    set_rag_plan_model(model)

    run_rag_workflow(_state())

    assert "system_prompt" in captured
    assert "payload" in captured
    assert captured["payload"]["filtered_rag_schema"]["documents"][0]["document_key"] == "doc_1"
    assert "document_key" in captured["system_prompt"]


def test_unknown_document_key_routes_to_insufficient_evidence() -> None:
    set_rag_documents(_documents())
    set_rag_plan_model(lambda _payload: {"document_keys": ["doc_9"], "query_terms": ["sick leave"]})

    result = run_rag_workflow(_state())

    assert result["rag_result"]["status"] == "insufficient_evidence"
    assert result["rag_result"]["validated_output"]["validated_evidence"] == []


def test_no_matching_chunks_routes_to_insufficient_evidence() -> None:
    set_rag_documents(_documents())
    set_rag_plan_model(lambda _payload: {"document_keys": ["doc_1"], "query_terms": ["nonmatching"]})

    result = run_rag_workflow(_state())

    assert result["rag_result"]["status"] == "insufficient_evidence"
    assert result["failure_code"] == "no_relevant_rag_chunks"


def test_missing_model_returns_error_without_retrieval_fallback() -> None:
    set_rag_documents(_documents())

    result = run_rag_workflow(_state())

    assert result["rag_result"]["status"] == "error"
    assert result["rag_result"]["errors"][0]["code"] == "rag_search_model_unavailable"
