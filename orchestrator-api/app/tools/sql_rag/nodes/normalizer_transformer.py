from __future__ import annotations

from typing import Any

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.state import (
    RESULT_SUCCESS,
    RESULT_VALIDATION_FAILED,
    TERMINAL_RESULT_STATUSES,
    SqlRagState,
)


def normalizer_transformer(state: SqlRagState) -> SqlRagState:
    step = state.get("current_step")
    child = state.get("current_child_result")
    if not isinstance(step, dict) or not isinstance(child, dict):
        return _malformed_failure(state, step)

    result_key = "rag_result" if step.get("step_type") == "rag" else "sql_result"
    result = child.get(result_key)
    if not isinstance(result, dict) or result.get("status") not in TERMINAL_RESULT_STATUSES:
        return _malformed_failure(state, step)

    normalized = {
        "step_id": result.get("step_id") or step.get("step_id"),
        "step_type": result.get("step_type") or step.get("step_type"),
        "status": result["status"],
        "validated_output": dict(result.get("validated_output") or {}),
        "limitations": list(result.get("limitations") or []),
        "errors": list(result.get("errors") or []),
        "audit_metadata": dict(result.get("audit_metadata") or {}),
    }
    step_results = list(state.get("step_results") or []) + [normalized]
    dependency_context = dict(state.get("dependency_context") or {})
    if normalized["status"] == RESULT_SUCCESS:
        completed_steps = list(state.get("completed_steps") or []) + [str(step["step_id"])]
        dependency_context[str(step["step_id"])] = {
            "validated_output": dict(normalized["validated_output"]),
        }
        if step.get("step_type") == "rag":
            covered_obligation_ids = list(state.get("covered_obligation_ids") or [])
            covered_obligation_ids.extend(
                obligation_id
                for obligation_id in step.get("obligation_ids") or []
                if obligation_id not in covered_obligation_ids
            )
            _audit_progress(
                state, step, True, completed_steps=completed_steps, covered_obligation_ids=covered_obligation_ids
            )
            return {
                "step_results": step_results,
                "completed_steps": completed_steps,
                "covered_obligation_ids": covered_obligation_ids,
                "dependency_context": dependency_context,
                "current_step": None,
                "current_child_result": None,
            }
        _audit_progress(
            state,
            step,
            True,
            completed_steps=completed_steps,
            event_type="normalizer_completed",
        )
        return {
            "step_results": step_results,
            "completed_steps": completed_steps,
            "dependency_context": dependency_context,
            "current_step": None,
            "current_child_result": None,
        }
    _audit_progress(state, step, False)
    return _failure_progress(state, step_results, dependency_context, normalized)


def _malformed_failure(state: SqlRagState, step: Any) -> SqlRagState:
    error = {"code": "malformed_child_output", "message": "Child workflow output was malformed."}
    normalized = {
        "step_id": step.get("step_id") if isinstance(step, dict) else None,
        "step_type": step.get("step_type") if isinstance(step, dict) else None,
        "status": RESULT_VALIDATION_FAILED,
        "validated_output": {},
        "limitations": [],
        "errors": [error],
        "audit_metadata": {},
    }
    step_results = list(state.get("step_results") or []) + [normalized]
    _audit_progress(state, step if isinstance(step, dict) else {}, False)
    return _failure_progress(state, step_results, dict(state.get("dependency_context") or {}), normalized)


def _failure_progress(
    state: SqlRagState,
    step_results: list[dict[str, Any]],
    dependency_context: dict[str, Any],
    normalized: dict[str, Any],
) -> SqlRagState:
    return {
        "step_results": step_results,
        "dependency_context": dependency_context,
        "current_step": None,
        "current_child_result": None,
        "errors": list(state.get("errors") or []) + list(normalized["errors"]),
    }


def _audit_progress(
    state: SqlRagState,
    step: dict[str, Any],
    succeeded: bool,
    *,
    completed_steps: list[str] | None = None,
    covered_obligation_ids: list[str] | None = None,
    event_type: str | None = None,
) -> None:
    completed = list(completed_steps if completed_steps is not None else state.get("completed_steps") or [])
    covered = list(
        covered_obligation_ids if covered_obligation_ids is not None else state.get("covered_obligation_ids") or []
    )
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.TOOL,
        event_type=event_type or ("runtime_step_completed" if succeeded else "runtime_step_failed"),
        status=AuditEventStatus.SUCCEEDED if succeeded else AuditEventStatus.VALIDATION_FAILED,
        workflow_name="sql_rag_tool",
        node_name="normalizer_transformer",
        metadata={
            "completed_step_count": len(completed),
            "covered_obligation_count": len(covered),
            "normalization_status": "succeeded" if succeeded else "failed",
        },
        restricted_metadata={
            "step_id": step.get("step_id"),
            "completed_step_ids": completed,
            "covered_obligation_ids": covered,
        },
        include_trace_entry=False,
    )
