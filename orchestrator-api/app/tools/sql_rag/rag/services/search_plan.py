from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any


_RagPlanModel = Callable[[dict[str, Any]], dict[str, Any] | str]
_rag_plan_model: _RagPlanModel | None = None
_RAG_SEARCH_SYSTEM_PROMPT = """Return JSON only.
You are selecting permitted RAG documents for a RAG child workflow.
Use only document_key values that appear in the provided filtered_rag_schema.
Return exactly this shape:
{"document_keys":["doc_1"],"query_terms":["term"],"reason":""}
Choose document_keys by matching the user question and step goal to document titles, safe paths, summaries, keywords, headers, and safe row samples.
Use short query_terms that appear relevant to the requested evidence.
Do not invent document keys, source IDs, chunk IDs, raw chunks, file paths, permission data, citations, or answer text.
"""


class RagPlanModelUnavailable(RuntimeError):
    pass


def set_rag_plan_model(model: _RagPlanModel | None) -> None:
    global _rag_plan_model
    _rag_plan_model = model


def build_search_plan_payload(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "system_prompt": _RAG_SEARCH_SYSTEM_PROMPT,
        "payload": {
            "rag_question": state.get("rag_question", ""),
            "step_goal": state.get("step_goal", ""),
            "dependency_context": state.get("dependency_context", {}),
            "filtered_rag_schema": state.get("llm_readable_rag_schema", {}),
        },
    }


def call_rag_plan_model(payload: dict[str, Any]) -> dict[str, Any] | str:
    if _rag_plan_model is None:
        raise RagPlanModelUnavailable("No RAG search plan model is configured.")
    try:
        return _rag_plan_model(payload)
    except Exception as exc:
        raise RagPlanModelUnavailable("RAG search plan model call failed.") from exc


def parse_search_plan(raw_plan: dict[str, Any] | str | None) -> dict[str, Any]:
    try:
        plan = json.loads(raw_plan) if isinstance(raw_plan, str) else raw_plan
    except json.JSONDecodeError as exc:
        raise ValueError("unreadable_rag_search_plan") from exc
    if not isinstance(plan, dict):
        raise ValueError("unreadable_rag_search_plan")
    if "document_keys" not in plan or not isinstance(plan["document_keys"], list):
        raise ValueError("invalid_rag_search_plan")
    if any(not isinstance(item, str) for item in plan["document_keys"]):
        raise ValueError("invalid_rag_search_plan")
    query_terms = plan.get("query_terms", [])
    if not isinstance(query_terms, list) or any(not isinstance(item, str) for item in query_terms):
        raise ValueError("invalid_rag_search_plan")
    return {
        "document_keys": plan["document_keys"],
        "query_terms": query_terms,
        "reason": str(plan.get("reason") or ""),
    }
