import asyncio
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from openwebui_functions.company_intelligent_pipe import Pipe, SAFE_TRANSPORT_ERROR


class FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def run_pipe(pipe, body, user=None, metadata=None):
    return asyncio.run(pipe.pipe(body, __user__=user, __metadata__=metadata))


def test_pipe_posts_metadata_user_prompt_to_openwebui_ask(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"final_answer": "answer from backend"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pipe = Pipe()
    pipe.valves.orchestrator_api_base_url = "http://backend.local"
    pipe.valves.openwebui_shared_secret = "secret-value"
    pipe.valves.request_timeout_seconds = 7

    result = run_pipe(
        pipe,
        {"messages": [{"role": "user", "content": "wrapped prompt"}]},
        metadata={"user_prompt": "real prompt"},
    )

    assert result == "answer from backend"
    assert captured["url"] == "http://backend.local/openwebui/ask"
    assert captured["timeout"] == 7
    assert captured["body"] == {"question": "real prompt"}


def test_pipe_default_timeout_is_600_seconds(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["timeout"] = timeout
        return FakeResponse({"final_answer": "answer from backend"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)

    result = run_pipe(Pipe(), {"messages": [{"role": "user", "content": "question"}]})

    assert result == "answer from backend"
    assert captured["timeout"] == 600.0


def test_pipe_falls_back_to_latest_user_message(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse({"final_answer": "latest answer"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pipe = Pipe()

    result = run_pipe(
        pipe,
        {
            "messages": [
                {"role": "user", "content": "first"},
                {"role": "assistant", "content": "middle"},
                {"role": "user", "content": "latest"},
            ]
        },
    )

    assert result == "latest answer"
    assert captured["body"] == {"question": "latest"}


def test_pipe_sends_existing_identity_headers(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        return FakeResponse({"final_answer": "ok"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pipe = Pipe()
    pipe.valves.openwebui_shared_secret = "shared"

    result = run_pipe(
        pipe,
        {"messages": [{"role": "user", "content": "question"}]},
        user={
            "id": "u1",
            "email": "user@example.com",
            "display_name": "User Name",
            "role": "admin",
            "ignored": "not forwarded",
        },
    )

    assert result == "ok"
    assert captured["headers"]["X-company-tool-token"] == "shared"
    assert captured["headers"]["X-openwebui-user-id"] == "u1"
    assert captured["headers"]["X-openwebui-user-email"] == "user@example.com"
    assert captured["headers"]["X-openwebui-user-name"] == "User Name"
    assert captured["headers"]["X-openwebui-user-role"] == "admin"
    assert "ignored" not in captured["headers"]


def test_pipe_returns_only_final_answer(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse(
            {
                "final_answer": "public answer",
                "raw_sql": "select secret",
                "trusted_access_context": {"leak": True},
            }
        )

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pipe = Pipe()

    result = run_pipe(pipe, {"messages": [{"role": "user", "content": "question"}]})

    assert result == "public answer"


def test_pipe_transport_error_is_generic_and_public_safe(monkeypatch):
    def fake_urlopen(request, timeout):
        raise urllib.error.URLError("backend said raw secret and SQL")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pipe = Pipe()
    pipe.valves.openwebui_shared_secret = "shared-secret"

    result = run_pipe(
        pipe,
        {"messages": [{"role": "user", "content": "sensitive question"}]},
        user={"id": "raw-user"},
    )

    assert result == SAFE_TRANSPORT_ERROR
    assert "backend said" not in result
    assert "sensitive question" not in result
    assert "shared-secret" not in result
    assert "raw-user" not in result


def test_pipe_missing_final_answer_returns_generic_error(monkeypatch):
    def fake_urlopen(request, timeout):
        return FakeResponse({"debug": "internal state"})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    pipe = Pipe()

    result = run_pipe(pipe, {"messages": [{"role": "user", "content": "question"}]})

    assert result == SAFE_TRANSPORT_ERROR
    assert "internal state" not in result
