from __future__ import annotations

from app.graphs.tool_selection_planner.state import ToolSelectionPlannerState
from app.services.tool_selection_planner import build_tool_selection_prompt as build_prompt


def build_tool_selection_prompt(state: ToolSelectionPlannerState) -> ToolSelectionPlannerState:
    return {
        "tool_selection_prompt": build_prompt(
            str(state.get("user_question") or ""),
            list(state.get("available_tool_cards", [])),
            list(state.get("messages") or []),
        )
    }
