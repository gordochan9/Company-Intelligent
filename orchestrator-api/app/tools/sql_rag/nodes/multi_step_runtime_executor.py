from __future__ import annotations

from typing import Any

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.contracts import RuntimePlanValidationError, validate_runtime_plan
from app.tools.sql_rag.state import (
    RESULT_SUCCESS,
    STATUS_BLOCKED,
    STATUS_COMPLETE,
    STATUS_INVALID_PLAN,
    STATUS_RUNNING,
    SqlRagState,
    fail_state,
)


def multi_step_runtime_executor(state: SqlRagState) -> SqlRagState:
    if state.get("runtime_plan_status") in {"blocked", "invalid_plan", "error"}:
        return {}
    try:
        plan = validate_runtime_plan(state.get("runtime_plan"))
    except RuntimePlanValidationError as exc:
        emit_audit_event(
            request_id=state.get("request_id"),
            trace_id=state.get("trace_id"),
            event_category=AuditEventCategory.TOOL,
            event_type="runtime_plan_validation_failed",
            status=AuditEventStatus.VALIDATION_FAILED,
            workflow_name="sql_rag_tool",
            node_name="multi_step_runtime_executor",
            metadata={"failure_code": exc.code},
            include_trace_entry=False,
        )
        return fail_state("multi_step_runtime_executor", exc.code, exc.message, status=STATUS_INVALID_PLAN)
    if state.get("runtime_plan_status") == "planned":
        emit_audit_event(
            request_id=state.get("request_id"),
            trace_id=state.get("trace_id"),
            event_category=AuditEventCategory.TOOL,
            event_type="runtime_plan_ready",
            status=AuditEventStatus.SUCCEEDED,
            workflow_name="sql_rag_tool",
            node_name="multi_step_runtime_executor",
            metadata={
                "obligation_count": len(plan["obligations"]),
                "step_count": len(plan["steps"]),
                "runtime_plan_status": "planned",
            },
            restricted_metadata={
                "obligation_ids": [item["obligation_id"] for item in plan["obligations"]],
                "steps": [
                    {
                        "step_id": step["step_id"],
                        "step_type": step["step_type"],
                        "obligation_ids": step["obligation_ids"],
                        "depends_on": step["depends_on"],
                    }
                    for step in plan["steps"]
                ],
            },
            include_trace_entry=False,
        )
    child_failure = _child_failure_patch(state)
    if child_failure is not None:
        return {**child_failure, "runtime_plan": plan}
    covered_obligation_ids = list(state.get("covered_obligation_ids") or [])
    coverage_patch = _sql_coverage_patch(state, plan, covered_obligation_ids)
    if coverage_patch.get("runtime_plan_status") == STATUS_INVALID_PLAN:
        return {**coverage_patch, "runtime_plan": plan}
    covered_obligation_ids = list(coverage_patch.get("covered_obligation_ids") or covered_obligation_ids)
    patch = _next_step_patch(
        plan,
        list(state.get("completed_steps") or []),
        covered_obligation_ids,
    )
    return {**patch, **coverage_patch, "runtime_plan": plan}


def _child_failure_patch(state: SqlRagState) -> SqlRagState | None:
    step_results = list(state.get("step_results") or [])
    if not step_results or step_results[-1].get("status") == RESULT_SUCCESS:
        return None
    errors = list(step_results[-1].get("errors") or [])
    failure_code = errors[0].get("code") if errors and isinstance(errors[0], dict) else None
    return {
        "runtime_plan_status": STATUS_BLOCKED,
        "current_step": None,
        "current_child_result": None,
        "failed_node": "multi_step_runtime_executor",
        "failure_code": failure_code or "child_workflow_failed",
    }


def _sql_coverage_patch(
    state: SqlRagState,
    plan: dict[str, Any],
    covered_obligation_ids: list[str],
) -> SqlRagState:
    step_results = list(state.get("step_results") or [])
    if not step_results:
        return {}
    result = step_results[-1]
    if result.get("status") != RESULT_SUCCESS or result.get("step_type") != "sql":
        return {}
    step = next(
        (item for item in plan["steps"] if item.get("step_id") == result.get("step_id") and item.get("step_type") == "sql"),
        None,
    )
    gate_reason = "missing_runtime_step" if step is None else _sql_output_gate_reason(result.get("validated_output"))
    assigned_obligation_ids = list(step.get("obligation_ids") or []) if step is not None else []
    if gate_reason is not None:
        _audit_sql_coverage(
            state,
            result,
            assigned_obligation_ids,
            covered_obligation_ids,
            succeeded=False,
            gate_reason=gate_reason,
        )
        return fail_state(
            "multi_step_runtime_executor",
            "uncovered_obligation",
            "SQL step output did not pass runtime coverage validation.",
            status=STATUS_INVALID_PLAN,
        )
    updated_coverage = list(covered_obligation_ids)
    updated_coverage.extend(
        obligation_id for obligation_id in assigned_obligation_ids if obligation_id not in updated_coverage
    )
    _audit_sql_coverage(
        state,
        result,
        assigned_obligation_ids,
        updated_coverage,
        succeeded=True,
        gate_reason="passed",
    )
    return {"covered_obligation_ids": updated_coverage}


def _sql_output_gate_reason(validated_output: object) -> str | None:
    if not isinstance(validated_output, dict):
        return "invalid_validated_output"
    if not all(key in validated_output for key in ("columns", "rows", "row_count")):
        return "missing_output_contract_key"
    columns = validated_output["columns"]
    rows = validated_output["rows"]
    row_count = validated_output["row_count"]
    if not isinstance(columns, list) or not columns or not all(
        isinstance(column, str) and bool(column) for column in columns
    ):
        return "invalid_columns"
    if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
        return "invalid_rows"
    if not isinstance(row_count, int) or isinstance(row_count, bool) or row_count < 0:
        return "invalid_row_count"
    if row_count > 0 and any(not any(row.get(column) is not None for row in rows) for column in columns):
        return "all_null_column"
    return None


def _audit_sql_coverage(
    state: SqlRagState,
    result: dict[str, Any],
    assigned_obligation_ids: list[str],
    covered_obligation_ids: list[str],
    *,
    succeeded: bool,
    gate_reason: str,
) -> None:
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.TOOL,
        event_type="runtime_step_completed" if succeeded else "runtime_step_failed",
        status=AuditEventStatus.SUCCEEDED if succeeded else AuditEventStatus.VALIDATION_FAILED,
        workflow_name="sql_rag_tool",
        node_name="multi_step_runtime_executor",
        metadata={
            "completed_step_count": len(state.get("completed_steps") or []),
            "covered_obligation_count": len(covered_obligation_ids),
            "coverage_status": "succeeded" if succeeded else "failed",
            "failure_code": None if succeeded else "uncovered_obligation",
        },
        restricted_metadata={
            "step_id": result.get("step_id"),
            "assigned_obligation_ids": assigned_obligation_ids,
            "covered_obligation_ids": covered_obligation_ids,
            "gate_reason": gate_reason,
        },
        include_trace_entry=False,
    )


def _next_step_patch(
    plan: dict,
    completed_steps: list[str],
    covered_obligation_ids: list[str],
) -> SqlRagState:
    completed = set(completed_steps)
    executable_steps = [step for step in plan["steps"] if step["step_type"] in {"sql", "rag"}]
    for step in executable_steps:
        if step["step_id"] in completed:
            continue
        if all(item in completed for item in step.get("depends_on", [])):
            return {"runtime_plan_status": STATUS_RUNNING, "current_step": dict(step)}
    incomplete = {step["step_id"] for step in executable_steps} - completed
    if incomplete:
        return fail_state(
            "multi_step_runtime_executor",
            "runtime_plan_blocked",
            "Runtime plan could not make progress.",
            status="blocked",
        )
    required = {obligation["obligation_id"] for obligation in plan["obligations"]}
    if set(covered_obligation_ids) != required:
        return fail_state(
            "multi_step_runtime_executor",
            "uncovered_obligation",
            "Runtime plan completed without covering every obligation.",
            status=STATUS_INVALID_PLAN,
        )
    return {"runtime_plan_status": STATUS_COMPLETE, "current_step": None}
