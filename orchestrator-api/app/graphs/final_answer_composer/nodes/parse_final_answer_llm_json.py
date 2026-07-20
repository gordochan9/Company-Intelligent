from __future__ import annotations

from app.graphs.final_answer_composer.contracts import FinalAnswerContractError, parse_llm_json
from app.graphs.final_answer_composer.state import FinalAnswerComposerState, fail_state


def parse_final_answer_llm_json(state: FinalAnswerComposerState) -> FinalAnswerComposerState:
    try:
        parsed = parse_llm_json(state.get("raw_final_answer_llm_response"))
    except FinalAnswerContractError as exc:
        return fail_state("parse_final_answer_llm_json", exc.code, exc.message)
    return {
        "parsed_answer_text": parsed["answer_text"],
        "parsed_used_citation_ids": parsed["used_citation_ids"],
    }
