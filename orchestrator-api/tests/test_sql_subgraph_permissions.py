from __future__ import annotations

import pytest

from app.tools.sql_rag.sql.agent import run_sql_workflow
from app.tools.sql_rag.sql.nodes.load_approved_join_relationships import load_approved_join_relationships
from app.tools.sql_rag.sql.nodes.read_filtered_sql_schema import read_filtered_sql_schema
from app.tools.sql_rag.sql.nodes.select_relevant_structured_resources import select_relevant_structured_resources
from app.tools.sql_rag.sql.services.schema import build_filtered_schema
from app.tools.sql_rag.sql.services.llm import set_sql_generation_model, set_sql_intent_model, set_sql_selector_model
from app.tools.sql_rag.sql.services.repository import set_approved_joins, set_structured_resources


@pytest.fixture(autouse=True)
def reset_sql_services():
    set_structured_resources([])
    set_approved_joins([])
    set_sql_intent_model(None)
    set_sql_selector_model(
        lambda payload: {
            field: payload["payload"]["sql_query_intent"].get(field, [])
            for field in ("table_keys", "column_keys", "join_keys")
        }
    )
    set_sql_generation_model(None)
    yield
    set_structured_resources([])
    set_approved_joins([])
    set_sql_intent_model(None)
    set_sql_selector_model(None)
    set_sql_generation_model(None)


def _state() -> dict:
    return {
        "request_id": "req-sql-security",
        "step_id": "step_1",
        "sql_question": "How many invoices are overdue?",
        "step_goal": "Count overdue invoices.",
        "trusted_user_context": {"email": "user@demo.com"},
        "user_permission_schema": {"allowed_resources": {"allowed_structured_resources": ["structured:finance"]}},
        "dependency_context": {},
        "trace": [],
    }


def test_missing_permission_schema_returns_access_failed() -> None:
    state = _state()
    state.pop("user_permission_schema")

    result = run_sql_workflow(state)

    assert result["sql_result"]["status"] == "access_failed"
    assert result["sql_result"]["errors"][0]["code"] == "missing_permission_context"


def test_denied_structured_resource_is_not_exposed_or_selectable() -> None:
    set_structured_resources(
        [
            {
                "resource_key": "structured:finance",
                "runtime_relation_name": "finance_table",
                "display_name": "Finance",
                "columns": [{"column_name": "amount", "data_type": "numeric"}],
            },
            {
                "resource_key": "structured:hr",
                "runtime_relation_name": "hr_table",
                "display_name": "HR",
                "columns": [{"column_name": "salary", "data_type": "numeric"}],
            },
        ]
    )
    captured_selector = {}
    set_sql_intent_model(lambda _payload: {"objective": "Return salary values."})

    def selector_model(payload: dict) -> dict:
        captured_selector.update(payload)
        return {"table_keys": ["table_2"], "column_keys": ["table_2_col_1"], "join_keys": []}

    set_sql_selector_model(selector_model)

    result = run_sql_workflow(_state())

    assert result["llm_readable_sql_schema"]["structured_resources"][0]["table_key"] == "table_1"
    assert result["llm_readable_sql_schema"]["structured_resources"][0]["display_name"] == "Finance"
    assert result["sql_result"]["status"] == "insufficient_evidence"
    assert [item["display_name"] for item in captured_selector["payload"]["filtered_sql_schema"]["structured_resources"]] == [
        "Finance"
    ]
    assert "HR" not in repr(captured_selector)


def test_approved_join_loader_filters_denied_and_invalid_joins() -> None:
    resources = [
        {
            "resource_key": "structured:finance",
            "permission_scope_key": "finance",
            "runtime_relation_name": "finance_table",
            "display_name": "Finance",
            "columns": [{"column_name": "customer_id", "data_type": "text"}],
        },
        {
            "resource_key": "structured:customers",
            "permission_scope_key": "finance",
            "runtime_relation_name": "customers_table",
            "display_name": "Customers",
            "columns": [{"column_name": "id", "data_type": "text"}],
        },
        {
            "resource_key": "structured:hr",
            "permission_scope_key": "hr",
            "runtime_relation_name": "hr_table",
            "display_name": "HR",
            "columns": [{"column_name": "employee_id", "data_type": "text"}],
        },
    ]
    set_approved_joins(
        [
            {
                "left_resource_key": "structured:finance",
                "left_column_name": "customer_id",
                "right_resource_key": "structured:customers",
                "right_column_name": "id",
                "join_type": "inner",
            },
            {
                "left_resource_key": "structured:finance",
                "left_column_name": "customer_id",
                "right_resource_key": "structured:hr",
                "right_column_name": "employee_id",
                "join_type": "inner",
            },
            {
                "left_resource_key": "structured:finance",
                "left_column_name": "missing_customer_id",
                "right_resource_key": "structured:customers",
                "right_column_name": "id",
                "join_type": "inner",
            },
        ]
    )
    schema = build_filtered_schema(
        request_id="req",
        step_id="step",
        user_permission_schema={
            "allowed_resources": {
                "allowed_scopes": ["finance"],
                "allowed_structured_resources": [],
            }
        },
        resources=resources,
    )

    result = load_approved_join_relationships({"filtered_sql_schema": schema, "audit_metadata": {}})

    assert len(result["filtered_sql_schema"]["approved_joins"]) == 1
    assert result["audit_metadata"]["total_active_approved_join_count"] == 3
    assert result["audit_metadata"]["permission_filtered_join_count"] == 1
    assert result["audit_metadata"]["dropped_denied_join_count"] == 1
    assert result["audit_metadata"]["dropped_invalid_metadata_join_count"] == 1
    readable = read_filtered_sql_schema(result)["llm_readable_sql_schema"]
    assert readable["approved_join_policy"] == "optional_verified_hints"
    assert len(readable["approved_joins"]) == 1

    selected = select_relevant_structured_resources(
        {
            "filtered_sql_schema": result["filtered_sql_schema"],
            "sql_query_intent": {
                "table_keys": ["table_1", "table_2"],
                "column_keys": ["table_1_col_1", "table_2_col_1"],
                "join_keys": ["join_1"],
                "filters": [],
            },
        }
    )
    assert len(selected["selected_resources"]["joins"]) == 1


def test_allowed_scope_exposes_import_style_structured_resource_key() -> None:
    schema = build_filtered_schema(
        request_id="req",
        step_id="step",
        user_permission_schema={"allowed_resources": {"allowed_scopes": ["finance"], "allowed_structured_resources": []}},
        resources=[
            {
                "resource_key": "structured:finance:orders",
                "permission_scope_key": "finance",
                "runtime_relation_name": "structured_finance_orders",
                "display_name": "Orders",
                "columns": [{"column_name": "amount", "data_type": "text"}],
            }
        ],
    )

    assert [item["resource_key"] for item in schema["structured_resources"]] == ["structured:finance:orders"]


def test_denied_scope_hides_import_style_structured_resource_key() -> None:
    schema = build_filtered_schema(
        request_id="req",
        step_id="step",
        user_permission_schema={"allowed_resources": {"allowed_scopes": ["file_server"], "allowed_structured_resources": []}},
        resources=[
            {
                "resource_key": "structured:finance:orders",
                "permission_scope_key": "finance",
                "runtime_relation_name": "structured_finance_orders",
                "display_name": "Orders",
                "columns": [{"column_name": "amount", "data_type": "text"}],
            }
        ],
    )

    assert schema["structured_resources"] == []


def test_exact_allowed_structured_resource_still_exposes_resource() -> None:
    schema = build_filtered_schema(
        request_id="req",
        step_id="step",
        user_permission_schema={"allowed_resources": {"allowed_scopes": [], "allowed_structured_resources": ["structured:finance"]}},
        resources=[
            {
                "resource_key": "structured:finance",
                "permission_scope_key": "finance",
                "runtime_relation_name": "finance_table",
                "display_name": "Finance",
                "columns": [{"column_name": "amount", "data_type": "text"}],
            }
        ],
    )

    assert [item["resource_key"] for item in schema["structured_resources"]] == ["structured:finance"]
