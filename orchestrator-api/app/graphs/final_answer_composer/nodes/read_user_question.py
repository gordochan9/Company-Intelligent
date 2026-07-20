from __future__ import annotations

from app.graphs.final_answer_composer.state import FinalAnswerComposerState, fail_state


def read_user_question(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    question = state.get("user_question")
    if not isinstance(question, str) or not question.strip():
        return fail_state("read_user_question", "missing_user_question", "User question was missing.")
    return {"user_question": question}
