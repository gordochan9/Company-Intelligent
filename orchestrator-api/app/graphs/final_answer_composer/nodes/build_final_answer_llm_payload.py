from __future__ import annotations

from app.graphs.final_answer_composer.contracts import build_llm_payload
from app.graphs.final_answer_composer.state import FinalAnswerComposerState


def build_final_answer_llm_payload(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    return {
        "final_answer_llm_payload": build_llm_payload(
            str(state["user_question"]),
            dict(state["final_answer_context"]),
        )
    }
