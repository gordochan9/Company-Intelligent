from __future__ import annotations

from typing import Any

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.services.audit_trace import emit_audit_event
from app.tools.sql_rag.sql.services.llm import SqlModelUnavailable, call_sql_model, parse_candidate
from app.tools.sql_rag.sql.services.validation import count_unbound_sql_parameters, sql_hash
from app.tools.sql_rag.sql.state import SqlState, fail_state


_SQL_GENERATION_SYSTEM_PROMPT = """Return JSON only.
Generate exactly one non-empty read-only PostgreSQL query statement for the selected structured resources.
The SQL must be fully executable exactly as emitted and must not depend on later parameter binding.
Do not emit unbound parameter placeholders such as $1, :name, %s, %(name)s, or a parameter-style question mark.
This restriction does not prohibit valid PostgreSQL JSONB operators such as ?, ?|, and ?&.
Do not return multiple semicolon-separated statements.
Return exactly this shape: {"sql":"SELECT ..."}
Use only runtime_relation_name values and real column headers in selected_resources.tables.
Never use INSERT, UPDATE, DELETE, MERGE, ALTER, DROP, CREATE, TRUNCATE, COPY, function calls with side effects, comments, raw file paths, secrets, or unrestricted schemas.
Base the SQL on the complete sql_query_intent and must not omit any intent requirement that can be represented with approved selected_resources.
Use WHERE for conditions that define the row population shared by all requested outputs.
Use aggregate FILTER or CASE WHEN for conditions that apply only to individual metrics while other metrics require the broader population.
Do not put a metric-specific condition in WHERE when doing so would remove rows required by another metric or its denominator.
Rates, totals, averages, ranking, and top-N results must be calculated deterministically in SQL.
Use NULLIF or an equivalent safe denominator guard where division by zero is possible.
Do not return NULL for a requested result when its required inputs are available.
Use validated dependency values only through the complete sql_query_intent, either as typed SQL literals or by retrieving them from selected approved tables or subqueries.
Preserve zero-subset groups when comparison requires the full group population.
Use aggregate metrics' validated output_name values as their stable aliases.
For row/list queries, select the logical output columns required by the step goal, obligations, and validated intent.
Treat selected_resources.joins as optional verified hints and use them when helpful.
When no suitable hint exists, construct a reasonable join only from the selected permission-filtered tables, their real headers, and the complete semantic intent.
Use selected_resources.source_columns for the proposed output/filter columns; approved join endpoints may be added safely by the selector.
Never use a relation or column outside selected_resources.
"""

_EMPTY_RETRY_INSTRUCTION = (
    "\nThe previous output was empty. Return JSON only with exactly one non-empty read-only PostgreSQL query statement in the sql field."
)


def generate_candidate_sql(state: SqlState) -> SqlState:
    payload = _sql_generation_payload(state)
    attempts = 1
    empty_first_attempt = False
    try:
        raw_candidate = call_sql_model(payload)
        candidate = parse_candidate(raw_candidate)
        if not candidate.strip():
            empty_first_attempt = True
            attempts = 2
            retry_payload = {**payload, "system_prompt": payload["system_prompt"] + _EMPTY_RETRY_INSTRUCTION}
            raw_candidate = call_sql_model(retry_payload)
            candidate = parse_candidate(raw_candidate)
    except SqlModelUnavailable:
        return fail_state("generate_candidate_sql", "sql_generation_model_unavailable", "SQL generation model is unavailable.")
    except ValueError as exc:
        return fail_state("generate_candidate_sql", str(exc), "Candidate SQL is invalid.")
    candidate = candidate.strip()
    if not candidate:
        return fail_state("generate_candidate_sql", "empty_candidate_query", "Candidate SQL is empty.")
    selected = state.get("selected_resources") or {}
    lowered = candidate.casefold()
    emit_audit_event(
        request_id=state.get("request_id"),
        trace_id=state.get("trace_id"),
        event_category=AuditEventCategory.SQL,
        event_type="candidate_sql_generated",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="sql_subgraph",
        node_name="generate_candidate_sql",
        metadata={
            "sql_hash": sql_hash(candidate),
            "operation_type": "select" if lowered.lstrip().startswith("select") else "with",
            "parameter_count": count_unbound_sql_parameters(candidate),
            "has_where_clause": " where " in f" {lowered} ",
            "has_group_by": " group by " in f" {lowered} ",
            "has_order_by": " order by " in f" {lowered} ",
            "has_limit": " limit " in f" {lowered} ",
            "selected_table_count": len(selected.get("tables") or []),
            "selected_column_count": len(selected.get("columns") or []),
            "generation_attempt_count": attempts,
            "empty_first_attempt": empty_first_attempt,
            "unbound_parameter_regeneration_count": state.get("unbound_parameter_regeneration_count", 0),
        },
        restricted_metadata={"candidate_sql": candidate},
        include_trace_entry=False,
    )
    return {"candidate_sql": candidate}


def _sql_generation_payload(state: SqlState) -> dict[str, Any]:
    regeneration_count = state.get("unbound_parameter_regeneration_count", 0)
    payload: dict[str, Any] = {
        "sql_query_intent": state.get("sql_query_intent", {}),
        "selected_resources": state.get("selected_resources", {}),
    }
    if regeneration_count:
        payload["validation_feedback_code"] = "unbound_sql_parameter"
    return {
        "system_prompt": _SQL_GENERATION_SYSTEM_PROMPT,
        "payload": payload,
    }
