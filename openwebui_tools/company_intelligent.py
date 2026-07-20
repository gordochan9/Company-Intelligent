from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


@dataclass
class Valves:
    orchestrator_api_base_url: str = os.getenv("ORCHESTRATOR_API_BASE_URL", "http://orchestrator-api:8000")
    openwebui_shared_secret: str = os.getenv("OPENWEBUI_SHARED_SECRET", "")
    request_timeout_seconds: float = 600.0
    emit_status_updates: bool = False


class Tools:
    """Open WebUI tool exposing the single Project 3.0 company_intelligent backend bridge."""

    def __init__(self) -> None:
        self.valves = Valves()

    def company_intelligent(self, question: str, __user__: dict | None = None, __event_emitter__=None) -> str:
        response = self._ask_backend(question, self._extract_identity(__user__ or {}))
        final_answer = response.get("final_answer")
        if not isinstance(final_answer, str) or not final_answer:
            raise RuntimeError("Backend response did not include final_answer.")
        return final_answer

    def _ask_backend(self, question: str, identity: dict[str, str]) -> dict[str, Any]:
        url = self.valves.orchestrator_api_base_url.rstrip("/") + "/openwebui/ask"
        body = json.dumps({"question": question}).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Company-Tool-Token": self.valves.openwebui_shared_secret,
                "X-OpenWebUI-User-Id": identity.get("user_id", ""),
                "X-OpenWebUI-User-Email": identity.get("email", ""),
                "X-OpenWebUI-User-Name": identity.get("display_name", ""),
                "X-OpenWebUI-User-Role": identity.get("role_hint", ""),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.valves.request_timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise RuntimeError("Company backend request failed.") from exc

    def _extract_identity(self, user: dict[str, Any]) -> dict[str, str]:
        return {
            "user_id": str(user.get("id") or ""),
            "email": str(user.get("email") or ""),
            "display_name": str(user.get("name") or user.get("display_name") or ""),
            "role_hint": str(user.get("role") or ""),
        }
