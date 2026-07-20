from __future__ import annotations

import json

import pytest

from app.schemas.join_discovery import JoinDiscoveryRefreshRequest
from app.services import join_discovery_approved_joins
from app.services.join_discovery_approved_joins import (
    build_join_discovery_input_packet,
    build_join_discovery_prompt,
    parse_llm_join_output,
    run_approved_join_discovery_refresh,
    set_join_discovery_model,
)
from app.services.llm_provider import LLMProviderUnavailable, deepseek_join_discovery
from test_join_discovery_llm_candidate_approval import Store, resources


REQUIRED_CANDIDATE_FIELDS = {
    "status",
    "confidence_label",
    "confidence_score",
    "join_type",
    "left_resource_key",
    "left_column_key",
    "right_resource_key",
    "right_column_key",
    "reason",
    "warnings",
    "limitations",
}


@pytest.fixture(autouse=True)
def restore_join_discovery_model():
    original = join_discovery_approved_joins._join_discovery_model
    yield
    set_join_discovery_model(original)


class _Response:
    def __init__(self, body: dict) -> None:
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def read(self) -> bytes:
        return json.dumps(self.body).encode("utf-8")


def _valid_output() -> dict:
    return {
        "status": "completed",
        "joins": [
            {
                "status": "approved",
                "confidence_label": "high",
                "confidence_score": 0.96,
                "join_type": "inner",
                "left_resource_key": "structured:orders",
                "left_column_key": "orders_customer",
                "right_resource_key": "structured:customers",
                "right_column_key": "customers_id",
                "reason": "Stable identifier relationship.",
                "warnings": [],
                "limitations": [],
            }
        ],
        "global_warnings": [],
        "limitations": [],
    }


def _prompt() -> dict:
    packet, errors = build_join_discovery_input_packet(resources(), JoinDiscoveryRefreshRequest())
    assert errors == []
    return build_join_discovery_prompt(packet)


def test_deepseek_join_discovery_sends_complete_input_and_pydantic_output_schema(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        captured["timeout"] = timeout
        return _Response({"choices": [{"message": {"content": json.dumps(_valid_output())}}]})

    monkeypatch.setenv("DEEPSEEK_API_KEY", "configured-test-key")
    monkeypatch.delenv("JOIN_DISCOVERY_LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    prompt = _prompt()

    deepseek_join_discovery(prompt)

    user_payload = json.loads(captured["body"]["messages"][1]["content"])
    assert user_payload["input"] == prompt["payload"]
    assert user_payload["output_schema"] == prompt["output_schema"]
    candidate_schema = user_payload["output_schema"]["$defs"]["LLMJoinCandidate"]
    assert REQUIRED_CANDIDATE_FIELDS <= set(candidate_schema["properties"])
    assert captured["body"]["temperature"] == 0
    assert captured["body"]["response_format"] == {"type": "json_object"}
    assert captured["timeout"] == 600


@pytest.mark.parametrize("configured", ["0", "-1", "not-an-integer"])
def test_join_discovery_timeout_invalid_values_use_safe_default(monkeypatch, configured: str) -> None:
    captured = {}

    def fake_urlopen(_request, timeout):
        captured["timeout"] = timeout
        return _Response({"choices": [{"message": {"content": json.dumps(_valid_output())}}]})

    monkeypatch.setenv("DEEPSEEK_API_KEY", "configured-test-key")
    monkeypatch.setenv("JOIN_DISCOVERY_LLM_TIMEOUT_SECONDS", configured)
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    deepseek_join_discovery(_prompt())

    assert captured["timeout"] == 600


def test_join_discovery_timeout_uses_configured_positive_integer(monkeypatch) -> None:
    captured = {}

    def fake_urlopen(_request, timeout):
        captured["timeout"] = timeout
        return _Response({"choices": [{"message": {"content": json.dumps(_valid_output())}}]})

    monkeypatch.setenv("DEEPSEEK_API_KEY", "configured-test-key")
    monkeypatch.setenv("JOIN_DISCOVERY_LLM_TIMEOUT_SECONDS", "321")
    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)

    deepseek_join_discovery(_prompt())

    assert captured["timeout"] == 321


def test_valid_production_shaped_response_passes_strict_validation() -> None:
    assert parse_llm_join_output(json.dumps(_valid_output())).joins[0].confidence_label == "high"


@pytest.mark.parametrize(
    "model,expected_code",
    [
        (lambda _prompt: "not json", "join_discovery_llm_json_invalid"),
        (lambda _prompt: {"status": "completed", "joins": [{}]}, "join_discovery_llm_schema_invalid"),
        (lambda _prompt: "", "join_discovery_llm_response_empty"),
    ],
)
def test_model_response_failures_have_distinct_safe_codes(model, expected_code: str) -> None:
    set_join_discovery_model(model)

    report = run_approved_join_discovery_refresh(store=Store(resources()))

    assert report.validation_errors == [{"code": expected_code, "message": report.validation_errors[0]["message"]}]


@pytest.mark.parametrize(
    "error,expected_code",
    [
        (LLMProviderUnavailable("provider body with password=secret"), "join_discovery_provider_unavailable"),
        (TimeoutError("provider timed out with api_key=secret"), "join_discovery_provider_timeout"),
    ],
)
def test_provider_failures_have_distinct_safe_codes_and_do_not_leak(error: Exception, expected_code: str) -> None:
    def fail(_prompt):
        raise error

    set_join_discovery_model(fail)

    report = run_approved_join_discovery_refresh(store=Store(resources()))
    rendered = repr(report.as_dict())

    assert report.validation_errors[0]["code"] == expected_code
    for forbidden in [
        "password=secret",
        "api_key=secret",
        "C-100",
        "postgresql://",
        r"C:\Users\Redacted",
        "system_prompt",
        "raw_response",
    ]:
        assert forbidden not in rendered


def test_valid_byod_no_candidates_remains_success() -> None:
    set_join_discovery_model(
        lambda _prompt: {"status": "no_candidates", "joins": [], "global_warnings": [], "limitations": []}
    )

    report = run_approved_join_discovery_refresh(store=Store(resources()))

    assert report.status == "completed_no_approved_joins"
    assert report.exit_code == 0
