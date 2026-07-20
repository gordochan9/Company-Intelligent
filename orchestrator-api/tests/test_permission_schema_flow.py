from app.graphs.permission_schema.graph import run_get_user_permission_schema
from app.services.permissions.cache import clear_permission_schema_cache


def _identity(email: str) -> dict:
    return {
        "request_id": "req-flow",
        "trace_id": "trace-flow",
        "openwebui_user_identity": {"email": email, "auth_source": "openwebui"},
        "active_dataset_id": "dataset-1",
        "source_catalog_version": "catalog-1",
    }


def setup_function() -> None:
    clear_permission_schema_cache()


def test_valid_admin_identity_produces_full_allowed_scope_contract() -> None:
    result = run_get_user_permission_schema(_identity("admin@demo.com"))

    assert result["access_status"] == "ok"
    assert result["trusted_user_context"]["email"] == "admin@demo.com"
    allowed = result["user_permission_schema"]["allowed_resources"]["allowed_scopes"]
    assert allowed == ["employee_guidelines", "file_server", "finance", "hr"]
    assert result["tool_capability_cards"] == [
        {
            "tool": "sql_rag",
            "enabled": True,
            "can_search_documents": True,
            "can_query_structured_data": True,
            "limitations": [],
        }
    ]


def test_valid_user_identity_excludes_denied_finance_and_hr_scopes() -> None:
    result = run_get_user_permission_schema(_identity("user@demo.com"))

    assert result["access_status"] == "ok"
    allowed = result["user_permission_schema"]["allowed_resources"]["allowed_scopes"]
    assert allowed == ["employee_guidelines", "file_server"]
    assert "finance" not in allowed
    assert "hr" not in allowed


def test_subgraph_entrypoint_emits_audit_trace_entry() -> None:
    result = run_get_user_permission_schema(_identity("user@demo.com"))

    assert result["trace"]
    assert result["trace"][-1]["workflow_name"] == "permission_schema"
    assert result["trace"][-1]["node_name"] == "emit_permission_schema"
