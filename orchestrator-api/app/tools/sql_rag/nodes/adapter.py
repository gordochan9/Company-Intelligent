from __future__ import annotations

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.contracts import final_answer_context_from_bundle, public_tool_result
from app.tools.sql_rag.state import RESULT_ERROR, SqlRagState, safe_error


def adapter(state: SqlRagState) -> SqlRagState:
    bundle = state.get("final_result_bundle")
    if not isinstance(bundle, dict):
        bundle = {
            "tool": "sql_rag",
            "status": RESULT_ERROR,
            "validated_outputs": [],
            "validated_evidence": [],
            "validated_citations": [],
            "validated_sql_rows": [],
            "limitations": [],
            "errors": [safe_error("missing_final_result_bundle", "SQL/RAG final result bundle was missing.")],
            "audit_metadata": {},
        }

    tool_result = public_tool_result(
        status=str(bundle.get("status") or RESULT_ERROR),
        validated_output={
            "validated_outputs": list(bundle.get("validated_outputs") or []),
            "validated_evidence": list(bundle.get("validated_evidence") or []),
            "validated_citations": list(bundle.get("validated_citations") or []),
            "validated_sql_rows": list(bundle.get("validated_sql_rows") or []),
        },
        limitations=list(bundle.get("limitations") or []),
        errors=list(bundle.get("errors") or []),
        audit_metadata=dict(bundle.get("audit_metadata") or {}),
    )
    final_answer_context = final_answer_context_from_bundle(bundle)
    rows = list(final_answer_context.get("validated_sql_rows") or [])
    columns = _structured_result_columns(list(bundle.get("validated_outputs") or []))
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.ADAPTER,
        event_type="sql_rag_adapter_completed",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_rag_tool",
        node_name="adapter",
        metadata={
            "sql_result_count": len([item for item in bundle.get("validated_outputs") or [] if item.get("step_type") == "sql"]),
            "structured_result_count": len(rows),
            "final_answer_context_has_structured_results": bool(rows),
            "final_answer_context_sql_row_count": len(rows),
            "final_answer_context_sql_column_count": len(columns),
            "citation_count": len(final_answer_context.get("validated_citations") or []),
            "limitation_count": len(final_answer_context.get("limitations") or []),
        },
        restricted_metadata={
            "structured_result_columns": columns,
            "structured_result_row_preview": rows[:5],
        },
        include_trace_entry=False,
    )
    return {
        "tool_result": tool_result,
        "tool_results": [tool_result],
        "final_answer_context": final_answer_context,
    }


def _structured_result_columns(step_results: list[dict]) -> list:
    columns = []
    for result in step_results:
        validated = result.get("validated_output") or {}
        columns.extend(validated.get("columns") or [])
    return columns
