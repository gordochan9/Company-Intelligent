from app.graphs.permission_schema.graph import run_get_user_permission_schema
from app.services.permissions import demo_adapter
from app.services.permissions.cache import clear_permission_schema_cache


def setup_function() -> None:
    clear_permission_schema_cache()


def test_missing_identity_fails_closed() -> None:
    result = run_get_user_permission_schema({"request_id": "req-missing"})

    assert result["access_status"] == "access_failed"
    assert result["user_permission_schema"] is None
    assert result["tool_capability_cards"] == []


def test_invalid_identity_fails_closed() -> None:
    result = run_get_user_permission_schema(
        {"openwebui_user_identity": {"email": "intruder@project3.local", "auth_source": "openwebui"}}
    )

    assert result["access_status"] == "access_failed"
    assert result["permission_errors"][0]["code"] == "identity_not_confirmed"


def test_group_adapter_failure_fails_closed(monkeypatch) -> None:
    def fail_groups(_trusted):
        raise RuntimeError("adapter failed")

    monkeypatch.setattr(demo_adapter, "resolve_groups", fail_groups)

    result = run_get_user_permission_schema(
        {"openwebui_user_identity": {"email": "user@demo.com", "auth_source": "openwebui"}}
    )

    assert result["access_status"] == "access_failed"
    assert result["permission_errors"][0]["code"] == "group_resolution_failed"


def test_permission_adapter_failure_fails_closed(monkeypatch) -> None:
    def fail_permissions(_trusted, _groups):
        raise RuntimeError("adapter failed")

    monkeypatch.setattr(demo_adapter, "resolve_source_permissions", fail_permissions)

    result = run_get_user_permission_schema(
        {"openwebui_user_identity": {"email": "user@demo.com", "auth_source": "openwebui"}}
    )

    assert result["access_status"] == "access_failed"
    assert result["permission_errors"][0]["code"] == "permission_resolution_failed"


def test_no_allowed_permissions_returns_denied(monkeypatch) -> None:
    monkeypatch.setattr(demo_adapter, "resolve_source_permissions", lambda _trusted, _groups: [])

    result = run_get_user_permission_schema(
        {"openwebui_user_identity": {"email": "user@demo.com", "auth_source": "openwebui"}}
    )

    assert result["access_status"] == "denied"
    assert result["permission_errors"][0]["code"] == "no_allowed_sources"


def test_invalid_source_metadata_fails_closed(monkeypatch) -> None:
    monkeypatch.setattr(demo_adapter, "resolve_source_permissions", lambda _trusted, _groups: [{"scope": ""}])

    result = run_get_user_permission_schema(
        {"openwebui_user_identity": {"email": "user@demo.com", "auth_source": "openwebui"}}
    )

    assert result["access_status"] == "access_failed"
    assert result["permission_errors"][0]["code"] == "invalid_source_metadata"


def test_tool_capability_cards_do_not_expose_raw_permission_metadata() -> None:
    result = run_get_user_permission_schema(
        {"openwebui_user_identity": {"email": "admin@demo.com", "auth_source": "openwebui"}}
    )

    serialized = repr(result["tool_capability_cards"]).lower()
    assert "allowed_source" not in serialized
    assert "source_id" not in serialized
    assert "raw_acl" not in serialized
