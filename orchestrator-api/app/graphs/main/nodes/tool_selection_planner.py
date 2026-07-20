from __future__ import annotations

from app.graphs.main.state import MainGraphState, safe_terminal_context
from app.graphs.tool_selection_planner.graph import run_tool_selection_planner


def tool_selection_planner(state: MainGraphState) -> MainGraphState:
    result = run_tool_selection_planner(state)
    selection = result.get("tool_selection") or {
        "status": "error",
        "selected_tools": [],
        "reason": "Tool selection failed.",
        "limitations": [],
        "errors": [{"code": "tool_selection_missing", "message": "Tool selection failed."}],
        "debug": {},
    }
    patch: MainGraphState = {"tool_selection": selection, "trace": list(result.get("trace") or state.get("trace") or [])}
    if selection.get("status") != "selected":
        status = selection.get("status") if selection.get("status") in {"clarification", "unsupported"} else "error"
        patch["final_answer_context"] = safe_terminal_context(
            status,
            reason=str(selection.get("reason") or "Tool selection did not select a workflow."),
            limitations=list(selection.get("limitations") or []),
            errors=list(selection.get("errors") or []),
        )
    return patch
