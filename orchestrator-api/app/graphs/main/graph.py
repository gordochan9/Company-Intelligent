from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.graphs.main.nodes.final_answer_composer import final_answer_composer
from app.graphs.main.nodes.get_user_permission_schema import get_user_permission_schema
from app.graphs.main.nodes.request_intake import request_intake
from app.graphs.main.nodes.tool_dispatch import tool_dispatch
from app.graphs.main.nodes.tool_selection_planner import tool_selection_planner
from app.graphs.main.state import MainGraphState


def _after_permission(state: MainGraphState) -> Literal["tool_selection_planner", "final_answer_composer"]:
    return "tool_selection_planner" if state.get("access_status") == "ok" else "final_answer_composer"


def _after_tool_selection(state: MainGraphState) -> Literal["tool_dispatch", "final_answer_composer"]:
    selection = state.get("tool_selection") or {}
    return "tool_dispatch" if selection.get("status") == "selected" else "final_answer_composer"


def build_main_graph():
    graph = StateGraph(MainGraphState)
    graph.add_node("request_intake", request_intake)
    graph.add_node("get_user_permission_schema", get_user_permission_schema)
    graph.add_node("tool_selection_planner", tool_selection_planner)
    graph.add_node("tool_dispatch", tool_dispatch)
    graph.add_node("final_answer_composer", final_answer_composer)

    graph.add_edge(START, "request_intake")
    graph.add_edge("request_intake", "get_user_permission_schema")
    graph.add_conditional_edges("get_user_permission_schema", _after_permission)
    graph.add_conditional_edges("tool_selection_planner", _after_tool_selection)
    graph.add_edge("tool_dispatch", "final_answer_composer")
    graph.add_edge("final_answer_composer", END)
    return graph.compile()


main_graph = build_main_graph()


def run_main_graph(input_state: MainGraphState) -> MainGraphState:
    return main_graph.invoke(input_state)
