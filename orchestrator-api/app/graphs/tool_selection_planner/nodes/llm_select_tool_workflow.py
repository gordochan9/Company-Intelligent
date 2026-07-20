from __future__ import annotations

from app.graphs.tool_selection_planner.state import ToolSelectionPlannerState
from app.services.tool_selection_planner import ToolSelectionModelUnavailable, model_unavailable_selection, select_tool_workflow


def llm_select_tool_workflow(state: ToolSelectionPlannerState) -> ToolSelectionPlannerState:
    try:
        raw_selection = select_tool_workflow(dict(state.get("tool_selection_prompt") or {}))
    except ToolSelectionModelUnavailable:
        raw_selection = model_unavailable_selection()
    return {"raw_llm_tool_selection": raw_selection}
