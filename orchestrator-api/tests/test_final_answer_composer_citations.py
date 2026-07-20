from __future__ import annotations

import pytest

from app.graphs.final_answer_composer.contracts import attach_citations
from app.graphs.final_answer_composer.graph import run_final_answer_composer
from app.graphs.final_answer_composer.nodes.call_final_answer_llm import set_final_answer_model


@pytest.fixture(autouse=True)
def reset_final_answer_model():
    set_final_answer_model(None)
    yield
    set_final_answer_model(None)


def test_attach_citations_drops_unknown_ids_and_does_not_create_objects() -> None:
    attached, unknown = attach_citations(
        [{"citation_id": "c1", "title": "Policy", "safe_location_path": "Policies / remote.md"}],
        ["c1", "missing"],
    )

    assert attached == [{"citation_id": "c1", "title": "Policy", "safe_location_path": "Policies / remote.md"}]
    assert unknown == ["missing"]


def test_public_citation_output_rejects_raw_paths_and_internal_ids() -> None:
    attached, unknown = attach_citations(
        [
            {"citation_id": "c1", "safe_location_path": "C:\\Users\\Gordon\\private.csv"},
            {"citation_id": "c2", "source_id": "internal-source", "safe_location_path": "Finance / ok.csv"},
            {"citation_id": "c3", "safe_location_path": "Finance / ok.csv"},
        ],
        ["c1", "c2", "c3"],
    )

    assert attached == [{"citation_id": "c3", "safe_location_path": "Finance / ok.csv"}]
    assert unknown == []


def test_unknown_citation_ids_are_logged_in_trace() -> None:
    set_final_answer_model(lambda _payload: {"answer_text": "See cited evidence.", "used_citation_ids": ["missing"]})

    result = run_final_answer_composer(
        {
            "request_id": "req-final",
            "trace_id": "trace-final",
            "user_question": "Question?",
            "final_answer_context": {
                "status": "success",
                "answer_material": {"document_evidence": []},
                "citations": [{"citation_id": "c1", "safe_location_path": "Policies / remote.md"}],
                "limitations": [],
                "errors": [],
            },
            "trace": [],
        }
    )

    assert result["public_citations"] == []
    assert any(entry["node_name"] == "attach_public_citations" for entry in result["trace"])
