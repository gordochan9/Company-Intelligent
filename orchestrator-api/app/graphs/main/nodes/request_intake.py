from __future__ import annotations

from app.graphs.main.state import MainGraphState
from app.services.audit_trace import new_request_id, new_trace_id


def request_intake(state: MainGraphState) -> MainGraphState:
    return {
        "request_id": str(state.get("request_id") or new_request_id()),
        "trace_id": str(state.get("trace_id") or new_trace_id()),
        "session_id": state.get("session_id"),
        "user_question": str(state.get("user_question") or ""),
        "openwebui_user_identity": dict(state.get("openwebui_user_identity") or {}),
        "messages": list(state.get("messages") or []),
        "trace": list(state.get("trace") or []),
        "tool_results": [],
        "errors": [],
    }
