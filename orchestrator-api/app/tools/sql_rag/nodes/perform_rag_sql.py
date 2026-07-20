from __future__ import annotations

from app.tools.sql_rag.rag.agent import run_rag_workflow
from app.tools.sql_rag.sql.agent import run_sql_workflow
from app.tools.sql_rag.state import SqlRagState, fail_state


def perform_rag_sql(state: SqlRagState) -> SqlRagState:
    step = state.get("current_step")
    if not isinstance(step, dict):
        return fail_state("perform_rag_sql", "missing_current_step", "Runtime step was missing.", status="blocked")

    step_type = step.get("step_type")
    if step_type not in {"rag", "sql"}:
        return fail_state("perform_rag_sql", "unsupported_runtime_step", "Runtime step was unsupported.", status="invalid_plan")
    step_goal = step.get("goal")
    if not isinstance(step_goal, str) or not step_goal.strip():
        return fail_state(
            "perform_rag_sql",
            "invalid_runtime_step_goal",
            "Runtime step goal was missing or invalid.",
            status="invalid_plan",
        )

    try:
        dependency_context = _required_dependency_context(state, step)
    except ValueError:
        return fail_state(
            "perform_rag_sql",
            "missing_dependency_context",
            "Dependency context was unavailable.",
            status="blocked",
        )

    child_state = {
        "request_id": state.get("request_id"),
        "trace_id": state.get("trace_id"),
        "step_id": step.get("step_id"),
        "step_goal": step_goal,
        "obligations": _step_obligations(state, step),
        "trusted_user_context": state.get("trusted_user_context"),
        "user_permission_schema": state.get("user_permission_schema"),
        "dependency_context": dependency_context,
        "trace": state.get("trace") or [],
    }
    if step_type == "rag":
        result = run_rag_workflow({**child_state, "rag_question": step_goal})
    else:
        result = run_sql_workflow({**child_state, "sql_question": step_goal})
    return {"current_child_result": dict(result)}


def _step_obligations(state: SqlRagState, step: dict) -> list[dict]:
    requested = set(step.get("obligation_ids") or [])
    return [
        dict(obligation)
        for obligation in (state.get("runtime_plan") or {}).get("obligations", [])
        if isinstance(obligation, dict) and obligation.get("obligation_id") in requested
    ]


def _required_dependency_context(state: SqlRagState, step: dict) -> dict:
    available = state.get("dependency_context") or {}
    completed = set(state.get("completed_steps") or [])
    dependencies = list(step.get("depends_on") or [])
    scoped: dict = {}
    for producer_id in dependencies:
        producer_context = available.get(producer_id)
        if (
            producer_id not in completed
            or not isinstance(producer_context, dict)
            or "validated_output" not in producer_context
        ):
            raise ValueError("missing_dependency_context")
        scoped[producer_id] = dict(producer_context)
    return scoped
