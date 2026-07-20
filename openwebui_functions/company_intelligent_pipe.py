"""Open WebUI Pipe entrypoint for the Project 3.0 backend."""

import asyncio
import json
import os
import urllib.error
import urllib.request
from typing import Any

from pydantic import BaseModel, Field


SAFE_TRANSPORT_ERROR = (
    "I couldn't reach the company backend for this request. Please try again later."
)


class Pipe:
    class Valves(BaseModel):
        orchestrator_api_base_url: str = Field(
            default_factory=lambda: os.getenv(
                "ORCHESTRATOR_API_BASE_URL", "http://orchestrator-api:8000"
            )
        )
        openwebui_shared_secret: str = Field(
            default_factory=lambda: os.getenv("OPENWEBUI_SHARED_SECRET", "")
        )
        request_timeout_seconds: float = 600.0

    def __init__(self) -> None:
        self.valves = self.Valves()

    async def pipe(
        self,
        body: dict[str, Any],
        __user__: dict[str, Any] | None = None,
        __metadata__: dict[str, Any] | None = None,
        __event_emitter__: Any | None = None,
    ) -> str:
        question = self._extract_question(body, __metadata__)
        if not question:
            return SAFE_TRANSPORT_ERROR

        identity = self._extract_identity(__user__)
        try:
            return await asyncio.to_thread(self._ask_backend, question, identity)
        except (
            OSError,
            urllib.error.URLError,
            urllib.error.HTTPError,
            json.JSONDecodeError,
            ValueError,
            TypeError,
        ):
            return SAFE_TRANSPORT_ERROR

    def _extract_question(
        self, body: dict[str, Any], metadata: dict[str, Any] | None
    ) -> str:
        if isinstance(metadata, dict):
            user_prompt = metadata.get("user_prompt")
            if isinstance(user_prompt, str) and user_prompt.strip():
                return user_prompt

        messages = body.get("messages", [])
        if not isinstance(messages, list):
            return ""

        for message in reversed(messages):
            if not isinstance(message, dict) or message.get("role") != "user":
                continue
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
        return ""

    def _extract_identity(self, user: dict[str, Any] | None) -> dict[str, str]:
        if not isinstance(user, dict):
            return {}

        identity: dict[str, str] = {}
        for key in ("id", "email", "role"):
            value = user.get(key)
            if value is not None:
                identity[key] = str(value)

        name = user.get("name", user.get("display_name"))
        if name is not None:
            identity["name"] = str(name)

        return identity

    def _ask_backend(self, question: str, identity: dict[str, str]) -> str:
        base_url = self.valves.orchestrator_api_base_url.rstrip("/")
        url = f"{base_url}/openwebui/ask"
        payload = json.dumps({"question": question}).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "X-Company-Tool-Token": self.valves.openwebui_shared_secret,
        }
        if user_id := identity.get("id"):
            headers["X-OpenWebUI-User-Id"] = user_id
        if email := identity.get("email"):
            headers["X-OpenWebUI-User-Email"] = email
        if name := identity.get("name"):
            headers["X-OpenWebUI-User-Name"] = name
        if role := identity.get("role"):
            headers["X-OpenWebUI-User-Role"] = role

        request = urllib.request.Request(
            url,
            data=payload,
            headers=headers,
            method="POST",
        )
        with urllib.request.urlopen(
            request, timeout=self.valves.request_timeout_seconds
        ) as response:
            data = json.loads(response.read().decode("utf-8"))

        final_answer = data.get("final_answer")
        if not isinstance(final_answer, str) or not final_answer:
            raise ValueError("missing_final_answer")
        return final_answer
