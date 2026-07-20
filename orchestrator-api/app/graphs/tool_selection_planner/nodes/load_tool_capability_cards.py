from __future__ import annotations

from app.graphs.tool_selection_planner.state import ToolSelectionPlannerState
from app.services.tool_selection_planner import normalize_tool_cards


def load_tool_capability_cards(state: ToolSelectionPlannerState) -> ToolSelectionPlannerState:
    return {"available_tool_cards": normalize_tool_cards(state.get("tool_capability_cards", []))}
