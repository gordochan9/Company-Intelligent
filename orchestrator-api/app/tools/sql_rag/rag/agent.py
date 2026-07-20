from __future__ import annotations

from app.tools.sql_rag.rag.graph import invoke_rag_subgraph
from app.tools.sql_rag.rag.state import RagState


def run_rag_workflow(step_state: RagState) -> RagState:
    return invoke_rag_subgraph(step_state)
