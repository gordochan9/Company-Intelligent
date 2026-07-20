from fastapi import FastAPI

from app.graphs.final_answer_composer.nodes.call_final_answer_llm import set_final_answer_model
from app.routes.openwebui import router as openwebui_router
from app.services.join_discovery_approved_joins import set_join_discovery_model
from app.services.llm_provider import deepseek_join_discovery, deepseek_payload_call, deepseek_tool_selection
from app.services.tool_selection_planner import set_tool_selection_model
from app.tools.sql_rag.nodes.runtime_obligation_planner import set_runtime_obligation_planner_model
from app.tools.sql_rag.rag.services.search_plan import set_rag_plan_model
from app.tools.sql_rag.sql.services.llm import set_sql_generation_model, set_sql_intent_model, set_sql_selector_model


def configure_runtime_models() -> None:
    import os

    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key == "replace_with_deepseek_api_key":
        return
    set_tool_selection_model(deepseek_tool_selection)
    set_runtime_obligation_planner_model(deepseek_payload_call)
    set_rag_plan_model(deepseek_payload_call)
    set_sql_intent_model(deepseek_payload_call)
    set_sql_selector_model(deepseek_payload_call)
    set_sql_generation_model(deepseek_payload_call)
    set_final_answer_model(deepseek_payload_call)
    set_join_discovery_model(deepseek_join_discovery)


def create_app() -> FastAPI:
    configure_runtime_models()
    app = FastAPI(title="Project 3.0 Orchestrator API")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "orchestrator-api"}

    app.include_router(openwebui_router)
    return app


app = create_app()
