from __future__ import annotations

import pytest

from app.graphs.final_answer_composer.contracts import FinalAnswerContractError, build_llm_payload, normalize_final_answer_context, parse_llm_json


def test_llm_payload_uses_only_approved_fields() -> None:
    context = normalize_final_answer_context(
        {
            "status": "success",
            "answer_material": {
                "obligations": [{"obligation_id": "o1", "description": "Count customers."}],
                "structured_results": [
                    {"step_id": "step_1", "goal": "Count customers.", "rows": [], "row_count": 0}
                ],
                "document_evidence": [],
            },
            "citations": [{"citation_id": "c1"}],
            "limitations": [],
            "errors": [],
            "trusted_user_context": {"email": "hidden@example.test"},
            "debug": {"hidden": True},
        }
    )

    payload = build_llm_payload("Question?", context)["payload"]

    assert set(payload) == {"user_question", "final_answer_context"}
    assert set(payload["final_answer_context"]) == {"status", "answer_material", "citations", "limitations", "errors"}
    assert "trusted_user_context" not in repr(payload)
    assert "debug" not in repr(payload)
    assert payload["user_question"] == "Question?"
    system_prompt = build_llm_payload("Question?", context)["system_prompt"]
    assert "each obligation" in system_prompt
    assert "step goal" in system_prompt
    assert "exact values verbatim" in system_prompt
    assert "count, list, customer, contact, category, and amount" in system_prompt
    assert "row_count is 0" in system_prompt


def test_parse_valid_json_answer() -> None:
    parsed = parse_llm_json('{"answer_text": "Done.", "used_citation_ids": ["c1"]}')

    assert parsed == {"answer_text": "Done.", "used_citation_ids": ["c1"]}


def test_missing_used_citation_ids_defaults_to_empty_list() -> None:
    parsed = parse_llm_json({"answer_text": "Done."})

    assert parsed == {"answer_text": "Done.", "used_citation_ids": []}


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        ("not json", "final_answer_llm_json_unreadable"),
        ({"used_citation_ids": []}, "final_answer_missing_answer_text"),
        ({"answer_text": "Done.", "used_citation_ids": [1]}, "final_answer_invalid_citation_ids"),
        ({"answer_text": "Done.", "extra": True}, "final_answer_llm_extra_fields"),
    ],
)
def test_invalid_llm_json_fails_safely(raw, code: str) -> None:
    with pytest.raises(FinalAnswerContractError) as exc:
        parse_llm_json(raw)

    assert exc.value.code == code
