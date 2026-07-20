from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.tools.sql_rag.sql.nodes.build_permission_filtered_sql_schema import build_permission_filtered_sql_schema
from app.tools.sql_rag.sql.nodes.build_sql_query_intent import build_sql_query_intent
from app.tools.sql_rag.sql.nodes.emit_sql_failure import emit_sql_failure
from app.tools.sql_rag.sql.nodes.emit_sql_result import emit_sql_result
from app.tools.sql_rag.sql.nodes.execute_sql import execute_sql
from app.tools.sql_rag.sql.nodes.generate_candidate_sql import generate_candidate_sql
from app.tools.sql_rag.sql.nodes.load_approved_join_relationships import load_approved_join_relationships
from app.tools.sql_rag.sql.nodes.read_filtered_sql_schema import read_filtered_sql_schema
from app.tools.sql_rag.sql.nodes.select_relevant_structured_resources import select_relevant_structured_resources
from app.tools.sql_rag.sql.nodes.sql_intake import sql_intake
from app.tools.sql_rag.sql.nodes.validate_sql_before_execution import validate_sql_before_execution
from app.tools.sql_rag.sql.nodes.validate_sql_result import validate_sql_result
from app.tools.sql_rag.sql.state import STATUS_RUNNING, SqlState


def _next_or_failure(next_node: str):
    def route(state: SqlState) -> Literal["emit_sql_failure"] | str:
        return next_node if state.get("sql_status") == STATUS_RUNNING else "emit_sql_failure"

    return route


def _route_after_sql_validation(
    state: SqlState,
) -> Literal["generate_candidate_sql", "execute_sql", "emit_sql_failure"]:
    if state.get("sql_status") != STATUS_RUNNING:
        return "emit_sql_failure"
    if isinstance(state.get("validated_sql"), dict):
        return "execute_sql"
    if state.get("unbound_parameter_regeneration_count") == 1 and state.get("candidate_sql") is None:
        return "generate_candidate_sql"
    return "emit_sql_failure"


def build_sql_subgraph():
    graph = StateGraph(SqlState)
    graph.add_node("sql_intake", sql_intake)
    graph.add_node("build_permission_filtered_sql_schema", build_permission_filtered_sql_schema)
    graph.add_node("load_approved_join_relationships", load_approved_join_relationships)
    graph.add_node("read_filtered_sql_schema", read_filtered_sql_schema)
    graph.add_node("build_sql_query_intent", build_sql_query_intent)
    graph.add_node("select_relevant_structured_resources", select_relevant_structured_resources)
    graph.add_node("generate_candidate_sql", generate_candidate_sql)
    graph.add_node("validate_sql_before_execution", validate_sql_before_execution)
    graph.add_node("execute_sql", execute_sql)
    graph.add_node("validate_sql_result", validate_sql_result)
    graph.add_node("emit_sql_result", emit_sql_result)
    graph.add_node("emit_sql_failure", emit_sql_failure)

    graph.add_edge(START, "sql_intake")
    graph.add_conditional_edges("sql_intake", _next_or_failure("build_permission_filtered_sql_schema"))
    graph.add_conditional_edges("build_permission_filtered_sql_schema", _next_or_failure("load_approved_join_relationships"))
    graph.add_conditional_edges("load_approved_join_relationships", _next_or_failure("read_filtered_sql_schema"))
    graph.add_conditional_edges("read_filtered_sql_schema", _next_or_failure("build_sql_query_intent"))
    graph.add_conditional_edges("build_sql_query_intent", _next_or_failure("select_relevant_structured_resources"))
    graph.add_conditional_edges("select_relevant_structured_resources", _next_or_failure("generate_candidate_sql"))
    graph.add_conditional_edges("generate_candidate_sql", _next_or_failure("validate_sql_before_execution"))
    graph.add_conditional_edges("validate_sql_before_execution", _route_after_sql_validation)
    graph.add_conditional_edges("execute_sql", _next_or_failure("validate_sql_result"))
    graph.add_conditional_edges("validate_sql_result", _next_or_failure("emit_sql_result"))
    graph.add_edge("emit_sql_result", END)
    graph.add_edge("emit_sql_failure", END)
    return graph.compile()


sql_subgraph = build_sql_subgraph()


def invoke_sql_subgraph(input_state: SqlState) -> SqlState:
    return sql_subgraph.invoke(input_state)
