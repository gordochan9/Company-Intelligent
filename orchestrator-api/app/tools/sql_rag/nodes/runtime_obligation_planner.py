from __future__ import annotations

from typing import Any, Callable

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.contracts import RuntimePlanValidationError, parse_runtime_plan
from app.tools.sql_rag.state import STATUS_PLANNED, SqlRagState, fail_state


_RuntimePlanModel = Callable[[dict[str, Any]], dict[str, Any] | str]
_runtime_obligation_planner_model: _RuntimePlanModel | None = None
MAX_CONVERSATION_MESSAGES = 12
MAX_CONVERSATION_CONTENT_CHARS = 2000
_RUNTIME_PLAN_SYSTEM_PROMPT = """Return JSON only.
Plan the internal SQL/RAG workflow after backend identity and permission enforcement.
Read conversation_history to resolve follow-up references in the user question before extracting answer obligations.
Return exactly this top-level shape:
{"status":"planned","obligations":[{"obligation_id":"o1","description":"..."}],"steps":[{"step_id":"step_1","step_type":"sql|rag|final_result","goal":"...","obligation_ids":["o1"],"depends_on":[],"reason":"..."}],"reason":""}
Return status planned only when obligations contains at least one item.
For any question with explicit answer obligations, return planned and delegate data or evidence sufficiency to the child steps. Missing schema or unseen data at this planning stage is not a reason to return another status.
Extract every explicit answer obligation and assign each obligation_id to exactly one executable sql or rag step.
Every obligation description must be self-contained.
One executable step may cover multiple compatible obligations, but separate count and list requirements must remain separate steps.
Choose sql or rag semantically. Do not use or request keyword routing.
Use sql for exact counts, totals, rankings, filters, arithmetic, and structured data.
Use rag for document, policy, citation, and narrative evidence.
Each executable step goal must preserve the subject, filters, time scope, comparison or ranking requirement, and requested outputs needed for that step.
Do not introduce an arithmetic operator or formula that the user did not state. Preserve a semantic result request such as a net or combined result without inventing subtraction or addition for the child step.
When later wording refers back to a metric already introduced in the same question, preserve that metric's definition. Do not invent a parallel calculation variant unless the question explicitly contrasts the variants.
Each step must be executable using only its assigned obligation descriptions, complete validated outputs from declared dependencies, and trusted permission context.
Do not predict child output names or select named dependency inputs.
Add exactly one final_result step that depends directly on every executable step and has no obligation_ids.
Before returning the plan, verify that every explicit requested output is represented by an obligation and assigned to an executable step.
Do not include raw SQL, table names, source IDs, catalog IDs, joins, chunks, samples, profiles, result rows, identity, permission decisions, or final answer text.
"""


def set_runtime_obligation_planner_model(model: _RuntimePlanModel | None) -> None:
    global _runtime_obligation_planner_model
    _runtime_obligation_planner_model = model


def runtime_obligation_planner(state: SqlRagState) -> SqlRagState:
    if _runtime_obligation_planner_model is None:
        return fail_state(
            "runtime_obligation_planner",
            "runtime_plan_model_unavailable",
            "Runtime plan model is unavailable.",
            status="planning_failed",
        )
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.PLANNER,
        event_type="runtime_plan_llm_called",
        status=AuditEventStatus.STARTED,
        workflow_name="sql_rag_tool",
        node_name="runtime_obligation_planner",
        metadata={"planning_status": "started"},
        include_trace_entry=False,
    )
    try:
        plan = parse_runtime_plan(_runtime_obligation_planner_model(_runtime_plan_payload(state)))
    except RuntimePlanValidationError as exc:
        return fail_state("runtime_obligation_planner", exc.code, exc.message, status="planning_failed")
    except Exception:
        return fail_state(
            "runtime_obligation_planner",
            "runtime_plan_model_error",
            "Runtime plan model call failed.",
            status="planning_failed",
        )

    if plan.get("status") != STATUS_PLANNED:
        return fail_state(
            "runtime_obligation_planner",
            "runtime_plan_invalid_status",
            "Runtime plan status was invalid.",
            status="planning_failed",
        )
    obligations = plan.get("obligations")
    if not isinstance(obligations, list) or not obligations:
        return fail_state(
            "runtime_obligation_planner",
            "runtime_plan_missing_obligations",
            "Runtime plan must contain obligations.",
            status="planning_failed",
        )
    steps = plan.get("steps") if isinstance(plan.get("steps"), list) else []
    executable = [step for step in steps if isinstance(step, dict) and step.get("step_type") in {"sql", "rag"}]
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.PLANNER,
        event_type="runtime_plan_parsed",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_rag_tool",
        node_name="runtime_obligation_planner",
        metadata={
            "obligation_count": len(obligations),
            "executable_step_count": len(executable),
            "sql_step_count": len([step for step in executable if step.get("step_type") == "sql"]),
            "rag_step_count": len([step for step in executable if step.get("step_type") == "rag"]),
            "dependency_count": sum(
                len(step.get("depends_on")) if isinstance(step.get("depends_on"), list) else 0
                for step in executable
            ),
            "planning_status": "parsed",
        },
        include_trace_entry=False,
    )
    return {"runtime_plan": plan, "runtime_plan_status": STATUS_PLANNED}


def _runtime_plan_payload(state: SqlRagState) -> dict[str, Any]:
    selection = state.get("tool_selection") or {}
    selected_sql_rag = [
        item
        for item in selection.get("selected_tools", [])
        if isinstance(item, dict) and item.get("tool") == "sql_rag"
    ]
    return {
        "system_prompt": _RUNTIME_PLAN_SYSTEM_PROMPT,
        "payload": {
            "user_question": state.get("user_question"),
            "conversation_history": _conversation_history_from_messages(state.get("messages")),
            "tool_selection_reason": selection.get("reason") or "",
            "selected_sql_rag_reason": selected_sql_rag[0].get("reason") if selected_sql_rag else "",
        },
    }


def _conversation_history_from_messages(messages: list[Any] | None) -> list[dict[str, str]]:
    history: list[dict[str, str]] = []
    for message in list(messages or [])[-MAX_CONVERSATION_MESSAGES:]:
        if not isinstance(message, dict):
            continue
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = _message_text(message.get("content"))
        if content:
            history.append({"role": role, "content": content[:MAX_CONVERSATION_CONTENT_CHARS]})
    return history


def _message_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            parts.append(item["text"])
    return "\n".join(parts).strip()
