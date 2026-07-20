from __future__ import annotations

from app.graphs.tool_selection_planner.state import ToolSelectionPlannerState


def tool_selection_intake(state: ToolSelectionPlannerState) -> ToolSelectionPlannerState:
    return {
        "request_id": state.get("request_id", ""),
        "trace_id": state.get("trace_id", ""),
        "user_question": str(state.get("user_question") or ""),
        "messages": list(state.get("messages", [])),
        "conversation_context": state.get("conversation_context"),
        "tool_capability_cards": list(state.get("tool_capability_cards", [])),
        "available_tool_cards": [],
        "tool_selection_prompt": {},
        "raw_llm_tool_selection": None,
        "tool_selection": None,
        "limitations": [],
        "errors": [],
        "debug": {},
        "trace": list(state.get("trace", [])),
    }
