from __future__ import annotations

from typing import Any

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.contracts import status_from_step_results
from app.tools.sql_rag.state import RESULT_INSUFFICIENT, RESULT_SUCCESS, SqlRagState


def final_result_bundle(state: SqlRagState) -> SqlRagState:
    existing = state.get("final_result_bundle")
    if isinstance(existing, dict):
        return {"final_result_bundle": existing}

    step_results = list(state.get("step_results") or [])
    runtime_plan = state.get("runtime_plan") or {}
    runtime_steps = {
        step.get("step_id"): step
        for step in runtime_plan.get("steps") or []
        if isinstance(step, dict) and isinstance(step.get("step_id"), str)
    }
    status = status_from_step_results(step_results)
    evidence: list[dict[str, Any]] = []
    citations: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    structured_results: list[dict[str, Any]] = []
    document_evidence: list[dict[str, Any]] = []
    limitations: list[dict[str, Any]] = list(state.get("limitations") or [])
    errors: list[dict[str, str]] = list(state.get("errors") or [])
    has_validated_output = False

    for result in step_results:
        validated = result.get("validated_output") or {}
        step = runtime_steps.get(result.get("step_id"), {})
        base = _step_material(result, step)
        result_limitations = list(result.get("limitations") or [])
        result_errors = list(result.get("errors") or [])
        limitations.extend(result_limitations)
        errors.extend(result_errors)
        base["limitations"] = result_limitations
        base["errors"] = result_errors

        if result.get("step_type") == "sql":
            columns = validated.get("columns")
            result_rows = validated.get("rows")
            row_count = validated.get("row_count")
            valid_contract = (
                isinstance(columns, list)
                and all(isinstance(column, str) for column in columns)
                and isinstance(result_rows, list)
                and all(isinstance(row, dict) for row in result_rows)
                and isinstance(row_count, int)
                and not isinstance(row_count, bool)
                and row_count >= 0
            )
            structured_results.append(
                {
                    **base,
                    "columns": list(columns) if valid_contract else [],
                    "rows": list(result_rows) if valid_contract else [],
                    "row_count": row_count if valid_contract else 0,
                }
            )
            if valid_contract:
                rows.extend(result_rows)
                has_validated_output |= result.get("status") == RESULT_SUCCESS
        elif result.get("step_type") == "rag":
            step_evidence = validated.get("validated_evidence") or []
            step_citations = validated.get("validated_citations") or []
            if not isinstance(step_evidence, list):
                step_evidence = []
            if not isinstance(step_citations, list):
                step_citations = []
            document_evidence.append(
                {
                    **base,
                    "validated_evidence": list(step_evidence),
                    "validated_citations": list(step_citations),
                }
            )
            evidence.extend(step_evidence)
            citations.extend(step_citations)
            has_validated_output |= result.get("status") == RESULT_SUCCESS and bool(step_evidence)

    if status == RESULT_SUCCESS and not has_validated_output:
        status = RESULT_INSUFFICIENT
        errors.append({"code": "no_validated_outputs", "message": "SQL/RAG tool produced no validated outputs."})

    answer_material = {
        "obligations": _safe_obligations(runtime_plan.get("obligations") or []),
        "structured_results": structured_results,
        "document_evidence": document_evidence,
    }
    bundle = {
        "tool": "sql_rag",
        "status": status,
        "validated_outputs": step_results,
        "validated_evidence": evidence,
        "validated_citations": citations,
        "validated_sql_rows": rows,
        "answer_material": answer_material,
        "limitations": limitations,
        "errors": _dedupe_errors(errors),
        "permission_safe_metadata": {
            "runtime_plan_status": state.get("runtime_plan_status"),
            "executed_step_ids": list(state.get("completed_steps") or []),
        },
        "audit_metadata": {
            "tool": "sql_rag",
            "runtime_plan_status": state.get("runtime_plan_status"),
            "runtime_step_count": len(runtime_plan.get("steps") or []),
            "executed_step_ids": list(state.get("completed_steps") or []),
            "child_workflow_statuses": [item.get("status") for item in step_results],
            "final_bundle_status": status,
        },
    }
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.TOOL,
        event_type="sql_rag_final_result_bundle_built",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_rag_tool",
        node_name="final_result_bundle",
        metadata={
            "sql_result_count": len(structured_results),
            "structured_result_count": len(structured_results),
            "final_answer_context_has_structured_results": bool(structured_results),
            "final_answer_context_sql_row_count": sum(item["row_count"] for item in structured_results),
            "final_answer_context_sql_column_count": len(_structured_result_columns(step_results)),
            "citation_count": len(citations),
            "limitation_count": len(limitations),
        },
        restricted_metadata={
            "structured_result_columns": _structured_result_columns(step_results),
            "structured_result_row_preview": rows[:5],
        },
        include_trace_entry=False,
    )
    return {"final_result_bundle": bundle}


def _step_material(result: dict[str, Any], step: dict[str, Any]) -> dict[str, Any]:
    return {
        "step_id": str(result.get("step_id") or step.get("step_id") or ""),
        "goal": str(step.get("goal") or ""),
        "obligation_ids": [item for item in step.get("obligation_ids") or [] if isinstance(item, str)],
        "step_type": str(result.get("step_type") or step.get("step_type") or ""),
        "status": str(result.get("status") or ""),
    }


def _safe_obligations(obligations: list[Any]) -> list[dict[str, str]]:
    return [
        {"obligation_id": item["obligation_id"], "description": item["description"]}
        for item in obligations
        if isinstance(item, dict)
        and isinstance(item.get("obligation_id"), str)
        and isinstance(item.get("description"), str)
    ]


def _dedupe_errors(errors: list[dict[str, str]]) -> list[dict[str, str]]:
    seen: set[tuple[str, str]] = set()
    unique: list[dict[str, str]] = []
    for error in errors:
        key = (str(error.get("code") or ""), str(error.get("message") or ""))
        if key in seen:
            continue
        seen.add(key)
        unique.append(error)
    return unique


def _structured_result_columns(step_results: list[dict[str, Any]]) -> list[Any]:
    columns: list[Any] = []
    for result in step_results:
        validated = result.get("validated_output") or {}
        columns.extend(validated.get("columns") or [])
    return columns
