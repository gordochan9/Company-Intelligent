from __future__ import annotations

import json
import re
from typing import Any

from app.graphs.final_answer_composer.state import ALLOWED_CONTEXT_STATUSES


SYSTEM_PROMPT = """You are the final answer composer for Project 3.0.

Your only job is to write a user-facing answer from the supplied final_answer_context.

Use only the original user question, final_answer_context status, answer material,
citations, limitations, and errors.

Do not retrieve data. Do not execute SQL. Do not validate permission.
Do not decide access. Do not validate evidence. Do not invent facts.
Do not invent citations. Do not create new citation IDs.
Do not expose raw SQL, raw ids, debug, internal traces, private credentials, or permission internals.
Do not perform exact arithmetic unless the exact value is already present in validated structured results.

Answer each obligation explicitly and interpret each per-step result according to its step goal.
Use validated exact values verbatim; do not round, recompute, rename, or omit them.
Include every requested count, list, customer, contact, category, and amount field present in the validated material.
When a structured result's row_count is 0, state that there are no matching records for that step goal.

Write the answer in the user's language.

Return JSON only:
{"answer_text": "string", "used_citation_ids": ["string"]}
"""

_FORBIDDEN_PUBLIC_CITATION_KEYS = {"_".join(("source", "id")), "_".join(("chunk", "id"))}
_ABSOLUTE_PATH_RE = re.compile(r"^[A-Za-z]:\\|^/|^file://", re.IGNORECASE)


class FinalAnswerContractError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(code)
        self.code = code
        self.message = message


def normalize_final_answer_context(context: Any) -> dict[str, Any]:
    if not isinstance(context, dict):
        raise FinalAnswerContractError("malformed_final_answer_context", "Final answer context was malformed.")
    status = context.get("status")
    if status not in ALLOWED_CONTEXT_STATUSES:
        raise FinalAnswerContractError("invalid_final_answer_context_status", "Final answer context status was invalid.")

    answer_material = context.get("answer_material")
    if not isinstance(answer_material, dict):
        raise FinalAnswerContractError("malformed_answer_material", "Final answer context answer material was malformed.")

    citations = context.get("citations", context.get("validated_citations", []))
    if not isinstance(citations, list):
        raise FinalAnswerContractError("malformed_citations", "Final answer context citations were malformed.")

    limitations = context.get("limitations", [])
    errors = context.get("errors", [])
    if not isinstance(limitations, list) or not isinstance(errors, list):
        raise FinalAnswerContractError("malformed_context_messages", "Final answer context messages were malformed.")

    return {
        "status": status,
        "tool": context.get("tool"),
        "answer_material": answer_material,
        "citations": citations,
        "limitations": limitations,
        "errors": errors,
    }


def build_llm_payload(user_question: str, context: dict[str, Any]) -> dict[str, Any]:
    return {
        "system_prompt": SYSTEM_PROMPT,
        "payload": {
            "user_question": user_question,
            "final_answer_context": {
                "status": context["status"],
                "answer_material": context["answer_material"],
                "citations": context["citations"],
                "limitations": context["limitations"],
                "errors": context["errors"],
            },
        },
    }


def parse_llm_json(raw_response: dict[str, Any] | str | None) -> dict[str, Any]:
    if isinstance(raw_response, str):
        try:
            parsed = json.loads(raw_response)
        except json.JSONDecodeError as exc:
            raise FinalAnswerContractError("final_answer_llm_json_unreadable", "Final answer LLM response was unreadable.") from exc
    else:
        parsed = raw_response
    if not isinstance(parsed, dict):
        raise FinalAnswerContractError("final_answer_llm_json_unreadable", "Final answer LLM response was unreadable.")
    if set(parsed) - {"answer_text", "used_citation_ids"}:
        raise FinalAnswerContractError("final_answer_llm_extra_fields", "Final answer LLM response contained unsupported fields.")
    answer_text = parsed.get("answer_text")
    if not isinstance(answer_text, str) or not answer_text.strip():
        raise FinalAnswerContractError("final_answer_missing_answer_text", "Final answer LLM response missed answer_text.")
    used = parsed.get("used_citation_ids", [])
    if not isinstance(used, list) or not all(isinstance(item, str) for item in used):
        raise FinalAnswerContractError("final_answer_invalid_citation_ids", "Final answer LLM response citation ids were invalid.")
    return {"answer_text": answer_text, "used_citation_ids": used}


def attach_citations(adapter_citations: list[dict[str, Any]], used_citation_ids: list[str]) -> tuple[list[dict[str, Any]], list[str]]:
    by_id = {item.get("citation_id"): item for item in adapter_citations if isinstance(item, dict)}
    attached: list[dict[str, Any]] = []
    unknown: list[str] = []
    for citation_id in used_citation_ids:
        citation = by_id.get(citation_id)
        if citation is None:
            unknown.append(citation_id)
            continue
        safe = _safe_public_citation(citation)
        if safe is not None:
            attached.append(safe)
    return attached, unknown


def _safe_public_citation(citation: dict[str, Any]) -> dict[str, Any] | None:
    if any(key in citation for key in _FORBIDDEN_PUBLIC_CITATION_KEYS):
        return None
    safe_path = citation.get("safe_location_path") or citation.get("safe_path")
    if isinstance(safe_path, str) and _ABSOLUTE_PATH_RE.search(safe_path):
        return None
    return dict(citation)
