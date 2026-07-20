import pytest

from app.graphs.permission_schema.graph import get_user_permission_schema_graph, run_get_user_permission_schema
from app.graphs.permission_schema.nodes.build_allowed_resource_map import build_allowed_resource_map
from app.graphs.permission_schema.nodes.emit_permission_schema import emit_permission_schema
from app.graphs.permission_schema.nodes.request_intake import request_intake
from app.graphs.permission_schema.nodes.resolve_trusted_identity import resolve_trusted_identity
from app.graphs.permission_schema.nodes.validate_permission_schema import validate_permission_schema
from app.services.permissions.cache import clear_permission_schema_cache


def setup_function() -> None:
    clear_permission_schema_cache()


def test_entrypoint_is_real_langgraph_compiled_graph() -> None:
    assert hasattr(get_user_permission_schema_graph, "invoke")


def test_request_intake_does_not_require_or_use_user_question() -> None:
    result = request_intake(
        {
            "openwebui_user_identity": {"email": "user@demo.com", "auth_source": "openwebui"},
            "user_question": "ignored by contract",
        }
    )

    assert result["access_status"] == "in_progress"
    assert "user_question" not in result


def test_subgraph_ignores_user_question_input() -> None:
    result = run_get_user_permission_schema(
        {
            "openwebui_user_identity": {"email": "user@demo.com", "auth_source": "openwebui"},
            "user_question": "show me finance data",
        }
    )

    assert result["access_status"] == "ok"
    assert result["user_permission_schema"]["allowed_resources"]["allowed_scopes"] == [
        "employee_guidelines",
        "file_server",
    ]


def test_resolve_trusted_identity_outputs_stable_context() -> None:
    state = request_intake({"openwebui_user_identity": {"email": "user@demo.com", "auth_source": "openwebui"}})
    result = resolve_trusted_identity(state)

    assert result["trusted_user_context"] == {
        "user_id": "project3-demo-user",
        "email": "user@demo.com",
        "display_name": "Project 3.0 Demo User",
        "identity_source": "openwebui",
    }


def test_build_allowed_resource_map_outputs_canonical_keys() -> None:
    result = build_allowed_resource_map(
        {
            "access_status": "in_progress",
            "raw_share_drive_permissions": [{"scope": "finance"}],
        }
    )

    assert set(result["allowed_resource_map"]) == {
        "allowed_scopes",
        "allowed_source_ids",
        "allowed_catalog_entry_ids",
        "allowed_rag_namespaces",
        "allowed_structured_resources",
        "allowed_join_policy_refs",
    }


def test_validate_permission_schema_rejects_missing_required_fields() -> None:
    result = validate_permission_schema(
        {
            "access_status": "in_progress",
            "trusted_user_context": {"email": "user@demo.com"},
            "user_permission_schema": {"schema_version": "3.0"},
        }
    )

    assert result["access_status"] == "permission_schema_failed"


def test_emit_permission_schema_returns_main_graph_contract_fields() -> None:
    result = emit_permission_schema(
        {
            "request_id": "req-contract",
            "trace_id": "trace-contract",
            "access_status": "access_failed",
            "trusted_user_context": None,
            "permission_errors": [{"code": "x", "message": "safe"}],
        }
    )

    assert {"access_status", "trusted_user_context", "user_permission_schema", "tool_capability_cards"}.issubset(result)
    assert result["tool_capability_cards"] == []
