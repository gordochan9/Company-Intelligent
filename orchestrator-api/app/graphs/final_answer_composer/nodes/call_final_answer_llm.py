from __future__ import annotations

from typing import Any, Callable

from app.graphs.final_answer_composer.state import FinalAnswerComposerState, fail_state


_FinalAnswerModel = Callable[[dict[str, Any]], dict[str, Any] | str]
_final_answer_model: _FinalAnswerModel | None = None


def set_final_answer_model(model: _FinalAnswerModel | None) -> None:
    global _final_answer_model
    _final_answer_model = model


def call_final_answer_llm(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    if _final_answer_model is None:
        return fail_state("call_final_answer_llm", "final_answer_model_unavailable", "Final answer model is unavailable.")
    try:
        response = _final_answer_model(dict(state["final_answer_llm_payload"]))
    except Exception:
        return fail_state("call_final_answer_llm", "final_answer_model_error", "Final answer model call failed.")
    return {
        "raw_final_answer_llm_response": response,
        "final_answer_llm_metadata": {"provider_status": "succeeded"},
    }
