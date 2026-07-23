from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openwebui_tools.company_intelligent import Tools


class _Response:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps({"final_answer": "Backend answer."}).encode("utf-8")


def test_tools_exposes_exactly_one_public_callable() -> None:
    public_callables = [
        name
        for name in dir(Tools)
        if not name.startswith("_") and callable(getattr(Tools, name))
    ]

    assert public_callables == ["company_intelligent"]
    assert "company_intelligent" in (Tools.__doc__ or "") or "company_intelligent" in (Tools.company_intelligent.__name__)


def test_company_intelligent_posts_question_identity_headers_and_returns_final_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    def urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["headers"] = dict(request.header_items())
        return _Response()

    monkeypatch.setattr("urllib.request.urlopen", urlopen)
    tools = Tools()
    tools.valves.orchestrator_api_base_url = "http://backend.local"
    tools.valves.openwebui_shared_secret = "shared"

    messages = [
        {"role": "user", "content": "Previous question"},
        {"role": "assistant", "content": "Previous answer"},
        {"role": "user", "content": "Question?"},
    ]

    result = tools.company_intelligent(
        "Question?",
        __user__={"id": "user-1", "email": "admin@demo.com", "name": "Alice", "role": "admin"},
        __messages__=messages,
    )

    assert result == "Backend answer."
    assert captured["url"] == "http://backend.local/openwebui/ask"
    assert captured["body"] == {"question": "Question?", "messages": messages}
    assert captured["headers"]["X-company-tool-token"] == "shared"
    assert captured["headers"]["X-openwebui-user-email"] == "admin@demo.com"
    assert captured["timeout"] == 600.0


def test_company_intelligent_fails_without_backend_final_answer(monkeypatch: pytest.MonkeyPatch) -> None:
    class MissingAnswer(_Response):
        def read(self) -> bytes:
            return json.dumps({"message": "bad"}).encode("utf-8")

    monkeypatch.setattr("urllib.request.urlopen", lambda _request, timeout: MissingAnswer())

    with pytest.raises(RuntimeError, match="final_answer"):
        Tools().company_intelligent("Question?", __user__={"email": "admin@demo.com"})
