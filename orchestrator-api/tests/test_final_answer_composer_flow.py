from __future__ import annotations

import pytest

from app.graphs.final_answer_composer.graph import run_final_answer_composer
from app.graphs.final_answer_composer.nodes.call_final_answer_llm import set_final_answer_model


@pytest.fixture(autouse=True)
def reset_final_answer_model():
    set_final_answer_model(None)
    yield
    set_final_answer_model(None)


def _state(status: str = "success") -> dict:
    return {
        "request_id": "req-final",
        "trace_id": "trace-final",
        "user_question": "What invoices are overdue?",
        "final_answer_context": {
            "status": status,
            "tool": "sql_rag",
            "answer_material": {
                "obligations": [{"obligation_id": "o1", "description": "Return overdue invoices."}],
                "structured_results": [
                    {
                        "step_id": "step_1",
                        "goal": "Return overdue invoice amounts.",
                        "obligation_ids": ["o1"],
                        "step_type": "sql",
                        "status": "success",
                        "columns": ["amount"],
                        "rows": [{"amount": 100}],
                        "row_count": 1,
                        "limitations": [],
                        "errors": [],
                    }
                ],
                "document_evidence": [],
            },
            "validated_evidence": [{"evidence_ref": "ev1", "text": "Policy evidence."}],
            "validated_sql_rows": [{"amount": 100}],
            "validated_citations": [{"citation_id": "c1", "title": "Finance", "safe_location_path": "Finance / invoices.csv"}],
            "limitations": [],
            "errors": [],
        },
        "trace": [],
    }


def test_success_context_produces_answered_status_and_public_citations() -> None:
    set_final_answer_model(lambda _payload: {"answer_text": "Invoice amount is 100.", "used_citation_ids": ["c1"]})

    result = run_final_answer_composer(_state())

    assert result["final_status"] == "answered"
    assert result["final_answer"] == "Invoice amount is 100."
    assert result["public_citations"] == [{"citation_id": "c1", "title": "Finance", "safe_location_path": "Finance / invoices.csv"}]


@pytest.mark.parametrize(
    ("context_status", "final_status"),
    [
        ("denied", "denied"),
        ("access_failed", "access_failed"),
        ("unsupported", "unsupported"),
        ("clarification", "clarification"),
        ("insufficient_evidence", "insufficient_evidence"),
        ("validation_failed", "validation_failed"),
        ("error", "error"),
    ],
)
def test_terminal_context_status_maps_to_public_final_status(context_status: str, final_status: str) -> None:
    set_final_answer_model(lambda _payload: {"answer_text": "Safe terminal answer.", "used_citation_ids": []})

    result = run_final_answer_composer(_state(context_status))

    assert result["final_status"] == final_status
    assert result["final_answer"] == "Safe terminal answer."


def test_malformed_context_does_not_call_llm() -> None:
    called = False

    def model(_payload: dict) -> dict:
        nonlocal called
        called = True
        return {"answer_text": "Should not run."}

    set_final_answer_model(model)
    state = _state()
    state["final_answer_context"] = None

    result = run_final_answer_composer(state)

    assert called is False
    assert result["final_status"] == "error"
    assert result["public_citations"] == []
