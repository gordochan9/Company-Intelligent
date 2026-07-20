from __future__ import annotations

from app.graphs.main.nodes.request_intake import request_intake
from app.graphs.main.state import safe_terminal_context


def test_request_intake_initializes_required_main_state_fields() -> None:
    result = request_intake(
        {
            "user_question": "Question?",
            "openwebui_user_identity": {"email": "admin@demo.com"},
        }
    )

    assert result["request_id"]
    assert result["trace_id"]
    assert result["user_question"] == "Question?"
    assert result["openwebui_user_identity"] == {"email": "admin@demo.com"}
    assert result["tool_results"] == []
    assert result["errors"] == []


def test_safe_terminal_context_is_public_safe() -> None:
    context = safe_terminal_context("unsupported", reason="Unsupported.")

    assert context == {
        "status": "unsupported",
        "tool": None,
        "answer_material": {"document_evidence": [], "structured_results": [], "mixed_findings": []},
        "citations": [],
        "limitations": [],
        "errors": [{"code": "unsupported", "message": "Unsupported."}],
        "permission_safe_metadata": {},
    }
