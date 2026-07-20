from __future__ import annotations

from typing import Literal

from langgraph.graph import END, START, StateGraph

from app.graphs.final_answer_composer.nodes.attach_public_citations import attach_public_citations
from app.graphs.final_answer_composer.nodes.build_final_answer_llm_payload import build_final_answer_llm_payload
from app.graphs.final_answer_composer.nodes.call_final_answer_llm import call_final_answer_llm
from app.graphs.final_answer_composer.nodes.emit_final_answer import emit_final_answer
from app.graphs.final_answer_composer.nodes.final_answer_intake import final_answer_intake
from app.graphs.final_answer_composer.nodes.log_final_answer_llm_response import log_final_answer_llm_response
from app.graphs.final_answer_composer.nodes.parse_final_answer_llm_json import parse_final_answer_llm_json
from app.graphs.final_answer_composer.nodes.read_final_answer_context_from_adapter import read_final_answer_context_from_adapter
from app.graphs.final_answer_composer.nodes.read_user_question import read_user_question
from app.graphs.final_answer_composer.state import STATUS_ERROR, FinalAnswerComposerState


def _next_or_emit(next_node: str):
    def route(state: FinalAnswerComposerState) -> Literal["emit_final_answer"] | str:
        return "emit_final_answer" if state.get("composer_status") == STATUS_ERROR else next_node

    return route


def build_final_answer_composer_graph():
    graph = StateGraph(FinalAnswerComposerState)
    graph.add_node("final_answer_intake", final_answer_intake)
    graph.add_node("read_user_question", read_user_question)
    graph.add_node("read_final_answer_context_from_adapter", read_final_answer_context_from_adapter)
    graph.add_node("build_final_answer_llm_payload", build_final_answer_llm_payload)
    graph.add_node("call_final_answer_llm", call_final_answer_llm)
    graph.add_node("log_final_answer_llm_response", log_final_answer_llm_response)
    graph.add_node("parse_final_answer_llm_json", parse_final_answer_llm_json)
    graph.add_node("attach_public_citations", attach_public_citations)
    graph.add_node("emit_final_answer", emit_final_answer)

    graph.add_edge(START, "final_answer_intake")
    graph.add_edge("final_answer_intake", "read_user_question")
    graph.add_conditional_edges("read_user_question", _next_or_emit("read_final_answer_context_from_adapter"))
    graph.add_conditional_edges("read_final_answer_context_from_adapter", _next_or_emit("build_final_answer_llm_payload"))
    graph.add_edge("build_final_answer_llm_payload", "call_final_answer_llm")
    graph.add_edge("call_final_answer_llm", "log_final_answer_llm_response")
    graph.add_conditional_edges("log_final_answer_llm_response", _next_or_emit("parse_final_answer_llm_json"))
    graph.add_conditional_edges("parse_final_answer_llm_json", _next_or_emit("attach_public_citations"))
    graph.add_edge("attach_public_citations", "emit_final_answer")
    graph.add_edge("emit_final_answer", END)
    return graph.compile()


final_answer_composer_graph = build_final_answer_composer_graph()


def run_final_answer_composer(main_state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    result = final_answer_composer_graph.invoke(main_state)
    return {
        "final_answer": result.get("final_answer"),
        "final_status": result.get("final_status"),
        "public_citations": result.get("public_citations", []),
        "public_limitations": result.get("public_limitations", []),
        "errors": result.get("errors", []),
        "trace": result.get("trace", []),
    }
