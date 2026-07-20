from __future__ import annotations

from app.graphs.final_answer_composer.graph import run_final_answer_composer


def final_answer_composer(state: dict) -> dict:
    result = run_final_answer_composer(state)
    return {
        "final_answer": result.get("final_answer"),
        "final_status": result.get("final_status"),
        "public_citations": result.get("public_citations", []),
        "public_limitations": result.get("public_limitations", []),
        "errors": result.get("errors", []),
        "trace": result.get("trace", []),
    }
