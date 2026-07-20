from __future__ import annotations

from app.graphs.tool_selection_planner.state import ToolSelectionPlannerState
from app.services.tool_selection_planner import parse_tool_selection_output as parse_output


def parse_tool_selection_output(state: ToolSelectionPlannerState) -> ToolSelectionPlannerState:
    return {
        "tool_selection": parse_output(
            state.get("raw_llm_tool_selection"),
            list(state.get("available_tool_cards", [])),
        )
    }
