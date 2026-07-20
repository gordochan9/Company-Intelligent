from __future__ import annotations

from app.tools.sql_rag.nodes.adapter import adapter


def test_adapter_emits_tool_results_and_final_answer_context_without_answer_text() -> None:
    result = adapter(
        {
            "final_result_bundle": {
                "tool": "sql_rag",
                "status": "success",
                "validated_outputs": [],
                "validated_evidence": [{"evidence_ref": "ev1"}],
                "validated_citations": [{"citation_id": "c1"}],
                "validated_sql_rows": [{"amount": 100}],
                "answer_material": {
                    "obligations": [{"obligation_id": "o1", "description": "Return amount."}],
                    "structured_results": [{"step_id": "step_1", "rows": [{"amount": 100}], "row_count": 1}],
                    "document_evidence": [],
                },
                "limitations": [],
                "errors": [],
                "permission_safe_metadata": {"executed_step_ids": ["step_1"]},
                "audit_metadata": {"final_bundle_status": "success"},
            }
        }
    )

    assert result["tool_results"][0]["tool"] == "sql_rag"
    assert result["tool_results"][0]["status"] == "success"
    assert result["final_answer_context"]["tool"] == "sql_rag"
    assert result["final_answer_context"]["validated_sql_rows"] == [{"amount": 100}]
    assert result["final_answer_context"]["answer_material"]["structured_results"][0]["step_id"] == "step_1"
    assert "answer" not in result["final_answer_context"]
    assert "raw_sql" not in repr(result)
    assert "raw_chunks" not in repr(result)
