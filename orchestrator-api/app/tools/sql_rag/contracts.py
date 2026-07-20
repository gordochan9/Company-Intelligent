from __future__ import annotations

import json
from typing import Any

from app.tools.sql_rag.state import (
    RESULT_ACCESS_FAILED,
    RESULT_ERROR,
    RESULT_INSUFFICIENT,
    RESULT_SUCCESS,
    RESULT_VALIDATION_FAILED,
    TERMINAL_RESULT_STATUSES,
    safe_error,
)


MAX_RUNTIME_STEPS = 8
ALLOWED_STEP_TYPES = {"rag", "sql", "final_result"}

_FORBIDDEN_FIELD_PARTS = {
    ("required", "inputs"),
    ("expected", "outputs"),
    ("raw", "sql"),
    ("table", "names"),
    ("source", "ids"),
    ("catalog", "entry", "ids"),
    ("retrieval", "query"),
    ("chunk", "ids"),
    ("join", "plan"),
    ("approved", "join", "details"),
    ("sample", "rows"),
    ("column", "profiles"),
    ("schema", "enrichment", "payload"),
    ("rag", "raw", "chunks"),
    ("sql", "result", "rows"),
}


class RuntimePlanValidationError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def require_sql_rag_input(state: dict[str, Any]) -> None:
    if state.get("access_status") != "ok":
        raise PermissionError("access_status_not_ok")
    if not state.get("trusted_user_context"):
        raise PermissionError("missing_trusted_user_context")
    if not state.get("user_permission_schema"):
        raise PermissionError("missing_user_permission_schema")
    if not state.get("user_question"):
        raise ValueError("missing_user_question")
    selection = state.get("tool_selection")
    if not isinstance(selection, dict) or selection.get("status") != "selected":
        raise ValueError("sql_rag_not_selected")
    selected = selection.get("selected_tools")
    if not isinstance(selected, list) or not any(item.get("tool") == "sql_rag" for item in selected if isinstance(item, dict)):
        raise ValueError("sql_rag_not_selected")


def parse_runtime_plan(raw_plan: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(raw_plan, str):
        try:
            parsed = json.loads(raw_plan)
        except json.JSONDecodeError as exc:
            raise RuntimePlanValidationError("runtime_plan_unreadable", "Runtime plan output was unreadable.") from exc
    else:
        parsed = raw_plan
    if not isinstance(parsed, dict):
        raise RuntimePlanValidationError("runtime_plan_unreadable", "Runtime plan output was unreadable.")
    return parsed


def validate_runtime_plan(raw_plan: dict[str, Any] | str | None) -> dict[str, Any]:
    plan = parse_runtime_plan(raw_plan)
    _reject_forbidden_fields(plan)
    if plan.get("status") != "planned":
        raise RuntimePlanValidationError("runtime_plan_invalid_status", "Runtime plan status was invalid.")
    limitations = plan.get("limitations", [])
    if not isinstance(limitations, list) or limitations:
        raise RuntimePlanValidationError(
            "runtime_plan_has_limitations", "Runtime plan must be complete and contain no planner limitations."
        )
    errors = plan.get("errors", [])
    if not isinstance(errors, list) or errors:
        raise RuntimePlanValidationError(
            "runtime_plan_has_errors", "Runtime plan must contain no planner errors."
        )
    obligations = plan.get("obligations")
    if not isinstance(obligations, list) or not obligations:
        raise RuntimePlanValidationError("runtime_plan_missing_obligations", "Runtime plan must contain obligations.")
    normalized_obligations: list[dict[str, str]] = []
    obligation_ids: set[str] = set()
    for obligation in obligations:
        if not isinstance(obligation, dict):
            raise RuntimePlanValidationError("runtime_plan_invalid_obligation", "Runtime plan obligation was invalid.")
        obligation_id = obligation.get("obligation_id")
        description = obligation.get("description")
        if not isinstance(obligation_id, str) or not obligation_id.strip() or "." in obligation_id:
            raise RuntimePlanValidationError("runtime_plan_invalid_obligation", "Runtime plan obligation_id was invalid.")
        if obligation_id in obligation_ids:
            raise RuntimePlanValidationError(
                "runtime_plan_duplicate_obligation_id", "Runtime plan obligation_id must be unique."
            )
        if not isinstance(description, str) or not description.strip():
            raise RuntimePlanValidationError("runtime_plan_invalid_obligation", "Runtime plan obligation description was invalid.")
        obligation_ids.add(obligation_id)
        normalized_obligations.append({"obligation_id": obligation_id, "description": description})

    steps = plan.get("steps")
    if not isinstance(steps, list) or not steps:
        raise RuntimePlanValidationError("runtime_plan_missing_steps", "Runtime plan must contain steps.")
    if len(steps) > MAX_RUNTIME_STEPS:
        raise RuntimePlanValidationError("runtime_plan_too_many_steps", "Runtime plan exceeded the step limit.")

    seen: set[str] = set()
    normalized_steps: list[dict[str, Any]] = []
    for index, step in enumerate(steps):
        if not isinstance(step, dict):
            raise RuntimePlanValidationError("runtime_plan_invalid_step", "Runtime plan step was invalid.")
        step_id = step.get("step_id")
        if not isinstance(step_id, str) or not step_id.strip() or "." in step_id:
            raise RuntimePlanValidationError("runtime_plan_missing_step_id", "Runtime plan step_id is required.")
        if step_id in seen:
            raise RuntimePlanValidationError("runtime_plan_duplicate_step_id", "Runtime plan step_id must be unique.")
        step_type = step.get("step_type")
        if step_type not in ALLOWED_STEP_TYPES:
            raise RuntimePlanValidationError("runtime_plan_unsupported_step_type", "Runtime plan step_type was unsupported.")
        if not isinstance(step.get("goal"), str) or not step["goal"]:
            raise RuntimePlanValidationError("runtime_plan_missing_goal", "Runtime plan step goal is required.")
        depends_on = step.get("depends_on", [])
        if depends_on is None:
            depends_on = []
        if not isinstance(depends_on, list) or not all(isinstance(item, str) for item in depends_on):
            raise RuntimePlanValidationError("runtime_plan_invalid_dependency", "Runtime plan dependency was invalid.")
        unknown = [item for item in depends_on if item not in seen]
        if unknown:
            future_ids = {item.get("step_id") for item in steps[index + 1 :] if isinstance(item, dict)}
            code = "runtime_plan_future_dependency" if any(item in future_ids for item in unknown) else "runtime_plan_unknown_dependency"
            raise RuntimePlanValidationError(code, "Runtime plan dependencies must reference earlier steps.")
        obligation_ids_value = step.get("obligation_ids", [])
        if not isinstance(obligation_ids_value, list):
            raise RuntimePlanValidationError(
                "runtime_plan_missing_obligation_ids", "Executable runtime steps must contain obligation_ids."
            )
        seen.add(step_id)
        normalized_steps.append(
            {
                "step_id": step_id,
                "step_type": step_type,
                "goal": step["goal"],
                "obligation_ids": list(obligation_ids_value),
                "depends_on": depends_on,
                "reason": str(step.get("reason") or ""),
            }
        )

    executable_steps = [step for step in normalized_steps if step["step_type"] in {"sql", "rag"}]
    final_steps = [step for step in normalized_steps if step["step_type"] == "final_result"]
    assignments: dict[str, str] = {}
    for step in executable_steps:
        assigned = step["obligation_ids"]
        if not assigned or any(not isinstance(item, str) or not item for item in assigned):
            raise RuntimePlanValidationError(
                "runtime_plan_missing_obligation_ids", "Executable runtime steps must contain obligation_ids."
            )
        for obligation_id in assigned:
            if obligation_id not in obligation_ids:
                raise RuntimePlanValidationError(
                    "runtime_plan_unknown_obligation", "Runtime step referenced an unknown obligation."
                )
            if obligation_id in assignments:
                raise RuntimePlanValidationError(
                    "runtime_plan_duplicate_obligation_assignment", "Each obligation must be assigned exactly once."
                )
            assignments[obligation_id] = step["step_id"]

    uncovered = obligation_ids - set(assignments)
    if uncovered:
        raise RuntimePlanValidationError("uncovered_obligation", "Runtime plan left obligations uncovered.")
    if not final_steps:
        raise RuntimePlanValidationError("runtime_plan_missing_final_result", "Runtime plan must contain final_result.")
    if len(final_steps) > 1:
        raise RuntimePlanValidationError(
            "runtime_plan_multiple_final_results", "Runtime plan must contain exactly one final_result."
        )
    final_step = final_steps[0]
    if final_step["obligation_ids"]:
        raise RuntimePlanValidationError(
            "runtime_plan_final_result_has_obligations", "Final result must not claim obligations."
        )
    executable_ids = {step["step_id"] for step in executable_steps}
    if set(final_step["depends_on"]) != executable_ids:
        raise RuntimePlanValidationError(
            "runtime_plan_incomplete_final_dependencies", "Final result must depend on every executable step."
        )
    return {
        "status": "planned",
        "obligations": normalized_obligations,
        "steps": normalized_steps,
        "reason": str(plan.get("reason") or ""),
    }


def public_tool_result(
    *,
    status: str,
    validated_output: dict[str, Any],
    limitations: list[dict[str, Any]],
    errors: list[dict[str, str]],
    audit_metadata: dict[str, Any],
) -> dict[str, Any]:
    if status not in TERMINAL_RESULT_STATUSES:
        status = RESULT_ERROR
        errors = [safe_error("invalid_tool_result_status", "SQL/RAG tool returned an invalid status.")]
    return {
        "tool": "sql_rag",
        "status": status,
        "validated_output": validated_output,
        "limitations": limitations,
        "errors": errors,
        "audit_metadata": audit_metadata,
    }


def final_answer_context_from_bundle(bundle: dict[str, Any]) -> dict[str, Any]:
    status = bundle.get("status")
    if status not in TERMINAL_RESULT_STATUSES:
        status = RESULT_ERROR
    return {
        "status": status,
        "tool": "sql_rag",
        "validated_evidence": list(bundle.get("validated_evidence") or []),
        "validated_sql_rows": list(bundle.get("validated_sql_rows") or []),
        "validated_citations": list(bundle.get("validated_citations") or []),
        "answer_material": dict(bundle.get("answer_material") or {}),
        "limitations": list(bundle.get("limitations") or []),
        "errors": list(bundle.get("errors") or []),
        "permission_safe_metadata": dict(bundle.get("permission_safe_metadata") or {}),
    }


def status_from_step_results(step_results: list[dict[str, Any]]) -> str:
    statuses = [item.get("status") for item in step_results]
    if not statuses:
        return RESULT_INSUFFICIENT
    if any(status == RESULT_ACCESS_FAILED for status in statuses):
        return RESULT_ACCESS_FAILED
    if any(status == RESULT_VALIDATION_FAILED for status in statuses):
        return RESULT_VALIDATION_FAILED
    if any(status == RESULT_ERROR for status in statuses):
        return RESULT_ERROR
    if any(status == RESULT_INSUFFICIENT for status in statuses):
        return RESULT_INSUFFICIENT
    return RESULT_SUCCESS if all(status == RESULT_SUCCESS for status in statuses) else RESULT_ERROR


def _reject_forbidden_fields(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            normalized = str(key).lower().replace("-", "_")
            parts = tuple(part for part in normalized.split("_") if part)
            if parts in _FORBIDDEN_FIELD_PARTS:
                raise RuntimePlanValidationError("runtime_plan_forbidden_field", "Runtime plan contained tool-internal fields.")
            _reject_forbidden_fields(child)
    elif isinstance(value, list):
        for item in value:
            _reject_forbidden_fields(item)
