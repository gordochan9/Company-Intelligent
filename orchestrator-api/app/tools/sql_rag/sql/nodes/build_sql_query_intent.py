from __future__ import annotations

from typing import Any

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.sql.services.llm import SqlModelUnavailable, call_intent_model, parse_intent
from app.tools.sql_rag.sql.state import SqlState, fail_state


_SQL_INTENT_SYSTEM_PROMPT = """Return JSON only.
Return one JSON object that freely describes the semantic SQL intent needed to satisfy the step goal.
Use any JSON fields and nested structures that help express every calculation, scope, filter, metric, grouping, ranking, relationship, and requested output.
Preserve every validated dependency value needed by the current calculation exactly, including its precision, scope, entity, semantic meaning, and relationship to the requested calculation.
Do not describe an available applicable dependency value as unknown or missing.
Do not select tables, columns, joins, or logical resource keys.
Do not calculate the requested answer.
Do not produce candidate SQL.
"""


def build_sql_query_intent(state: SqlState) -> SqlState:
    payload = _sql_intent_payload(state)
    try:
        intent = parse_intent(call_intent_model(payload))
    except SqlModelUnavailable:
        return fail_state("build_sql_query_intent", "sql_intent_model_unavailable", "SQL intent model is unavailable.")
    except ValueError:
        return fail_state("build_sql_query_intent", "invalid_sql_intent", "SQL query intent is invalid.")
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="sql_query_intent_built",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="build_sql_query_intent",
        metadata={
            "intent_status": "built",
            "top_level_field_count": len(intent),
            "semantic_content_present": True,
        },
        include_trace_entry=False,
    )
    return {"sql_query_intent": intent}


def _sql_intent_payload(state: SqlState) -> dict[str, Any]:
    return {
        "system_prompt": _SQL_INTENT_SYSTEM_PROMPT,
        "payload": {
            "sql_question": state.get("sql_question", ""),
            "step_goal": state.get("step_goal", ""),
            "obligations": state.get("obligations", []),
            "dependency_context": state.get("dependency_context", {}),
        },
    }
