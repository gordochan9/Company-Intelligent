from __future__ import annotations

import pytest
from psycopg import errors

from app.services.audit_trace import REDACTED
from app.tools.sql_rag.nodes.adapter import adapter
from app.tools.sql_rag.nodes.final_result_bundle import final_result_bundle
from app.tools.sql_rag.sql.agent import run_sql_workflow
from app.tools.sql_rag.sql.services.executor import set_sql_executor
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
    set_sql_executor(None)
    yield
    set_structured_resources([])
    set_approved_joins([])
    set_sql_intent_model(None)
    set_sql_selector_model(None)
    set_sql_generation_model(None)
    set_sql_executor(None)


@pytest.fixture
def captured_events(monkeypatch):
    events = []
    monkeypatch.setattr("app.services.audit_trace._persist_audit_event", events.append)
    return events


def _resource() -> dict:
    return {
        "resource_key": "structured:products",
        "runtime_relation_name": "products_table",
        "display_name": "Products",
        "columns": [
            {"column_name": "product_name", "data_type": "text", "safe_description": "Product name."},
            {"column_name": "discontinued", "data_type": "text", "safe_description": "Discontinued flag."},
        ],
        "safe_row_samples": [{"product_name": "Chai", "discontinued": "no"}],
        "column_profiles": {"discontinued": {"values": ["yes", "no"]}},
    }


def _state() -> dict:
    return {
        "request_id": "req-audit",
        "trace_id": "trace-audit",
        "step_id": "step_1",
        "sql_question": "How many discontinued products are listed, and what are their names?",
        "step_goal": "Return discontinued product names.",
        "trusted_user_context": {"email": "admin@demo.com"},
        "user_permission_schema": {
            "allowed_resources": {
                "allowed_structured_resources": ["structured:products"],
                "allowed_scopes": ["products"],
            }
        },
        "dependency_context": {},
        "trace": [],
    }


def test_sql_success_emits_troubleshooting_audit_events(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(
        lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1", "table_1_col_2"], "join_keys": []}
    )
    set_sql_generation_model(lambda _payload: {"sql": "SELECT product_name, discontinued FROM products_table LIMIT 10"})
    set_sql_executor(
        lambda _sql, _validated: {
            "columns": ["product_name", "discontinued"],
            "rows": [
                {"product_name": f"Product {index}", "discontinued": "yes", "path": r"C:\Users\Redacted\secret.csv", "api_key": "sk-test-value"}
                for index in range(6)
            ],
        }
    )

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "success"
    event_types = [event.event_type for event in captured_events]
    for event_type in {
        "sql_intake_started",
        "sql_intake_completed",
        "filtered_sql_schema_built",
        "sql_query_intent_built",
        "structured_resource_selection_evaluated",
        "candidate_sql_generated",
        "sql_validation_completed",
        "sql_execution_completed",
        "sql_result_validated",
        "sql_result_emitted",
    }:
        assert event_type in event_types

    candidate_event = next(event for event in captured_events if event.event_type == "candidate_sql_generated")
    assert "candidate_sql" not in candidate_event.metadata
    assert candidate_event.restricted_metadata["candidate_sql"].startswith("SELECT product_name")

    emitted = next(event for event in captured_events if event.event_type == "sql_result_emitted")
    assert "validated_sql" not in emitted.metadata
    assert emitted.restricted_metadata["validated_sql"].startswith("SELECT product_name")
    assert len(emitted.restricted_metadata["row_preview"]) == 5
    assert emitted.restricted_metadata["row_preview"][0]["path"] == REDACTED
    assert emitted.restricted_metadata["row_preview"][0]["api_key"] == REDACTED


def test_sql_failure_emits_failed_node_and_restricted_candidate_sql(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "UPDATE products_table SET product_name = 'blocked'"})

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "validation_failed"
    failure_event = next(event for event in captured_events if event.event_type == "sql_failure_emitted")
    assert failure_event.failure.failed_node == "validate_sql_before_execution"
    assert failure_event.failure.failure_code == "unsafe_sql_operation"
    assert failure_event.metadata["failed_node"] == "validate_sql_before_execution"
    assert "candidate_sql" not in failure_event.metadata
    assert failure_event.restricted_metadata["candidate_sql"].startswith("UPDATE")


def test_sql_execution_failure_emits_safe_execution_and_terminal_audits_once(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT product_name FROM products_table"})
    def executor(_sql: str, _validated: dict) -> dict:
        raise errors.UndefinedColumn("raw database detail: secret_column")

    set_sql_executor(executor)

    result = run_sql_workflow(_state())

    execution_failures = [event for event in captured_events if event.event_type == "sql_execution_failed"]
    terminal_failures = [event for event in captured_events if event.event_type == "sql_failure_emitted"]
    assert len(execution_failures) == 1
    assert execution_failures[0].failure.failure_code == "sql_execution_failed"
    assert execution_failures[0].failure.failed_node == "execute_sql"
    assert len(terminal_failures) == 1
    assert terminal_failures[0].failure.failure_code == "sql_execution_failed"
    assert terminal_failures[0].failure.failed_node == "execute_sql"
    assert "secret_column" not in repr(result)
    assert "secret_column" not in repr(captured_events)


def test_free_sql_intent_audit_records_only_safe_shape_metadata(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(
        lambda _payload: {
            "free_semantics": {"private_filter": "private-value", "expression": "WHERE discontinued = 'yes'"},
            "expected_outputs": ["name"],
            "unexpected_model_key": "must-not-be-audited",
        }
    )
    set_sql_selector_model(
        lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []}
    )
    set_sql_generation_model(lambda _payload: {"sql": "SELECT product_name FROM products_table LIMIT 10"})
    set_sql_executor(lambda _sql, _validated: {"columns": ["product_name"], "rows": [{"product_name": "Chai"}]})

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "success"
    intent_event = next(event for event in captured_events if event.event_type == "sql_query_intent_built")
    assert intent_event.metadata == {
        "intent_status": "built",
        "top_level_field_count": 3,
        "semantic_content_present": True,
    }
    assert intent_event.restricted_metadata == {}
    assert "private-value" not in repr(intent_event)
    assert "must-not-be-audited" not in repr(intent_event)


def test_selector_emits_one_canonical_event_without_public_key_leakage(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"objective": "List products."})
    set_sql_selector_model(
        lambda _payload: {
            "table_keys": ["table_1", "table_missing"],
            "column_keys": ["table_1_col_1", "column_missing"],
            "join_keys": ["join_missing"],
        }
    )
    set_sql_generation_model(lambda _payload: {"sql": "SELECT product_name FROM products_table LIMIT 10"})
    set_sql_executor(lambda _sql, _validated: {"columns": ["product_name"], "rows": [{"product_name": "Chai"}]})

    result = run_sql_workflow(_state())

    selector_events = [event for event in captured_events if event.event_type == "structured_resource_selection_evaluated"]
    assert result["sql_result"]["status"] == "success"
    assert len(selector_events) == 1
    assert not any(event.event_type == "structured_resources_selected" for event in captured_events)
    event = selector_events[0]
    assert "proposed_table_keys" not in event.metadata
    assert event.restricted_metadata["proposed_table_keys"] == ["table_1", "table_missing"]
    assert "table_missing" not in repr(result["sql_result"])


def test_final_result_bundle_and_adapter_log_sql_evidence_preservation(captured_events) -> None:
    bundle_patch = final_result_bundle(
        {
            "request_id": "req-audit",
            "trace_id": "trace-audit",
            "runtime_plan_status": "complete",
            "completed_steps": ["step_1"],
            "runtime_plan": {
                "obligations": [{"obligation_id": "o1", "description": "List products."}],
                "steps": [
                    {
                        "step_id": "step_1",
                        "step_type": "sql",
                        "goal": "List products.",
                        "obligation_ids": ["o1"],
                    }
                ],
            },
            "step_results": [
                {
                    "step_id": "step_1",
                    "step_type": "sql",
                    "status": "success",
                    "validated_output": {
                        "rows": [{"product_name": f"Product {index}"} for index in range(6)],
                        "columns": ["product_name"],
                        "row_count": 6,
                    },
                    "limitations": [],
                    "errors": [],
                }
            ],
        }
    )
    adapted = adapter({"request_id": "req-audit", "trace_id": "trace-audit", **bundle_patch})

    assert adapted["final_answer_context"]["validated_sql_rows"][0] == {"product_name": "Product 0"}
    bundle_event = next(event for event in captured_events if event.event_type == "sql_rag_final_result_bundle_built")
    adapter_event = next(event for event in captured_events if event.event_type == "sql_rag_adapter_completed")
    assert bundle_event.metadata["final_answer_context_sql_row_count"] == 6
    assert adapter_event.metadata["final_answer_context_sql_column_count"] == 1
    assert len(adapter_event.restricted_metadata["structured_result_row_preview"]) == 5
