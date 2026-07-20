from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class LLMProviderUnavailable(RuntimeError):
    pass


class LLMProviderTimeout(LLMProviderUnavailable):
    pass


class LLMProviderResponseEmpty(LLMProviderUnavailable):
    pass


def deepseek_json(system_prompt: str, payload: dict[str, Any], *, timeout: int = 60) -> dict[str, Any] | str:
    api_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    if not api_key or api_key == "replace_with_deepseek_api_key":
        raise LLMProviderUnavailable("DeepSeek API key is not configured.")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com").rstrip("/")
    model = os.getenv("LLM_MODEL") or os.getenv("MODEL_NAME") or "deepseek-v4-pro"
    body = json.dumps(
        {
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": json.dumps(payload, sort_keys=True)},
            ],
            "temperature": 0,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")
    request = urllib.request.Request(
        base_url + "/chat/completions",
        data=body,
        method="POST",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except TimeoutError as exc:
        raise LLMProviderTimeout("DeepSeek request timed out.") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, TimeoutError):
            raise LLMProviderTimeout("DeepSeek request timed out.") from exc
        raise LLMProviderUnavailable("DeepSeek request failed.") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise LLMProviderUnavailable("DeepSeek request failed.") from exc
    content = (((raw.get("choices") or [{}])[0].get("message") or {}).get("content") or "").strip()
    if not content:
        raise LLMProviderResponseEmpty("DeepSeek response was empty.")
    return content


def deepseek_tool_selection(system_prompt: str, payload: dict[str, Any]) -> dict[str, Any] | str:
    return deepseek_json(system_prompt, payload)


def deepseek_payload_call(payload: dict[str, Any]) -> dict[str, Any] | str:
    return deepseek_json(payload.get("system_prompt", "Return JSON only."), payload.get("payload", payload))


def deepseek_join_discovery(prompt: dict[str, Any]) -> dict[str, Any] | str:
    return deepseek_json(
        prompt.get("system_prompt", "Return JSON only."),
        {"input": prompt.get("payload", prompt), "output_schema": prompt.get("output_schema", {})},
        timeout=_positive_int_env("JOIN_DISCOVERY_LLM_TIMEOUT_SECONDS", 600),
    )


def _positive_int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default
