from __future__ import annotations

import pytest

from app.graphs.final_answer_composer.graph import run_final_answer_composer
from app.graphs.final_answer_composer.nodes.call_final_answer_llm import set_final_answer_model


@pytest.fixture(autouse=True)
def reset_final_answer_model():
    set_final_answer_model(None)
    yield
    set_final_answer_model(None)


def _state() -> dict:
    return {
        "request_id": "req-final",
        "trace_id": "trace-final",
        "user_question": "Question?",
        "final_answer_context": {
            "status": "success",
            "answer_material": {"document_evidence": []},
            "citations": [],
            "limitations": [],
            "errors": [],
        },
        "trace": [],
    }


def test_llm_success_response_is_logged_without_public_raw_response() -> None:
    set_final_answer_model(lambda _payload: {"answer_text": "Done.", "used_citation_ids": []})

    result = run_final_answer_composer(_state())

    assert any(entry["node_name"] == "log_final_answer_llm_response" for entry in result["trace"])
    assert "raw_final_answer_llm_response" not in result
    assert "llm_response" not in repr(
        {
            "final_answer": result["final_answer"],
            "public_citations": result["public_citations"],
            "public_limitations": result["public_limitations"],
        }
    )


def test_llm_parse_failure_is_logged_and_public_error_is_safe() -> None:
    set_final_answer_model(lambda _payload: "not json")

    result = run_final_answer_composer(_state())

    assert result["final_status"] == "error"
    assert any(entry["node_name"] == "log_final_answer_llm_response" for entry in result["trace"])
    assert result["public_citations"] == []


def test_provider_failure_fails_safely_and_logs_attempt() -> None:
    def model(_payload: dict) -> dict:
        raise RuntimeError("provider down")

    set_final_answer_model(model)

    result = run_final_answer_composer(_state())

    assert result["final_status"] == "error"
    assert any(entry["node_name"] == "log_final_answer_llm_response" for entry in result["trace"])
