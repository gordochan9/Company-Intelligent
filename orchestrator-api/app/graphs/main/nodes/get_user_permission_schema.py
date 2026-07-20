from __future__ import annotations

from app.graphs.main.state import MainGraphState, safe_terminal_context
from app.graphs.permission_schema.graph import run_get_user_permission_schema


def get_user_permission_schema(state: MainGraphState) -> MainGraphState:
    result = run_get_user_permission_schema(state)
    patch: MainGraphState = {
        "access_status": result.get("access_status", "access_failed"),
        "trusted_user_context": result.get("trusted_user_context"),
        "user_permission_schema": result.get("user_permission_schema"),
        "tool_capability_cards": list(result.get("tool_capability_cards") or []),
        "permission_limitations": list(result.get("permission_limitations") or []),
        "permission_errors": list(result.get("permission_errors") or result.get("errors") or []),
        "trace": list(result.get("trace") or state.get("trace") or []),
    }
    if patch["access_status"] != "ok":
        status = "denied" if patch["access_status"] == "denied" else "access_failed"
        patch["final_answer_context"] = safe_terminal_context(
            status,
            reason="Permission check did not allow this request.",
            limitations=patch["permission_limitations"],
            errors=patch["permission_errors"],
        )
    return patch
