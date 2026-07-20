from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _headers(token: str = "shared") -> dict[str, str]:
    return {
        "X-Company-Tool-Token": token,
        "X-OpenWebUI-User-Id": "user-1",
        "X-OpenWebUI-User-Email": "admin@demo.com",
        "X-OpenWebUI-User-Name": "Alice",
        "X-OpenWebUI-User-Role": "admin",
    }


def test_openwebui_ask_calls_main_graph_with_question_and_identity(monkeypatch, monkeypatch_context=None) -> None:
    captured: dict = {}
    monkeypatch.setenv("OPENWEBUI_SHARED_SECRET", "shared")

    def graph(state: dict) -> dict:
        captured.update(state)
        return {
            "final_answer": "Done.",
            "final_status": "answered",
            "public_citations": [{"citation_id": "c1"}],
            "public_limitations": [],
            "errors": [],
        }

    monkeypatch.setattr("app.routes.openwebui.run_main_graph", graph)

    response = TestClient(app).post("/openwebui/ask", json={"question": "Question?"}, headers=_headers())

    assert response.status_code == 200
    assert captured["user_question"] == "Question?"
    assert captured["openwebui_user_identity"]["email"] == "admin@demo.com"
    assert captured["openwebui_user_identity"]["role_hint"] == "admin"
    assert response.json() == {
        "final_answer": "Done.",
        "final_status": "answered",
        "public_citations": [{"citation_id": "c1"}],
        "public_limitations": [],
        "errors": [],
    }


def test_openwebui_ask_rejects_missing_or_wrong_transport_token(monkeypatch) -> None:
    called = False
    monkeypatch.setenv("OPENWEBUI_SHARED_SECRET", "shared")

    def graph(_state: dict) -> dict:
        nonlocal called
        called = True
        return {}

    monkeypatch.setattr("app.routes.openwebui.run_main_graph", graph)

    missing = TestClient(app).post("/openwebui/ask", json={"question": "Question?"}, headers={k: v for k, v in _headers().items() if k != "X-Company-Tool-Token"})
    wrong = TestClient(app).post("/openwebui/ask", json={"question": "Question?"}, headers=_headers("wrong"))

    assert missing.status_code == 401
    assert wrong.status_code == 401
    assert called is False


def test_openwebui_ask_rejects_extra_body_permission_fields(monkeypatch) -> None:
    monkeypatch.setenv("OPENWEBUI_SHARED_SECRET", "shared")

    response = TestClient(app).post(
        "/openwebui/ask",
        json={"question": "Question?", "allowed_scopes": ["finance"]},
        headers=_headers(),
    )

    assert response.status_code == 422


def test_openwebui_ask_normalizes_string_limitations(monkeypatch) -> None:
    monkeypatch.setenv("OPENWEBUI_SHARED_SECRET", "shared")

    def graph(_state: dict) -> dict:
        return {
            "final_answer": "Access is limited.",
            "final_status": "insufficient_evidence",
            "public_citations": [],
            "public_limitations": ["Only permitted data is available."],
            "errors": [],
        }

    monkeypatch.setattr("app.routes.openwebui.run_main_graph", graph)

    response = TestClient(app).post("/openwebui/ask", json={"question": "Question?"}, headers=_headers())

    assert response.status_code == 200
    assert response.json()["public_limitations"] == [{"message": "Only permitted data is available."}]
