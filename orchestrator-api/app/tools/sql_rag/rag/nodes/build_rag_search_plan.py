from __future__ import annotations

from app.tools.sql_rag.rag.services.search_plan import (
    RagPlanModelUnavailable,
    build_search_plan_payload,
    call_rag_plan_model,
    parse_search_plan,
)
from app.tools.sql_rag.rag.state import RagState, fail_state


def build_rag_search_plan(state: RagState) -> RagState:
    payload = build_search_plan_payload(state)
    try:
        raw_plan = call_rag_plan_model(payload)
        plan = parse_search_plan(raw_plan)
    except RagPlanModelUnavailable:
        return fail_state("build_rag_search_plan", "rag_search_model_unavailable", "RAG search planning model is unavailable.")
    except ValueError as exc:
        return fail_state("build_rag_search_plan", str(exc), "RAG search plan is invalid.")
    return {"raw_rag_search_plan": raw_plan, "rag_search_plan": plan}
