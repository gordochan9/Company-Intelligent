from __future__ import annotations

import hmac
import os

from fastapi import APIRouter, Header, HTTPException, Request

from app.graphs.main.graph import run_main_graph
from app.schemas.openwebui import OpenWebUIAskRequest, OpenWebUIAskResponse
from app.services.openwebui_identity import OpenWebUIIdentityError, normalize_openwebui_identity


router = APIRouter(prefix="/openwebui", tags=["openwebui"])


@router.post("/ask", response_model=OpenWebUIAskResponse)
def openwebui_ask(
    payload: OpenWebUIAskRequest,
    request: Request,
    x_company_tool_token: str | None = Header(default=None, alias="X-Company-Tool-Token"),
) -> OpenWebUIAskResponse:
    _require_transport_token(x_company_tool_token)
    try:
        identity = normalize_openwebui_identity(dict(request.headers))
    except OpenWebUIIdentityError:
        raise HTTPException(status_code=400, detail="Invalid Open WebUI identity metadata.") from None

    result = run_main_graph(
        {
            "user_question": payload.question,
            "openwebui_user_identity": identity,
            "openwebui_request_metadata": {"source": "company_intelligent"},
        }
    )
    return OpenWebUIAskResponse(
        final_answer=str(result.get("final_answer") or ""),
        final_status=str(result.get("final_status") or "error"),
        public_citations=list(result.get("public_citations") or []),
        public_limitations=_public_limitations(result.get("public_limitations")),
        errors=list(result.get("errors") or []),
    )


def _require_transport_token(actual: str | None) -> None:
    expected = os.getenv("OPENWEBUI_SHARED_SECRET")
    if not expected:
        raise HTTPException(status_code=503, detail="Open WebUI bridge is not configured.")
    if not actual or not hmac.compare_digest(actual, expected):
        raise HTTPException(status_code=401, detail="Invalid Open WebUI bridge credentials.")


def _public_limitations(value: object) -> list[dict[str, str]]:
    limitations = value if isinstance(value, list) else []
    safe: list[dict[str, str]] = []
    for item in limitations:
        if isinstance(item, dict):
            safe.append({str(key): str(val) for key, val in item.items()})
        elif item:
            safe.append({"message": str(item)})
    return safe
