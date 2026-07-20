from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any

from app.graphs.final_answer_composer.graph import run_final_answer_composer
from app.graphs.final_answer_composer.nodes.call_final_answer_llm import set_final_answer_model
from app.graphs.tool_selection_planner.graph import run_tool_selection_planner
from app.services.llm_provider import deepseek_json, deepseek_payload_call, deepseek_tool_selection
from app.services.tool_selection_planner import FORBIDDEN_OUTPUT_FIELDS, set_tool_selection_model


SECRET_RE = re.compile(r"sk-[A-Za-z0-9_-]{8,}|[A-Za-z0-9_-]{32,}")


def main() -> int:
    _load_dotenv()
    checks: list[dict[str, str]] = []
    exit_code = 0

    if not _deepseek_configured():
        checks.append({"component": "deepseek", "status": "failed", "code": "deepseek_env_missing"})
        return _emit(checks, 1)

    try:
        raw = deepseek_json("Return a JSON object with a status field.", {"check": "provider"})
        parsed = json.loads(raw) if isinstance(raw, str) else raw
        if not isinstance(parsed, dict):
            raise ValueError("unexpected_provider_response")
        checks.append({"component": "deepseek", "status": "ok", "code": "provider_call_succeeded"})
    except Exception:
        checks.append({"component": "deepseek", "status": "failed", "code": "provider_call_failed"})
        return _emit(checks, 1)

    set_tool_selection_model(deepseek_tool_selection)
    planner_result = run_tool_selection_planner(
        {
            "request_id": "smoke-llm",
            "trace_id": "smoke-llm",
            "user_question": "What does the employee guideline say about sick leave?",
            "tool_capability_cards": [{"tool": "sql_rag"}],
            "trace": [],
        }
    )
    selection = planner_result.get("tool_selection") or {}
    if selection.get("status") == "selected" and not _contains_forbidden(selection):
        checks.append({"component": "tool_selection_planner", "status": "ok", "code": "route_level_schema_valid"})
    else:
        checks.append({"component": "tool_selection_planner", "status": "failed", "code": "route_level_schema_invalid"})
        exit_code = 1

    set_final_answer_model(deepseek_payload_call)
    answer_result = run_final_answer_composer(
        {
            "request_id": "smoke-llm",
            "trace_id": "smoke-llm",
            "user_question": "What does the employee guideline say about sick leave?",
            "final_answer_context": {
                "status": "success",
                "tool": "sql_rag",
                "validated_evidence": [
                    {
                        "evidence_ref": "rag_evidence_1",
                        "text": "Employees may use sick leave when they are ill and should notify their manager.",
                        "citation_id": "c1",
                    }
                ],
                "validated_citations": [
                    {
                        "citation_id": "c1",
                        "title": "Employee Guidelines",
                        "safe_location_path": "Employee Guidelines/policy.md",
                    }
                ],
                "limitations": [],
                "errors": [],
            },
            "trace": [],
        }
    )
    if answer_result.get("final_status") == "answered" and answer_result.get("final_answer") and not _unsafe_public_text(str(answer_result.get("final_answer"))):
        checks.append({"component": "final_answer_composer", "status": "ok", "code": "public_answer_valid"})
    else:
        checks.append({"component": "final_answer_composer", "status": "failed", "code": "public_answer_invalid"})
        exit_code = 1

    return _emit(checks, exit_code)


def _load_dotenv() -> None:
    for candidate in (Path(".env"), Path(__file__).resolve().parents[3] / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text(encoding="utf-8").splitlines():
            if not line.strip() or line.lstrip().startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key, value)


def _deepseek_configured() -> bool:
    key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    return bool(key and key != "replace_with_deepseek_api_key")


def _contains_forbidden(value: Any) -> bool:
    if isinstance(value, dict):
        if FORBIDDEN_OUTPUT_FIELDS.intersection(value):
            return True
        return any(_contains_forbidden(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_forbidden(item) for item in value)
    return False


def _unsafe_public_text(text: str) -> bool:
    return bool(re.search(r"sk-[A-Za-z0-9_-]{8,}|postgres(?:ql)?://|[A-Za-z]:\\Users\\|file://", text, re.IGNORECASE))


def _emit(checks: list[dict[str, str]], exit_code: int) -> int:
    output = {"status": "ok" if exit_code == 0 else "failed", "checks": checks}
    text = json.dumps(output, indent=2, sort_keys=True)
    if SECRET_RE.search(text):
        print(json.dumps({"status": "failed", "checks": [{"component": "smoke", "status": "failed", "code": "secret_like_output"}]}, indent=2))
        return 1
    print(text)
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
