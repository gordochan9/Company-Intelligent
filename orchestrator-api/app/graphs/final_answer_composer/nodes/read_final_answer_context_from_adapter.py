from __future__ import annotations

from app.graphs.final_answer_composer.contracts import FinalAnswerContractError, normalize_final_answer_context
from app.graphs.final_answer_composer.state import FinalAnswerComposerState, fail_state


def read_final_answer_context_from_adapter(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    try:
        context = normalize_final_answer_context(state.get("final_answer_context"))
    except FinalAnswerContractError as exc:
        return fail_state("read_final_answer_context_from_adapter", exc.code, exc.message)
    return {
        "final_answer_context": context,
        "answer_material": context["answer_material"],
        "adapter_citations": list(context["citations"]),
        "limitations": list(context["limitations"]),
        "errors": list(context["errors"]),
    }
