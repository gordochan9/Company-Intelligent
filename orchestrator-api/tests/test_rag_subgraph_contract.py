from __future__ import annotations

from app.tools.sql_rag.rag.contracts import public_rag_result, require_rag_input
from app.tools.sql_rag.rag.nodes.rag_intake import rag_intake
from app.tools.sql_rag.rag.state import ALLOWED_RAG_STATUSES, empty_validated_output


def test_rag_input_contract_requires_core_step_and_permission_fields() -> None:
    state = {
        "request_id": "req",
        "step_id": "step",
        "rag_question": "question",
        "trusted_user_context": {"email": "user@example.test"},
        "user_permission_schema": {
            "allowed_resources": {
                "allowed_scopes": [],
                "allowed_catalog_entry_ids": [],
                "allowed_rag_namespaces": [],
            }
        },
        "obligations": [{"obligation_id": "o1", "description": "Find policy evidence."}],
    }

    require_rag_input(state)

    intake = rag_intake(state)
    assert intake["obligations"] == state["obligations"]
    assert "required_inputs" not in intake
    assert "expected_outputs" not in intake


def test_rag_public_statuses_are_limited_to_child_rag_statuses() -> None:
    assert ALLOWED_RAG_STATUSES == {"success", "insufficient_evidence", "error"}
    for forbidden in ["access_failed", "validation_failed", "denied", "permission_failed"]:
        assert forbidden not in ALLOWED_RAG_STATUSES


def test_public_rag_result_shape_is_stable() -> None:
    result = public_rag_result(
        step_id="step_1",
        status="insufficient_evidence",
        validated_output=empty_validated_output(),
        limitations=[],
        errors=[{"code": "no_evidence", "message": "No evidence."}],
        audit_metadata={"failure_code": "no_evidence"},
    )

    assert set(result) == {"step_id", "step_type", "status", "validated_output", "limitations", "errors", "audit_metadata"}
    assert result["step_type"] == "rag"
    assert result["validated_output"] == {
        "document_findings": [],
        "validated_evidence": [],
        "validated_citations": [],
        "retrieval_metadata": {},
    }
