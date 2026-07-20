from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.tools.sql_rag.nodes.adapter import adapter
from app.tools.sql_rag.nodes.final_result_bundle import final_result_bundle
from app.tools.sql_rag.nodes.multi_step_runtime_executor import multi_step_runtime_executor
from app.tools.sql_rag.nodes.normalizer_transformer import normalizer_transformer
from app.tools.sql_rag.nodes.perform_rag_sql import perform_rag_sql
from app.tools.sql_rag.nodes.runtime_obligation_planner import runtime_obligation_planner
from app.tools.sql_rag.nodes.sql_rag_agent import sql_rag_agent
from app.tools.sql_rag.state import STATUS_NOT_STARTED, STATUS_PLANNED, STATUS_RUNNING, SqlRagState


def _after_agent(state: SqlRagState) -> Literal["runtime_obligation_planner", "final_result_bundle"]:
    return "runtime_obligation_planner" if state.get("runtime_plan_status") == STATUS_NOT_STARTED else "final_result_bundle"


def _after_planner(state: SqlRagState) -> Literal["multi_step_runtime_executor", "final_result_bundle"]:
    return "multi_step_runtime_executor" if state.get("runtime_plan_status") == STATUS_PLANNED else "final_result_bundle"


def _after_executor(state: SqlRagState) -> Literal["perform_rag_sql", "final_result_bundle"]:
    if state.get("runtime_plan_status") == STATUS_RUNNING and state.get("current_step"):
        return "perform_rag_sql"
    return "final_result_bundle"


def build_sql_rag_tool_graph():
    graph = StateGraph(SqlRagState)
    graph.add_node("sql_rag_agent", sql_rag_agent)
    graph.add_node("runtime_obligation_planner", runtime_obligation_planner)
    graph.add_node("multi_step_runtime_executor", multi_step_runtime_executor)
    graph.add_node("perform_rag_sql", perform_rag_sql)
    graph.add_node("normalizer_transformer", normalizer_transformer)
    graph.add_node("final_result_bundle", final_result_bundle)
    graph.add_node("adapter", adapter)

    graph.add_edge(START, "sql_rag_agent")
    graph.add_conditional_edges("sql_rag_agent", _after_agent)
    graph.add_conditional_edges("runtime_obligation_planner", _after_planner)
    graph.add_conditional_edges("multi_step_runtime_executor", _after_executor)
    graph.add_edge("perform_rag_sql", "normalizer_transformer")
    graph.add_edge("normalizer_transformer", "multi_step_runtime_executor")
    graph.add_edge("final_result_bundle", "adapter")
    graph.add_edge("adapter", END)
    return graph.compile()


sql_rag_tool_graph = build_sql_rag_tool_graph()


def invoke_sql_rag_tool_graph(input_state: SqlRagState) -> SqlRagState:
    return sql_rag_tool_graph.invoke(input_state)
