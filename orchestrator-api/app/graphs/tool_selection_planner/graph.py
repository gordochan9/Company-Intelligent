from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.graphs.tool_selection_planner.nodes.build_tool_selection_prompt import build_tool_selection_prompt
from app.graphs.tool_selection_planner.nodes.emit_tool_selection import emit_tool_selection
from app.graphs.tool_selection_planner.nodes.llm_select_tool_workflow import llm_select_tool_workflow
from app.graphs.tool_selection_planner.nodes.load_tool_capability_cards import load_tool_capability_cards
from app.graphs.tool_selection_planner.nodes.parse_tool_selection_output import parse_tool_selection_output
from app.graphs.tool_selection_planner.nodes.tool_selection_intake import tool_selection_intake
from app.graphs.tool_selection_planner.state import ToolSelectionPlannerState


def build_tool_selection_planner_graph():
    graph = StateGraph(ToolSelectionPlannerState)
    graph.add_node("tool_selection_intake", tool_selection_intake)
    graph.add_node("load_tool_capability_cards", load_tool_capability_cards)
    graph.add_node("build_tool_selection_prompt", build_tool_selection_prompt)
    graph.add_node("llm_select_tool_workflow", llm_select_tool_workflow)
    graph.add_node("parse_tool_selection_output", parse_tool_selection_output)
    graph.add_node("emit_tool_selection", emit_tool_selection)

    graph.add_edge(START, "tool_selection_intake")
    graph.add_edge("tool_selection_intake", "load_tool_capability_cards")
    graph.add_edge("load_tool_capability_cards", "build_tool_selection_prompt")
    graph.add_edge("build_tool_selection_prompt", "llm_select_tool_workflow")
    graph.add_edge("llm_select_tool_workflow", "parse_tool_selection_output")
    graph.add_edge("parse_tool_selection_output", "emit_tool_selection")
    graph.add_edge("emit_tool_selection", END)
    return graph.compile()


tool_selection_planner_graph = build_tool_selection_planner_graph()


def invoke_tool_selection_planner_subgraph(input_state: ToolSelectionPlannerState) -> ToolSelectionPlannerState:
    return tool_selection_planner_graph.invoke(input_state)


def run_tool_selection_planner(main_state: ToolSelectionPlannerState) -> ToolSelectionPlannerState:
    return invoke_tool_selection_planner_subgraph(main_state)
