from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.tools.sql_rag.rag.nodes.build_permission_filtered_rag_schema import build_permission_filtered_rag_schema
from app.tools.sql_rag.rag.nodes.build_rag_search_plan import build_rag_search_plan
from app.tools.sql_rag.rag.nodes.emit_rag_failure import emit_rag_failure
from app.tools.sql_rag.rag.nodes.emit_rag_result import emit_rag_result
from app.tools.sql_rag.rag.nodes.rag_intake import rag_intake
from app.tools.sql_rag.rag.nodes.read_filtered_rag_schema import read_filtered_rag_schema
from app.tools.sql_rag.rag.nodes.retrieve_relevant_chunks import retrieve_relevant_chunks
from app.tools.sql_rag.rag.nodes.select_relevant_documents import select_relevant_documents
from app.tools.sql_rag.rag.nodes.validate_rag_evidence import validate_rag_evidence
from app.tools.sql_rag.rag.state import STATUS_RUNNING, RagState


def _next_or_failure(next_node: str):
    def route(state: RagState) -> Literal["emit_rag_failure"] | str:
        return next_node if state.get("rag_status") == STATUS_RUNNING else "emit_rag_failure"

    return route


def build_rag_subgraph():
    graph = StateGraph(RagState)
    graph.add_node("rag_intake", rag_intake)
    graph.add_node("build_permission_filtered_rag_schema", build_permission_filtered_rag_schema)
    graph.add_node("read_filtered_rag_schema", read_filtered_rag_schema)
    graph.add_node("build_rag_search_plan", build_rag_search_plan)
    graph.add_node("select_relevant_documents", select_relevant_documents)
    graph.add_node("retrieve_relevant_chunks", retrieve_relevant_chunks)
    graph.add_node("validate_rag_evidence", validate_rag_evidence)
    graph.add_node("emit_rag_result", emit_rag_result)
    graph.add_node("emit_rag_failure", emit_rag_failure)

    graph.add_edge(START, "rag_intake")
    graph.add_conditional_edges("rag_intake", _next_or_failure("build_permission_filtered_rag_schema"))
    graph.add_conditional_edges("build_permission_filtered_rag_schema", _next_or_failure("read_filtered_rag_schema"))
    graph.add_conditional_edges("read_filtered_rag_schema", _next_or_failure("build_rag_search_plan"))
    graph.add_conditional_edges("build_rag_search_plan", _next_or_failure("select_relevant_documents"))
    graph.add_conditional_edges("select_relevant_documents", _next_or_failure("retrieve_relevant_chunks"))
    graph.add_conditional_edges("retrieve_relevant_chunks", _next_or_failure("validate_rag_evidence"))
    graph.add_conditional_edges("validate_rag_evidence", _next_or_failure("emit_rag_result"))
    graph.add_edge("emit_rag_result", END)
    graph.add_edge("emit_rag_failure", END)
    return graph.compile()


rag_subgraph = build_rag_subgraph()


def invoke_rag_subgraph(input_state: RagState) -> RagState:
    return rag_subgraph.invoke(input_state)
