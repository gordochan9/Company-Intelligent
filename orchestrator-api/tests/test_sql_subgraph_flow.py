from __future__ import annotations

import pytest
from psycopg import OperationalError, errors

from app.tools.sql_rag.sql.agent import run_sql_workflow
from app.tools.sql_rag.sql.nodes.select_relevant_structured_resources import select_relevant_structured_resources
from app.tools.sql_rag.sql.services.executor import set_sql_executor
from app.tools.sql_rag.sql.services.llm import set_sql_generation_model, set_sql_intent_model, set_sql_selector_model
from app.tools.sql_rag.sql.services.repository import set_approved_joins, set_structured_resources
from app.tools.sql_rag.sql.services.validation import count_unbound_sql_parameters


def _selection_from_intent(payload: dict) -> dict:
    intent = payload["payload"]["sql_query_intent"]
    return {field: intent.get(field, []) for field in ("table_keys", "column_keys", "join_keys")}


@pytest.fixture(autouse=True)
def reset_sql_services():
    set_structured_resources([])
    set_approved_joins([])
    set_sql_intent_model(None)
    set_sql_selector_model(_selection_from_intent)
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
        "resource_key": "structured:finance",
        "runtime_relation_name": "finance_table",
        "display_name": "Finance",
        "columns": [
            {"column_name": "amount", "data_type": "numeric", "safe_description": "Invoice amount."},
            {"column_name": "status", "data_type": "text", "safe_description": "Invoice status."},
        ],
        "safe_row_samples": [{"amount": "100", "status": "overdue"}],
        "column_profiles": {"amount": {"kind": "numeric"}},
    }


def _state() -> dict:
    return {
        "request_id": "req-sql",
        "trace_id": "trace-sql",
        "step_id": "step_1",
        "sql_question": "Which invoice amounts are overdue?",
        "step_goal": "Return overdue invoice amounts.",
        "trusted_user_context": {"email": "admin@demo.com"},
        "user_permission_schema": {
            "allowed_resources": {
                "allowed_structured_resources": ["structured:finance"],
            }
        },
        "obligations": [],
        "dependency_context": {},
        "trace": [],
    }


def _selector_state(selection: dict, *, approved_joins: list[dict] | None = None) -> dict:
    set_sql_selector_model(lambda _payload: selection)
    schema = {
        "structured_resources": [
            {
                "table_key": "table_1",
                "resource_key": "structured:finance",
                "runtime_relation_name": "finance_table",
                "display_name": "Finance",
                "columns": [
                    {"column_key": "table_1_col_1", "column_name": "amount", "data_type": "numeric"},
                ],
            },
            {
                "table_key": "table_2",
                "resource_key": "structured:hr",
                "runtime_relation_name": "hr_table",
                "display_name": "HR",
                "columns": [
                    {"column_key": "table_2_col_1", "column_name": "employee_id", "data_type": "text"},
                ],
            },
        ],
        "approved_joins": approved_joins or [],
    }
    return {
        "request_id": "req-selector-audit",
        "trace_id": "trace-selector-audit",
        "sql_query_intent": {"objective": "Answer the analytical question."},
        "filtered_sql_schema": schema,
        "llm_readable_sql_schema": schema,
    }


def _selector_event(captured_events):
    events = [event for event in captured_events if event.event_type == "structured_resource_selection_evaluated"]
    assert len(events) == 1
    assert not any(event.event_type == "structured_resources_selected" for event in captured_events)
    return events[0]


def test_valid_sql_step_returns_success_with_validated_rows_and_hash() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT amount FROM finance_table LIMIT 10"})
    set_sql_executor(
        lambda _sql, _validated: {
            "columns": ["amount"],
            "rows": [{"amount": 100}],
            "calculation_metadata": {"operation": "projection"},
            "restricted_reader": True,
            "rls_enforced": True,
        }
    )

    result = run_sql_workflow(_state())

    sql_result = result["sql_result"]
    assert sql_result["status"] == "success"
    assert sql_result["validated_output"]["rows"] == [{"amount": 100}]
    assert sql_result["validated_output"]["columns"] == ["amount"]
    assert sql_result["validated_output"]["row_count"] == 1
    assert isinstance(sql_result["validated_output"]["sql_hash"], str)
    assert "SELECT amount" not in repr(sql_result)


def test_execution_boundary_passes_scope_and_exact_resource_permissions() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT amount FROM finance_table"})
    captured: dict = {}

    def executor(_sql: str, validated: dict) -> dict:
        captured.update(validated)
        return {"columns": ["amount"], "rows": []}

    state = _state()
    state["user_permission_schema"]["allowed_resources"]["allowed_scopes"] = ["finance"]
    set_sql_executor(executor)

    result = run_sql_workflow(state)

    assert result["sql_result"]["status"] == "success"
    assert captured["permission_scope_keys"] == ["finance"]
    assert captured["permission_resource_keys"] == ["structured:finance"]


def test_sql_models_receive_bounded_prompts() -> None:
    set_structured_resources([_resource()])
    captured_intent: dict = {}
    captured_selector: dict = {}
    selector_calls = []
    captured_generation: dict = {}

    def intent_model(payload: dict) -> dict:
        captured_intent.update(payload)
        return {"objective": "Return overdue invoice amounts.", "filters": [{"status": "overdue"}]}

    def selector_model(payload: dict) -> dict:
        selector_calls.append(payload)
        captured_selector.update(payload)
        return {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []}

    def generation_model(payload: dict) -> dict:
        captured_generation.update(payload)
        return {"sql": "SELECT amount FROM finance_table LIMIT 10"}

    set_sql_intent_model(intent_model)
    set_sql_selector_model(selector_model)
    set_sql_generation_model(generation_model)
    set_sql_executor(lambda _sql, _validated: {"columns": ["amount"], "rows": [{"amount": 100}]})

    run_sql_workflow(_state())

    assert "system_prompt" in captured_intent
    assert "payload" in captured_intent
    assert "filtered_sql_schema" not in captured_intent["payload"]
    assert "JSON object" in captured_intent["system_prompt"]
    assert "resource selection" not in captured_intent["system_prompt"].lower()
    assert "Do not produce candidate SQL" in captured_intent["system_prompt"]
    assert captured_selector["payload"]["sql_query_intent"] == {
        "objective": "Return overdue invoice amounts.",
        "filters": [{"status": "overdue"}],
    }
    assert captured_selector["payload"]["filtered_sql_schema"]["structured_resources"][0]["table_key"] == "table_1"
    assert captured_selector["payload"]["filtered_sql_schema"]["approved_join_policy"] == "optional_verified_hints"
    assert set(captured_selector["payload"]["output_schema"]["required"]) == {"table_keys", "column_keys", "join_keys"}
    assert captured_selector["payload"]["output_schema"]["additionalProperties"] is False
    assert captured_selector["payload"]["output_schema"]["properties"]["table_keys"]["items"]["enum"] == ["table_1"]
    assert captured_selector["payload"]["output_schema"]["properties"]["column_keys"]["items"]["enum"] == [
        "table_1_col_1",
        "table_1_col_2",
    ]
    assert captured_selector["payload"]["output_schema"]["properties"]["join_keys"]["items"]["enum"] == []
    assert "derived metric" in captured_selector["system_prompt"]
    assert "adjustment" in captured_selector["system_prompt"]
    assert "human-readable label" in captured_selector["system_prompt"]
    assert "opaque identifier alone" in captured_selector["system_prompt"]
    assert len(selector_calls) == 1
    assert "system_prompt" in captured_generation
    assert "payload" in captured_generation
    assert captured_generation["payload"]["selected_resources"]["tables"][0]["runtime_relation_name"] == "finance_table"
    assert "SELECT" in captured_generation["system_prompt"]
    assert "exactly one non-empty read-only PostgreSQL query statement" in captured_generation["system_prompt"]
    assert "Do not return multiple semicolon-separated statements" in captured_generation["system_prompt"]
    assert "complete sql_query_intent" in captured_generation["system_prompt"]
    assert "must not omit" in captured_generation["system_prompt"]
    assert "optional verified hints" in captured_generation["system_prompt"]
    assert "reasonable join" in captured_generation["system_prompt"]
    assert 'return {"sql":""}' not in captured_generation["system_prompt"]
    assert "manually join" not in captured_generation["system_prompt"]
    assert "manual join" not in captured_generation["system_prompt"]


def test_q1_style_prompt_allows_reasonable_join_without_approved_join_hints() -> None:
    resources = [
        {
            "resource_key": "structured:categories",
            "runtime_relation_name": "categories",
            "display_name": "Categories",
            "columns": [
                {"column_name": "categoryid", "data_type": "text"},
                {"column_name": "categoryname", "data_type": "text"},
            ],
        },
        {
            "resource_key": "structured:products",
            "runtime_relation_name": "products",
            "display_name": "Products",
            "columns": [
                {"column_name": "productid", "data_type": "text"},
                {"column_name": "categoryid", "data_type": "text"},
            ],
        },
        {
            "resource_key": "structured:order_details_2020",
            "runtime_relation_name": "order_details_2020",
            "display_name": "Order Details 2020",
            "columns": [
                {"column_name": "productid", "data_type": "text"},
                {"column_name": "orderprice", "data_type": "text"},
                {"column_name": "quantity", "data_type": "text"},
            ],
        },
    ]
    set_structured_resources(resources)
    state = _state()
    state["user_permission_schema"]["allowed_resources"]["allowed_structured_resources"] = [
        resource["resource_key"] for resource in resources
    ]
    set_sql_intent_model(
        lambda _payload: {
            "table_keys": ["table_1", "table_2", "table_3"],
            "column_keys": [
                "table_1_col_1",
                "table_1_col_2",
                "table_2_col_1",
                "table_2_col_2",
                "table_3_col_1",
                "table_3_col_2",
                "table_3_col_3",
            ],
            "join_keys": [],
            "metric": "",
            "metrics": [],
        }
    )
    captured_generation = {}

    def generation_model(payload: dict) -> dict:
        captured_generation.update(payload)
        return {
            "sql": (
                "SELECT categoryname "
                "FROM categories "
                "LIMIT 3"
            )
        }

    set_sql_generation_model(generation_model)
    set_sql_executor(
        lambda _sql, _validated: {
            "columns": ["categoryname"],
            "rows": [{"categoryname": "A"}],
        }
    )

    result = run_sql_workflow(state)
    selected = captured_generation["payload"]["selected_resources"]

    assert result["sql_result"]["status"] == "success"
    assert selected["joins"] == []
    assert "reasonable join" in captured_generation["system_prompt"]
    assert "manually join" not in captured_generation["system_prompt"]
    assert "manual join" not in captured_generation["system_prompt"]
    assert {column["column_key"] for column in selected["source_columns"]} == {
        "table_1_col_1",
        "table_1_col_2",
        "table_2_col_1",
        "table_2_col_2",
        "table_3_col_1",
        "table_3_col_2",
        "table_3_col_3",
    }
    assert all(
        {column["column_key"] for column in table["columns"]}
        <= {column["column_key"] for column in selected["columns"]}
        for table in selected["tables"]
    )


def test_free_filter_semantics_do_not_create_selector_specific_resources(captured_events) -> None:
    set_structured_resources([_resource()])
    captured_generation: dict = {}

    set_sql_intent_model(
        lambda _payload: {
            "table_keys": ["table_1"],
            "column_keys": ["table_1_col_1", "table_1_col_2"],
            "join_keys": [],
            "filters": [{"column_key": "table_1_col_2", "operator": "=", "value_hint": "overdue"}],
        }
    )

    def generation_model(payload: dict) -> dict:
        captured_generation.update(payload)
        return {"sql": "SELECT amount FROM finance_table WHERE status = 'overdue' LIMIT 10"}

    set_sql_generation_model(generation_model)
    set_sql_executor(lambda _sql, _validated: {"columns": ["amount"], "rows": [{"amount": 100}]})

    result = run_sql_workflow(_state())

    selected = captured_generation["payload"]["selected_resources"]
    selected_column_keys = {column["column_key"] for column in selected["columns"]}
    assert result["sql_result"]["status"] == "success"
    assert selected_column_keys == {"table_1_col_1", "table_1_col_2"}
    assert "filter_columns" not in selected
    assert captured_generation["payload"]["sql_query_intent"]["filters"] == [
        {"column_key": "table_1_col_2", "operator": "=", "value_hint": "overdue"}
    ]
    event = next(item for item in captured_events if item.event_type == "sql_validation_completed")
    assert event.metadata["validation_status"] == "approved"
    assert "unselected_column_count" not in event.metadata
    assert "selected_columns" not in event.restricted_metadata
    assert "referenced_columns" not in event.restricted_metadata


def test_unselected_filter_column_is_left_to_postgresql_rls(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(
        lambda _payload: {
            "table_keys": ["table_1"],
            "column_keys": ["table_1_col_1"],
            "join_keys": [],
        }
    )
    set_sql_generation_model(
        lambda _payload: {
            "sql": 'SELECT "amount" FROM "finance_table" WHERE "status" = \'overdue\' LIMIT 10'
        }
    )
    set_sql_executor(lambda _sql, _validated: {"columns": ["amount"], "rows": [{"amount": 100}]})

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "success"
    event = next(item for item in captured_events if item.event_type == "sql_validation_completed")
    assert event.metadata["validation_status"] == "approved"
    assert "unselected_column_count" not in event.metadata
    assert "selected_columns" not in event.restricted_metadata


def test_missing_executor_fails_after_validation_without_fake_execution() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT amount FROM finance_table LIMIT 10"})

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "error"
    assert result["sql_result"]["errors"][0]["code"] == "sql_executor_unavailable"


def test_empty_sql_result_remains_successful() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT amount FROM finance_table LIMIT 10"})
    set_sql_executor(lambda _sql, _validated: {"columns": ["amount"], "rows": []})

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "success"
    assert result["sql_result"]["validated_output"]["row_count"] == 0
    assert result["sql_result"]["validated_output"]["rows"] == []


def test_multiple_statements_fail_before_execution() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT 1; SELECT 2"})
    attempts = 0

    def executor(_sql: str, _validated: dict) -> dict:
        nonlocal attempts
        attempts += 1
        return {"columns": [], "rows": []}

    set_sql_executor(executor)

    result = run_sql_workflow(_state())

    assert attempts == 0
    assert result["sql_result"]["status"] == "validation_failed"
    assert result["sql_result"]["errors"][0]["code"] == "multiple_sql_statements"
    assert result["sql_result"]["audit_metadata"]["failed_node"] == "validate_sql_before_execution"


@pytest.mark.parametrize(
    ("sql", "expected"),
    [
        ("SELECT * FROM finance_table WHERE amount = $1", 1),
        ("SELECT * FROM finance_table WHERE amount = :amount", 1),
        ("SELECT * FROM finance_table WHERE amount = %s", 1),
        ("SELECT * FROM finance_table WHERE amount = %(amount)s", 1),
        ("SELECT * FROM finance_table WHERE amount = ?", 1),
        ("SELECT * FROM finance_table WHERE amount = $1 OR status = :status", 2),
    ],
)
def test_unbound_parameter_detector_counts_supported_placeholder_forms(sql: str, expected: int) -> None:
    assert count_unbound_sql_parameters(sql) == expected


@pytest.mark.parametrize(
    "sql",
    [
        "SELECT orderdate::date FROM finance_table",
        "SELECT '$1', ':name', '%s', '?'",
        "SELECT $$ $1 :name ? $$",
        "SELECT 1 -- $1\n",
        "SELECT payload ? 'key' FROM finance_table",
        "SELECT payload ?| ARRAY['a', 'b'] FROM finance_table",
        "SELECT payload ?& ARRAY['a', 'b'] FROM finance_table",
    ],
)
def test_unbound_parameter_detector_ignores_postgresql_non_parameters(sql: str) -> None:
    assert count_unbound_sql_parameters(sql) == 0


def test_unbound_parameter_regenerates_once_then_executes_bound_free_sql(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(
        lambda _payload: {
            "table_keys": ["table_1"],
            "column_keys": ["table_1_col_1", "table_1_col_2"],
            "join_keys": [],
            "goal": "Return the requested amount for the validated status.",
        }
    )
    candidates = iter(
        [
            {"sql": "SELECT amount FROM finance_table WHERE status = :status"},
            {"sql": "SELECT amount FROM finance_table WHERE status = 'overdue'"},
        ]
    )
    generation_payloads: list[dict] = []
    executed: list[str] = []

    def generation_model(payload: dict) -> dict:
        generation_payloads.append(payload)
        return next(candidates)

    set_sql_generation_model(generation_model)
    set_sql_executor(
        lambda sql, _validated: executed.append(sql)
        or {"columns": ["amount"], "rows": [{"amount": 100}]}
    )

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "success"
    assert len(generation_payloads) == 2
    assert generation_payloads[1]["payload"]["validation_feedback_code"] == "unbound_sql_parameter"
    assert executed == ["SELECT amount FROM finance_table WHERE status = 'overdue'"]
    generated = [event for event in captured_events if event.event_type == "candidate_sql_generated"]
    assert [event.metadata["parameter_count"] for event in generated] == [1, 0]
    rejected = [event for event in captured_events if event.event_type == "sql_validation_failed"]
    assert len(rejected) == 1
    assert rejected[0].failure.failure_code == "unbound_sql_parameter"
    assert rejected[0].metadata["regeneration_scheduled"] is True


def test_repeated_unbound_parameter_fails_without_execution_or_third_generation(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(
        lambda _payload: {
            "table_keys": ["table_1"],
            "column_keys": ["table_1_col_1"],
            "join_keys": [],
        }
    )
    generation_calls = 0
    execution_calls = 0

    def generation_model(_payload: dict) -> dict:
        nonlocal generation_calls
        generation_calls += 1
        return {"sql": f"SELECT amount FROM finance_table WHERE amount = ${generation_calls}"}

    def executor(_sql: str, _validated: dict) -> dict:
        nonlocal execution_calls
        execution_calls += 1
        return {"columns": ["amount"], "rows": [{"amount": 100}]}

    set_sql_generation_model(generation_model)
    set_sql_executor(executor)

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "validation_failed"
    assert result["sql_result"]["errors"][0]["code"] == "unbound_sql_parameter"
    assert generation_calls == 2
    assert execution_calls == 0
    rejected = [event for event in captured_events if event.event_type == "sql_validation_failed"]
    assert len(rejected) == 2
    assert [event.metadata["regeneration_scheduled"] for event in rejected] == [True, False]


def test_empty_candidate_is_retried_once_with_same_context() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    calls: list[dict] = []

    def model(payload: dict) -> dict:
        calls.append(payload)
        return {"sql": ""} if len(calls) == 1 else {"sql": "SELECT amount FROM finance_table"}

    set_sql_generation_model(model)
    set_sql_executor(lambda _sql, _validated: {"columns": ["amount"], "rows": [{"amount": 100}]})

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "success"
    assert len(calls) == 2
    assert calls[0]["payload"] == calls[1]["payload"]
    assert "previous output was empty" in calls[1]["system_prompt"]


def test_second_empty_candidate_fails_without_third_call() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    calls = 0

    def model(_payload: dict) -> dict:
        nonlocal calls
        calls += 1
        return {"sql": "  "}

    set_sql_generation_model(model)

    result = run_sql_workflow(_state())

    assert calls == 2
    assert result["sql_result"]["errors"][0]["code"] == "empty_candidate_query"


def test_malformed_candidate_and_provider_error_are_not_retried() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    calls = 0

    def malformed(_payload: dict) -> str:
        nonlocal calls
        calls += 1
        return "not-json"

    set_sql_generation_model(malformed)
    malformed_result = run_sql_workflow(_state())
    assert calls == 1
    assert malformed_result["sql_result"]["errors"][0]["code"] == "unreadable_candidate_query"

    def provider_error(_payload: dict) -> dict:
        nonlocal calls
        calls += 1
        raise RuntimeError("provider failed")

    calls = 0
    set_sql_generation_model(provider_error)
    provider_result = run_sql_workflow(_state())
    assert calls == 1
    assert provider_result["sql_result"]["errors"][0]["code"] == "sql_generation_model_unavailable"


@pytest.mark.parametrize("database_error", [errors.UndefinedColumn, errors.UndefinedTable])
def test_expected_postgresql_execution_error_returns_safe_failure(database_error: type[Exception]) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT amount FROM finance_table"})
    attempts = 0

    def executor(_sql: str, _validated: dict) -> dict:
        nonlocal attempts
        attempts += 1
        raise database_error("raw database detail: secret_identifier")

    set_sql_executor(executor)

    result = run_sql_workflow(_state())

    sql_result = result["sql_result"]
    assert attempts == 1
    assert sql_result["status"] == "validation_failed"
    assert sql_result["errors"] == [{"code": "sql_execution_failed", "message": "SQL execution failed."}]
    assert sql_result["audit_metadata"]["failed_node"] == "execute_sql"
    assert sql_result["validated_output"]["rows"] == []
    assert sql_result["validated_output"]["row_count"] == 0
    assert "secret_identifier" not in repr(result)


def test_insufficient_privilege_uses_existing_access_failed_path() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT amount FROM finance_table"})
    def executor(_sql: str, _validated: dict) -> dict:
        raise errors.InsufficientPrivilege("raw denied relation")

    set_sql_executor(executor)

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "access_failed"
    assert result["sql_result"]["errors"][0]["code"] == "restricted_sql_access_failed"
    assert "raw denied relation" not in repr(result)


def test_operational_error_uses_existing_executor_unavailable_path() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT amount FROM finance_table"})
    def executor(_sql: str, _validated: dict) -> dict:
        raise OperationalError("raw connection detail")

    set_sql_executor(executor)

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "error"
    assert result["sql_result"]["errors"][0]["code"] == "sql_executor_unavailable"
    assert "raw connection detail" not in repr(result)


def test_arbitrary_executor_programming_error_is_not_reclassified() -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    set_sql_generation_model(lambda _payload: {"sql": "SELECT amount FROM finance_table"})
    def executor(_sql: str, _validated: dict) -> dict:
        raise TypeError("programming error")

    set_sql_executor(executor)

    with pytest.raises(TypeError, match="programming error"):
        run_sql_workflow(_state())


def test_semantic_intent_and_dependency_context_are_transported_to_sql_generation() -> None:
    set_structured_resources([_resource()])
    state = _state()
    state.update(
        {
            "obligations": [{"obligation_id": "o1", "description": "Calculate the overdue rate."}],
            "dependency_context": {
                "step_0": {
                    "validated_output": {
                        "rows": [{"employee_name": "Laura Callahan", "sales_revenue": "8761.6200"}],
                        "columns": ["employee_name", "sales_revenue"],
                        "row_count": 1,
                    }
                }
            },
        }
    )
    captured_intent: dict = {}
    captured_selector: dict = {}
    captured_generation: dict = {}

    def intent_model(payload: dict) -> dict:
        captured_intent.update(payload)
        return {
            "table_keys": ["table_1"],
            "column_keys": ["table_1_col_1", "table_1_col_2"],
            "join_keys": [],
            "metric": "overdue rate",
            "filters": [],
            "population": "Invoices belonging to the validated winner.",
            "validated_dependency": {
                "employee_name": "Laura Callahan",
                "june_2021_sales_revenue": "8761.6200",
                "calculation_role": "numerator for the requested company-revenue percentage",
            },
            "metrics": [
                {
                    "name": "overdue_count",
                    "aggregation": "count",
                    "output_name": "overdue_count",
                    "condition": "Invoices with overdue status.",
                    "condition_column_keys": ["table_1_col_2"],
                    "value_description": "Qualifying invoice rows.",
                    "value_column_keys": [],
                    "numerator_metric": "",
                    "denominator_metric": "",
                },
                {
                    "name": "total_count",
                    "aggregation": "count",
                    "output_name": "total_count",
                    "condition": "All invoices in the population.",
                    "condition_column_keys": [],
                    "value_description": "All invoice rows.",
                    "value_column_keys": [],
                    "numerator_metric": "",
                    "denominator_metric": "",
                },
                {
                    "name": "overdue_rate",
                    "aggregation": "rate",
                    "output_name": "overdue_rate",
                    "condition": "Rate over the full invoice population.",
                    "condition_column_keys": [],
                    "value_description": "Overdue count divided by total count.",
                    "value_column_keys": [],
                    "numerator_metric": "overdue_count",
                    "denominator_metric": "total_count",
                },
            ],
            "grouping": [],
            "ranking": {"by_output": "overdue_rate", "direction": "desc", "top_n": 1},
            "arbitrary_nested_semantics": {"expression": "WHERE status = 'overdue'", "confidence": None},
            "expected_outputs": ["overdue_rate"],
        }

    def selector_model(payload: dict) -> dict:
        captured_selector.update(payload)
        return {
            field: payload["payload"]["sql_query_intent"].get(field, [])
            for field in ("table_keys", "column_keys", "join_keys")
        }

    def generation_model(payload: dict) -> dict:
        captured_generation.update(payload)
        return {
            "sql": (
                "SELECT COUNT(*) FILTER (WHERE status = 'overdue') AS overdue_count, "
                "COUNT(*) AS total_count, "
                "COUNT(*) FILTER (WHERE status = 'overdue')::numeric / NULLIF(COUNT(*), 0) AS overdue_rate "
                "FROM finance_table ORDER BY overdue_rate DESC LIMIT 1"
            )
        }

    set_sql_intent_model(intent_model)
    set_sql_selector_model(selector_model)
    set_sql_generation_model(generation_model)
    set_sql_executor(
        lambda _sql, _validated: {
            "columns": ["overdue_count", "total_count", "overdue_rate"],
            "rows": [{"overdue_count": 2, "total_count": 5, "overdue_rate": 0.4}],
        }
    )

    result = run_sql_workflow(state)

    assert result["sql_result"]["status"] == "success"
    assert captured_intent["payload"]["obligations"] == state["obligations"]
    assert "required_inputs" not in captured_intent["payload"]
    assert "expected_outputs" not in captured_intent["payload"]
    assert captured_intent["payload"]["dependency_context"] == state["dependency_context"]
    intent_prompt = captured_intent["system_prompt"]
    assert "Preserve every validated dependency value needed by the current calculation exactly" in intent_prompt
    assert "Do not describe an available applicable dependency value as unknown or missing" in intent_prompt
    assert "dependency_context" not in captured_selector["payload"]
    assert captured_generation["payload"]["sql_query_intent"]["population"] == "Invoices belonging to the validated winner."
    assert captured_generation["payload"]["sql_query_intent"]["validated_dependency"] == {
        "employee_name": "Laura Callahan",
        "june_2021_sales_revenue": "8761.6200",
        "calculation_role": "numerator for the requested company-revenue percentage",
    }
    assert "dependency_context" not in captured_generation["payload"]
    assert "filtered_sql_schema" not in captured_generation["payload"]
    assert captured_generation["payload"]["sql_query_intent"]["arbitrary_nested_semantics"] == {
        "expression": "WHERE status = 'overdue'",
        "confidence": None,
    }
    assert captured_generation["payload"]["sql_query_intent"]["expected_outputs"] == ["overdue_rate"]
    prompt = captured_generation["system_prompt"]
    assert "Use WHERE for conditions that define the row population" in prompt
    assert "aggregate FILTER or CASE WHEN" in prompt
    assert "NULLIF or an equivalent safe denominator guard" in prompt
    assert "fully executable exactly as emitted" in prompt
    assert "Do not emit unbound parameter placeholders" in prompt
    assert "Do not return NULL for a requested result when its required inputs are available" in prompt
    assert "ranking" in prompt
    assert "stable aliases" in prompt


def test_expected_outputs_is_opaque_and_does_not_change_build_contract() -> None:
    set_structured_resources([_resource()])
    state = _state()
    captured_generation: dict = {}
    set_sql_intent_model(
        lambda _payload: {
            "table_keys": ["table_1"],
            "column_keys": ["table_1_col_1"],
            "join_keys": [],
            "expected_outputs": ["different_alias"],
        }
    )
    set_sql_generation_model(lambda payload: captured_generation.update(payload) or {"sql": "SELECT amount FROM finance_table LIMIT 10"})
    set_sql_executor(lambda _sql, _validated: {"columns": ["amount"], "rows": [{"amount": 100}]})

    result = run_sql_workflow(state)

    assert result["sql_result"]["status"] == "success"
    assert captured_generation["payload"]["sql_query_intent"]["expected_outputs"] == ["different_alias"]


@pytest.mark.parametrize("intent", [{}, {"nested": []}, {"value": None}])
def test_empty_semantic_intent_fails_in_build_node(intent: dict) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: intent)
    set_sql_generation_model(lambda _payload: pytest.fail("Generator should not run"))

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "error"
    assert result["sql_result"]["errors"][0]["code"] == "invalid_sql_intent"
    assert result["sql_result"]["audit_metadata"]["failed_node"] == "build_sql_query_intent"


@pytest.mark.parametrize("raw_intent", ["not json", "[]", '"scalar"', "1", "true", "null", [], None])
def test_non_object_intent_fails_closed_in_build_node(raw_intent: object) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: raw_intent)
    set_sql_generation_model(lambda _payload: pytest.fail("Generator should not run"))

    result = run_sql_workflow(_state())

    assert result["sql_result"]["status"] == "error"
    assert result["sql_result"]["errors"] == [
        {"code": "invalid_sql_intent", "message": "SQL query intent is invalid."}
    ]
    assert result["sql_result"]["audit_metadata"]["failed_node"] == "build_sql_query_intent"


@pytest.mark.parametrize(
    "selection",
    [
        {},
        {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"]},
        {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": [], "extra": True},
        {"table_keys": "table_1", "column_keys": ["table_1_col_1"], "join_keys": []},
        {"table_keys": ["table_1", 1], "column_keys": ["table_1_col_1"], "join_keys": []},
        {"table_keys": ["table_1"], "column_keys": [""], "join_keys": []},
        {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": [None]},
    ],
)
def test_strict_selector_output_fails_closed(selection: dict, captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"objective": "Return invoice amounts."})
    set_sql_selector_model(lambda _payload: selection)
    set_sql_generation_model(lambda _payload: pytest.fail("Generator should not run"))

    result = run_sql_workflow(_state())

    event = _selector_event(captured_events)
    assert result["sql_result"]["status"] == "validation_failed"
    assert result["sql_result"]["errors"][0]["code"] == "invalid_structured_resource_selection"
    assert event.status.value == "validation_failed"
    assert event.metadata["selection_reason_code"] == "selector_output_invalid"
    assert event.metadata["selector_model_status"] == "succeeded"
    assert event.metadata["selector_parse_status"] == "invalid"
    assert event.metadata["selector_output_schema_valid"] is False
    assert event.metadata["duplicate_table_key_count"] == 0
    assert event.metadata["unknown_column_key_count"] == 0
    assert event.metadata["owner_table_added_count"] == 0
    assert event.metadata["ignored_unknown_join_hint_count"] == 0


def test_selector_model_unavailable_fails_once(captured_events) -> None:
    set_structured_resources([_resource()])
    set_sql_intent_model(lambda _payload: {"objective": "Return invoice amounts."})
    set_sql_selector_model(None)

    result = run_sql_workflow(_state())

    event = _selector_event(captured_events)
    assert result["sql_result"]["errors"][0]["code"] == "sql_selector_model_unavailable"
    assert event.status.value == "failed"
    assert event.metadata["selection_reason_code"] == "selector_model_unavailable"
    assert event.metadata["selector_parse_status"] == "not_started"
    assert event.metadata["duplicate_join_key_count"] == 0
    assert event.metadata["ignored_incomplete_join_hint_count"] == 0
    assert event.duration_ms is not None


def test_selector_valid_subset_adds_column_owner_and_preserves_catalog_order(captured_events) -> None:
    result = select_relevant_structured_resources(
        _selector_state(
            {
                "table_keys": ["table_2", "table_2", "table_missing"],
                "column_keys": ["table_2_col_1", "table_1_col_1", "table_1_col_1", "column_missing"],
                "join_keys": ["join_missing", "join_missing"],
            }
        )
    )

    event = _selector_event(captured_events)
    selected = result["selected_resources"]
    assert [item["table_key"] for item in selected["tables"]] == ["table_1", "table_2"]
    assert [item["column_key"] for item in selected["source_columns"]] == ["table_1_col_1", "table_2_col_1"]
    assert event.metadata["duplicate_table_key_count"] == 1
    assert event.metadata["duplicate_column_key_count"] == 1
    assert event.metadata["duplicate_join_key_count"] == 1
    assert event.metadata["owner_table_added_count"] == 1
    assert event.metadata["unmatched_table_key_count"] == 1
    assert event.metadata["matched_table_key_count"] + event.metadata["unmatched_table_key_count"] == 2
    assert event.metadata["unknown_column_key_count"] == 1
    assert event.metadata["ignored_unknown_join_hint_count"] == 1
    assert event.restricted_metadata["matched_table_keys"] == ["table_2"]
    assert event.restricted_metadata["owner_added_table_keys"] == ["table_1"]


def test_valid_column_can_supply_missing_owner_table(captured_events) -> None:
    result = select_relevant_structured_resources(
        _selector_state({"table_keys": [], "column_keys": ["table_2_col_1"], "join_keys": []})
    )

    event = _selector_event(captured_events)
    assert [item["table_key"] for item in result["selected_resources"]["tables"]] == ["table_2"]
    assert event.metadata["owner_table_added_count"] == 1
    assert event.metadata["selection_reason_code"] == "valid_subset_selected"


@pytest.mark.parametrize(
    "selection",
    [
        {"table_keys": ["table_missing"], "column_keys": ["column_missing"], "join_keys": []},
        {"table_keys": ["table_1"], "column_keys": [], "join_keys": []},
    ],
)
def test_selector_requires_at_least_one_valid_column(selection: dict, captured_events) -> None:
    result = select_relevant_structured_resources(_selector_state(selection))

    event = _selector_event(captured_events)
    assert result["failure_code"] == "no_relevant_structured_resources"
    assert event.status.value == "insufficient_evidence"
    assert event.metadata["matched_column_in_selected_tables_count"] == 0


def test_valid_join_adds_execution_endpoints_without_polluting_source_columns(captured_events) -> None:
    join = {
        "join_key": "join_1",
        "left_table_key": "table_1",
        "left_column_key": "table_1_col_1",
        "right_table_key": "table_2",
        "right_column_key": "table_2_col_1",
        "join_type": "inner",
    }
    result = select_relevant_structured_resources(
        _selector_state(
            {"table_keys": ["table_1", "table_2"], "column_keys": ["table_1_col_1"], "join_keys": ["join_1"]},
            approved_joins=[join],
        )
    )

    event = _selector_event(captured_events)
    selected = result["selected_resources"]
    assert [item["join_key"] for item in selected["joins"]] == ["join_1"]
    assert [item["column_key"] for item in selected["columns"]] == ["table_1_col_1", "table_2_col_1"]
    assert [item["column_key"] for item in selected["source_columns"]] == ["table_1_col_1"]
    assert event.metadata["matched_join_hint_count"] == 1


def test_multiple_valid_join_candidates_preserve_catalog_order() -> None:
    joins = [
        {
            "join_key": key,
            "left_table_key": "table_1",
            "left_column_key": "table_1_col_1",
            "right_table_key": "table_2",
            "right_column_key": "table_2_col_1",
        }
        for key in ("join_1", "join_2")
    ]
    result = select_relevant_structured_resources(
        _selector_state(
            {
                "table_keys": ["table_2", "table_1"],
                "column_keys": ["table_1_col_1"],
                "join_keys": ["join_2", "join_1"],
            },
            approved_joins=joins,
        )
    )

    assert [item["join_key"] for item in result["selected_resources"]["joins"]] == ["join_1", "join_2"]


@pytest.mark.parametrize(
    ("selection", "joins", "metadata_field"),
    [
        (
            {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []},
            [],
            None,
        ),
        (
            {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": ["join_missing"]},
            [],
            "ignored_unknown_join_hint_count",
        ),
        (
            {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": ["join_1"]},
            [{"join_key": "join_1", "left_column_key": "table_1_col_1"}],
            "ignored_incomplete_join_hint_count",
        ),
        (
            {"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": ["join_1"]},
            [
                {
                    "join_key": "join_1",
                    "left_table_key": "table_1",
                    "left_column_key": "table_1_col_1",
                    "right_table_key": "table_2",
                    "right_column_key": "table_2_col_1",
                }
            ],
            "ignored_outside_selected_tables_join_hint_count",
        ),
    ],
)
def test_join_hints_never_overturn_valid_table_column_selection(
    selection: dict, joins: list[dict], metadata_field: str | None, captured_events
) -> None:
    result = select_relevant_structured_resources(_selector_state(selection, approved_joins=joins))

    event = _selector_event(captured_events)
    assert "selected_resources" in result
    assert event.metadata["selection_reason_code"] == "valid_subset_selected"
    if metadata_field:
        assert event.metadata[metadata_field] == 1


def test_selector_audit_persistence_failure_does_not_change_control_flow(monkeypatch) -> None:
    monkeypatch.setattr("app.services.audit_trace._persist_audit_event", lambda _event: (_ for _ in ()).throw(RuntimeError()))

    result = select_relevant_structured_resources(
        _selector_state({"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    )

    assert "selected_resources" in result


def test_selector_canonical_event_never_creates_trace_entry(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(
        "app.tools.sql_rag.sql.nodes.select_relevant_structured_resources.emit_audit_event",
        lambda **kwargs: calls.append(kwargs),
    )

    result = select_relevant_structured_resources(
        _selector_state({"table_keys": ["table_1"], "column_keys": ["table_1_col_1"], "join_keys": []})
    )

    assert "selected_resources" in result
    assert len(calls) == 1
    assert calls[0]["include_trace_entry"] is False
    assert "proposed_table_keys" not in calls[0]["metadata"]
    assert calls[0]["restricted_metadata"]["proposed_table_keys"] == ["table_1"]


def test_selector_restricted_key_lists_are_bounded(captured_events) -> None:
    long_key = "x" * 129
    result = select_relevant_structured_resources(
        _selector_state(
            {
                "table_keys": ["table_1", *[f"table_missing_{index}" for index in range(100)]],
                "column_keys": ["table_1_col_1", long_key],
                "join_keys": [],
            }
        )
    )

    event = _selector_event(captured_events)
    assert "selected_resources" in result
    assert event.metadata["restricted_key_lists_truncated"] is True
    assert len(event.restricted_metadata["proposed_table_keys"]) == 100
    assert len(event.restricted_metadata["proposed_column_keys"][1]) == 128
