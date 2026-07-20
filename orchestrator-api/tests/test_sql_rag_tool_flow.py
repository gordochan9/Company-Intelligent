from __future__ import annotations

import pytest

from app.tools.sql_rag.agent import run_sql_rag_agent
from app.tools.sql_rag.nodes.multi_step_runtime_executor import multi_step_runtime_executor
from app.tools.sql_rag.nodes.normalizer_transformer import normalizer_transformer
from app.tools.sql_rag.nodes.perform_rag_sql import perform_rag_sql
from app.tools.sql_rag.nodes.runtime_obligation_planner import runtime_obligation_planner, set_runtime_obligation_planner_model
from app.tools.sql_rag.sql.services.executor import set_sql_executor
from app.tools.sql_rag.sql.services.llm import set_sql_generation_model, set_sql_intent_model, set_sql_selector_model
from app.tools.sql_rag.sql.services.repository import set_approved_joins, set_structured_resources


@pytest.fixture(autouse=True)
def reset_runtime_plan_model():
    set_runtime_obligation_planner_model(None)
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
    set_runtime_obligation_planner_model(None)
    set_structured_resources([])
    set_approved_joins([])
    set_sql_intent_model(None)
    set_sql_selector_model(None)
    set_sql_generation_model(None)
    set_sql_executor(None)


@pytest.fixture
def captured_events(monkeypatch: pytest.MonkeyPatch) -> list:
    events = []
    monkeypatch.setattr("app.services.audit_trace._persist_audit_event", events.append)
    return events


def _state() -> dict:
    return {
        "request_id": "req-sql-rag",
        "trace_id": "trace-sql-rag",
        "user_question": "What invoices are overdue?",
        "access_status": "ok",
        "trusted_user_context": {"email": "admin@demo.com"},
        "user_permission_schema": {
            "allowed_resources": {
                "allowed_scopes": ["finance"],
                "allowed_catalog_entry_ids": ["catalog:finance"],
                "allowed_rag_namespaces": ["finance"],
                "allowed_structured_resources": ["structured:finance"],
            }
        },
        "tool_selection": {
            "status": "selected",
            "selected_tools": [{"tool": "sql_rag", "reason": "Company data request."}],
            "reason": "Company data request.",
            "limitations": [],
            "errors": [],
            "debug": {},
        },
        "trace": [],
    }


def _sql_plan() -> dict:
    return {
        "status": "planned",
        "obligations": [{"obligation_id": "o1", "description": "Return overdue invoice amounts."}],
        "steps": [
            {
                "step_id": "step_1",
                "step_type": "sql",
                "goal": "Return overdue invoice amounts.",
                "obligation_ids": ["o1"],
                "depends_on": [],
            },
            {
                "step_id": "final",
                "step_type": "final_result",
                "goal": "Bundle validated outputs.",
                "obligation_ids": [],
                "depends_on": ["step_1"],
            },
        ],
    }


def _rag_plan() -> dict:
    return {
        "status": "planned",
        "obligations": [{"obligation_id": "o1", "description": "Find policy evidence."}],
        "steps": [
            {
                "step_id": "step_1",
                "step_type": "rag",
                "goal": "Find policy evidence about the requested topic.",
                "obligation_ids": ["o1"],
                "depends_on": [],
            },
            {
                "step_id": "final",
                "step_type": "final_result",
                "goal": "Bundle validated outputs.",
                "obligation_ids": [],
                "depends_on": ["step_1"],
            },
        ],
    }


def _sql_result(step_id: str, rows: list[dict], columns: list[str], limitations: list | None = None) -> dict:
    return {
        "sql_result": {
            "step_id": step_id,
            "step_type": "sql",
            "status": "success",
            "validated_output": {"rows": rows, "columns": columns, "row_count": len(rows), "sql_hash": "sha256:x"},
            "limitations": list(limitations or []),
            "errors": [],
            "audit_metadata": {},
        }
    }


def _completed_step_state(plan: dict, step_type: str, validated_output: object) -> dict:
    step = next(step for step in plan["steps"] if step["step_type"] == step_type)
    return {
        **_state(),
        "runtime_plan": plan,
        "runtime_plan_status": "running",
        "completed_steps": [step["step_id"]],
        "covered_obligation_ids": [],
        "step_results": [
            {
                "step_id": step["step_id"],
                "step_type": step_type,
                "status": "success",
                "validated_output": validated_output,
                "limitations": [],
                "errors": [],
                "audit_metadata": {},
            }
        ],
    }


def test_sql_normalizer_preserves_success_without_claiming_coverage(captured_events: list) -> None:
    step = _sql_plan()["steps"][0]
    output = {"rows": [{"amount": 100}], "columns": ["amount"], "row_count": 1}

    result = normalizer_transformer(
        {
            **_state(),
            "current_step": step,
            "current_child_result": {
                "sql_result": {
                    "step_id": "step_1",
                    "step_type": "sql",
                    "status": "success",
                    "validated_output": output,
                    "limitations": [],
                    "errors": [],
                    "audit_metadata": {},
                }
            },
            "completed_steps": [],
            "covered_obligation_ids": [],
            "step_results": [],
            "dependency_context": {},
        }
    )

    assert result["completed_steps"] == ["step_1"]
    assert "covered_obligation_ids" not in result
    assert result["dependency_context"] == {"step_1": {"validated_output": output}}
    assert [event.event_type for event in captured_events] == ["normalizer_completed"]


def test_rag_normalizer_keeps_existing_coverage_ownership(captured_events: list) -> None:
    step = _rag_plan()["steps"][0]
    output = {"validated_evidence": [], "validated_citations": []}

    result = normalizer_transformer(
        {
            **_state(),
            "current_step": step,
            "current_child_result": {
                "rag_result": {
                    "step_id": "step_1",
                    "step_type": "rag",
                    "status": "success",
                    "validated_output": output,
                    "limitations": [],
                    "errors": [],
                    "audit_metadata": {},
                }
            },
            "completed_steps": [],
            "covered_obligation_ids": [],
            "step_results": [],
            "dependency_context": {},
        }
    )

    assert result["covered_obligation_ids"] == ["o1"]
    assert [event.event_type for event in captured_events] == ["runtime_step_completed"]


@pytest.mark.parametrize("value", [0, 0.0, False, ""])
def test_sql_runtime_gate_accepts_falsey_non_null_values(value: object) -> None:
    output = {"rows": [{"value": value}], "columns": ["value"], "row_count": 1}

    result = multi_step_runtime_executor(_completed_step_state(_sql_plan(), "sql", output))

    assert result["runtime_plan_status"] == "complete"
    assert result["covered_obligation_ids"] == ["o1"]


def test_sql_runtime_gate_accepts_zero_rows_and_non_empty_columns() -> None:
    output = {"rows": [], "columns": ["amount"], "row_count": 0}

    result = multi_step_runtime_executor(_completed_step_state(_sql_plan(), "sql", output))

    assert result["runtime_plan_status"] == "complete"
    assert result["covered_obligation_ids"] == ["o1"]


def test_sql_runtime_gate_accepts_columns_with_non_null_values_across_different_rows() -> None:
    output = {
        "rows": [{"amount": 100, "count": None}, {"amount": None, "count": 0}],
        "columns": ["amount", "count"],
        "row_count": 2,
    }

    result = multi_step_runtime_executor(_completed_step_state(_sql_plan(), "sql", output))

    assert result["runtime_plan_status"] == "complete"
    assert result["covered_obligation_ids"] == ["o1"]


@pytest.mark.parametrize(
    "output",
    [
        None,
        {},
        {"rows": [], "columns": [], "row_count": 0},
        {"rows": "not-a-list", "columns": ["amount"], "row_count": 1},
        {"rows": [], "columns": ["amount"], "row_count": True},
        {"rows": [{"amount": None}], "columns": ["amount"], "row_count": 1},
    ],
)
def test_sql_runtime_gate_rejects_malformed_or_all_null_output(output: object, captured_events: list) -> None:
    result = multi_step_runtime_executor(_completed_step_state(_sql_plan(), "sql", output))

    assert result["runtime_plan_status"] == "invalid_plan"
    assert result["failure_code"] == "uncovered_obligation"
    failed = [event for event in captured_events if event.event_type == "runtime_step_failed"]
    assert len(failed) == 1
    assert set(failed[0].restricted_metadata) == {
        "step_id",
        "assigned_obligation_ids",
        "covered_obligation_ids",
        "gate_reason",
    }
    assert "not-a-list" not in repr(failed[0])


def test_runtime_executor_does_not_take_rag_coverage_ownership() -> None:
    output = {"validated_evidence": [{"evidence_ref": "ev1"}], "validated_citations": []}

    result = multi_step_runtime_executor(_completed_step_state(_rag_plan(), "rag", output))

    assert result["runtime_plan_status"] == "invalid_plan"
    assert result["failure_code"] == "uncovered_obligation"
    assert "covered_obligation_ids" not in result


def test_sql_only_plan_dispatches_and_covers_obligation(
    monkeypatch: pytest.MonkeyPatch, captured_events: list
) -> None:
    calls: list[dict] = []
    set_runtime_obligation_planner_model(lambda _payload: _sql_plan())

    def sql_child(step_state: dict) -> dict:
        calls.append(step_state)
        return _sql_result("step_1", [{"amount": 100}], ["amount"], [{"message": "SQL child limitation."}])

    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow", sql_child)
    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_rag_workflow", lambda _state: pytest.fail("RAG child should not run"))

    result = run_sql_rag_agent(_state())

    assert len(calls) == 1
    assert calls[0]["obligations"] == [{"obligation_id": "o1", "description": "Return overdue invoice amounts."}]
    assert "required_inputs" not in calls[0]
    assert "expected_outputs" not in calls[0]
    assert result["tool_results"][0]["status"] == "success"
    assert result["final_answer_context"]["validated_sql_rows"] == [{"amount": 100}]
    assert result["final_answer_context"]["answer_material"] == {
        "obligations": [{"obligation_id": "o1", "description": "Return overdue invoice amounts."}],
        "structured_results": [
            {
                "step_id": "step_1",
                "goal": "Return overdue invoice amounts.",
                "obligation_ids": ["o1"],
                "step_type": "sql",
                "status": "success",
                "columns": ["amount"],
                "rows": [{"amount": 100}],
                "row_count": 1,
                "limitations": [{"message": "SQL child limitation."}],
                "errors": [],
            }
        ],
        "document_evidence": [],
    }
    assert "sql_hash" not in repr(result["final_answer_context"]["answer_material"])
    assert "permission" not in repr(result["final_answer_context"]["answer_material"])
    assert result["final_answer_context"]["limitations"] == [{"message": "SQL child limitation."}]
    assert "runtime_step_completed" in [event.event_type for event in captured_events]
    assert "runtime_step_coverage_evaluated" not in [event.event_type for event in captured_events]


def test_rag_only_plan_dispatches_and_covers_obligation(monkeypatch: pytest.MonkeyPatch) -> None:
    set_runtime_obligation_planner_model(lambda _payload: _rag_plan())
    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow", lambda _state: pytest.fail("SQL child should not run"))
    monkeypatch.setattr(
        "app.tools.sql_rag.nodes.perform_rag_sql.run_rag_workflow",
        lambda _state: {
            "rag_result": {
                "step_id": "step_1",
                "step_type": "rag",
                "status": "success",
                "validated_output": {
                    "validated_evidence": [{"evidence_ref": "ev1"}],
                    "validated_citations": [{"citation_id": "c1", "evidence_ref": "ev1"}],
                },
                "limitations": [{"message": "RAG child limitation."}],
                "errors": [],
                "audit_metadata": {},
            }
        },
    )

    result = run_sql_rag_agent(_state())

    assert result["tool_results"][0]["status"] == "success"
    assert result["final_answer_context"]["validated_citations"] == [{"citation_id": "c1", "evidence_ref": "ev1"}]
    assert result["final_answer_context"]["answer_material"]["document_evidence"] == [
        {
            "step_id": "step_1",
            "goal": "Find policy evidence about the requested topic.",
            "obligation_ids": ["o1"],
            "step_type": "rag",
            "status": "success",
            "limitations": [{"message": "RAG child limitation."}],
            "errors": [],
            "validated_evidence": [{"evidence_ref": "ev1"}],
            "validated_citations": [{"citation_id": "c1", "evidence_ref": "ev1"}],
        }
    ]
    assert result["final_answer_context"]["limitations"] == [{"message": "RAG child limitation."}]


def test_zero_row_sql_result_is_validated_answer_material(monkeypatch: pytest.MonkeyPatch) -> None:
    set_runtime_obligation_planner_model(lambda _payload: _sql_plan())
    monkeypatch.setattr(
        "app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow",
        lambda _state: _sql_result("step_1", [], ["amount"]),
    )

    result = run_sql_rag_agent(_state())

    assert result["tool_results"][0]["status"] == "success"
    structured = result["final_answer_context"]["answer_material"]["structured_results"][0]
    assert structured["rows"] == []
    assert structured["row_count"] == 0


def test_runtime_obligation_planner_model_receives_bounded_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict = {}

    def model(payload: dict) -> dict:
        captured.update(payload)
        return _sql_plan()

    set_runtime_obligation_planner_model(model)
    monkeypatch.setattr(
        "app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow",
        lambda _state: _sql_result("step_1", [{"amount": 100}], ["amount"]),
    )

    run_sql_rag_agent(_state())

    assert captured["payload"]["user_question"] == "What invoices are overdue?"
    assert "obligation_id" in captured["system_prompt"]
    assert "expected_outputs" not in captured["system_prompt"]
    assert "required_inputs" not in captured["system_prompt"]
    assert "raw SQL" in captured["system_prompt"]
    assert "planned only when obligations contains at least one item" in captured["system_prompt"]
    assert "conversation_context" not in captured["payload"]
    assert "limitations" not in captured["system_prompt"]


def test_planner_rejects_non_planned_candidate_before_parsed_event(captured_events: list) -> None:
    set_runtime_obligation_planner_model(
        lambda _payload: {"status": "failed", "obligations": [{"obligation_id": "o1"}], "steps": []}
    )

    result = runtime_obligation_planner(_state())

    assert result["runtime_plan_status"] == "planning_failed"
    assert result["failure_code"] == "runtime_plan_invalid_status"
    assert not any(event.event_type == "runtime_plan_parsed" for event in captured_events)


@pytest.mark.parametrize("obligations", [None, "not-a-list", []])
def test_planner_rejects_missing_or_empty_obligations_before_parsed_event(
    obligations: object, captured_events: list
) -> None:
    candidate = {"status": "planned", "steps": []}
    if obligations is not None:
        candidate["obligations"] = obligations
    set_runtime_obligation_planner_model(lambda _payload: candidate)

    result = runtime_obligation_planner(_state())

    assert result["runtime_plan_status"] == "planning_failed"
    assert result["failure_code"] == "runtime_plan_missing_obligations"
    assert not any(event.event_type == "runtime_plan_parsed" for event in captured_events)


def test_non_empty_planner_limitations_fail_closed_without_child_dispatch(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = {**_sql_plan(), "limitations": [{"message": "Partial plan."}]}
    set_runtime_obligation_planner_model(lambda _payload: plan)
    monkeypatch.setattr(
        "app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow",
        lambda _state: pytest.fail("SQL child should not run"),
    )
    monkeypatch.setattr(
        "app.tools.sql_rag.nodes.perform_rag_sql.run_rag_workflow",
        lambda _state: pytest.fail("RAG child should not run"),
    )

    result = run_sql_rag_agent(_state())

    assert result["tool_results"][0]["status"] == "validation_failed"
    assert result["tool_results"][0]["errors"][0]["code"] == "runtime_plan_has_limitations"


def test_planner_audit_logs_counts_before_validation_and_structure_after_validation(
    monkeypatch: pytest.MonkeyPatch, captured_events: list
) -> None:
    plan = _sql_plan()
    plan["obligations"][0]["description"] = "SENSITIVE OBLIGATION TEXT"
    plan["steps"][0]["goal"] = "SENSITIVE STEP GOAL"
    set_runtime_obligation_planner_model(lambda _payload: plan)
    monkeypatch.setattr(
        "app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow",
        lambda _state: _sql_result("step_1", [{"amount": 100}], ["amount"]),
    )

    run_sql_rag_agent(_state())

    called = next(event for event in captured_events if event.event_type == "runtime_plan_llm_called")
    assert called.metadata == {"planning_status": "started"}
    assert called.restricted_metadata == {}
    parsed = next(event for event in captured_events if event.event_type == "runtime_plan_parsed")
    assert parsed.restricted_metadata == {}
    assert set(parsed.metadata) == {
        "obligation_count",
        "executable_step_count",
        "sql_step_count",
        "rag_step_count",
        "dependency_count",
        "planning_status",
    }
    ready = next(event for event in captured_events if event.event_type == "runtime_plan_ready")
    assert ready.restricted_metadata["obligation_ids"] == ["o1"]
    assert ready.restricted_metadata["steps"][0] == {
        "step_id": "step_1",
        "step_type": "sql",
        "obligation_ids": ["o1"],
        "depends_on": [],
    }
    assert "SENSITIVE OBLIGATION TEXT" not in repr(parsed)
    assert "SENSITIVE STEP GOAL" not in repr(parsed)
    assert "SENSITIVE OBLIGATION TEXT" not in repr(ready)
    assert "SENSITIVE STEP GOAL" not in repr(ready)


def test_count_and_names_execute_through_two_complete_sql_children(
    monkeypatch: pytest.MonkeyPatch, captured_events: list
) -> None:
    plan = {
        "status": "planned",
        "obligations": [
            {"obligation_id": "o1", "description": "Count inactive assets."},
            {"obligation_id": "o2", "description": "List inactive asset names."},
        ],
        "steps": [
            {
                "step_id": "count_step",
                "step_type": "sql",
                "goal": "Count inactive assets.",
                "obligation_ids": ["o1"],
            },
            {
                "step_id": "names_step",
                "step_type": "sql",
                "goal": "List inactive asset names.",
                "obligation_ids": ["o2"],
            },
            {
                "step_id": "final",
                "step_type": "final_result",
                "goal": "Bundle both validated SQL results.",
                "depends_on": ["count_step", "names_step"],
            },
        ],
    }
    intent_calls: list[dict] = []
    generation_calls: list[dict] = []
    set_runtime_obligation_planner_model(lambda _payload: plan)
    set_structured_resources(
        [
            {
                "resource_key": "structured:assets",
                "runtime_relation_name": "assets_table",
                "display_name": "Assets",
                "columns": [
                    {"column_name": "asset_name", "data_type": "text", "safe_description": "Asset name."},
                    {"column_name": "status", "data_type": "text", "safe_description": "Asset status."},
                ],
            }
        ]
    )

    def intent_model(payload: dict) -> dict:
        intent_calls.append(payload)
        obligations = payload["payload"]["obligations"]
        if obligations[0]["obligation_id"] == "o1":
            return {
                "table_keys": ["table_1"],
                "column_keys": ["table_1_col_2"],
                "join_keys": [],
                "metric": "count inactive assets",
                "filters": [{"column_key": "table_1_col_2", "operator": "equals", "value_hint": "inactive"}],
                "population": "Assets with the requested status.",
                "metrics": [
                    {
                        "name": "inactive_count",
                        "aggregation": "count",
                        "output_name": "inactive_count",
                        "condition": "All assets in the filtered population.",
                        "condition_column_keys": [],
                        "value_description": "Assets in the filtered population.",
                        "value_column_keys": [],
                        "numerator_metric": "",
                        "denominator_metric": "",
                    }
                ],
                "grouping": [],
                "ranking": None,
                "reason": "Count the filtered rows.",
            }
        return {
            "table_keys": ["table_1"],
            "column_keys": ["table_1_col_1", "table_1_col_2"],
            "join_keys": [],
            "metric": "",
            "filters": [{"column_key": "table_1_col_2", "operator": "equals", "value_hint": "inactive"}],
            "population": "Assets with the requested status.",
            "metrics": [],
            "grouping": [],
            "ranking": None,
            "reason": "Return the requested names.",
        }

    def generation_model(payload: dict) -> dict:
        generation_calls.append(payload)
        if payload["payload"]["sql_query_intent"]["metrics"]:
            return {"sql": "SELECT COUNT(*) AS inactive_count FROM assets_table WHERE status = 'inactive' LIMIT 1"}
        return {"sql": "SELECT asset_name FROM assets_table WHERE status = 'inactive' LIMIT 10"}

    set_sql_intent_model(intent_model)
    set_sql_generation_model(generation_model)
    set_sql_executor(
        lambda sql, _validated: (
            {"columns": ["inactive_count"], "rows": [{"inactive_count": 2}]}
            if "COUNT(*)" in sql
            else {"columns": ["asset_name"], "rows": [{"asset_name": "A"}, {"asset_name": "B"}]}
        )
    )
    state = _state()
    state["user_question"] = "How many inactive assets are there, and what are their names?"
    state["user_permission_schema"]["allowed_resources"]["allowed_structured_resources"] = ["structured:assets"]

    result = run_sql_rag_agent(state)

    assert len(intent_calls) == 2
    assert len(generation_calls) == 2
    assert intent_calls[0]["payload"]["obligations"] == [{"obligation_id": "o1", "description": "Count inactive assets."}]
    assert intent_calls[1]["payload"]["obligations"] == [{"obligation_id": "o2", "description": "List inactive asset names."}]
    assert intent_calls[0]["payload"]["dependency_context"] == {}
    assert intent_calls[1]["payload"]["dependency_context"] == {}
    assert generation_calls[1]["payload"]["sql_query_intent"]["metric"] == ""
    assert generation_calls[1]["payload"]["sql_query_intent"]["metrics"] == []
    assert result["tool_results"][0]["status"] == "success"
    assert result["final_answer_context"]["validated_sql_rows"] == [
        {"inactive_count": 2},
        {"asset_name": "A"},
        {"asset_name": "B"},
    ]
    completed = [event for event in captured_events if event.event_type == "runtime_step_completed"]
    assert completed[-1].restricted_metadata["covered_obligation_ids"] == ["o1", "o2"]
    for event_type in (
        "sql_intake_completed",
        "sql_query_intent_built",
        "candidate_sql_generated",
        "sql_validation_completed",
        "sql_execution_completed",
        "sql_result_validated",
    ):
        assert len([event for event in captured_events if event.event_type == event_type]) == 2


def test_dependent_sql_step_receives_only_required_validated_output(monkeypatch: pytest.MonkeyPatch) -> None:
    plan = {
        "status": "planned",
        "obligations": [
            {"obligation_id": "o1", "description": "Identify the winning carrier."},
            {"obligation_id": "o2", "description": "Calculate metrics for the winner."},
        ],
        "steps": [
            {
                "step_id": "winner_step",
                "step_type": "sql",
                "goal": "Return the carrier with the highest late shipment count.",
                "obligation_ids": ["o1"],
            },
            {
                "step_id": "metric_step",
                "step_type": "sql",
                "goal": "Return total count, late count, late rate, and average days late for the winning carrier.",
                "obligation_ids": ["o2"],
                "depends_on": ["winner_step"],
            },
            {
                "step_id": "final",
                "step_type": "final_result",
                "goal": "Bundle both validated SQL results.",
                "depends_on": ["winner_step", "metric_step"],
            },
        ],
    }
    calls: list[dict] = []
    set_runtime_obligation_planner_model(lambda _payload: plan)

    def sql_child(step_state: dict) -> dict:
        calls.append(step_state)
        if step_state["step_id"] == "winner_step":
            return _sql_result(
                "winner_step",
                [{"winning_carrier": "Carrier A", "late_count": 3}],
                ["winning_carrier", "late_count"],
            )
        return _sql_result(
            "metric_step",
            [{"total_count": 10, "late_count": 3, "late_rate": 0.3, "average_days_late": 4.5}],
            ["total_count", "late_count", "late_rate", "average_days_late"],
        )

    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow", sql_child)

    result = run_sql_rag_agent(_state())

    assert calls[0]["dependency_context"] == {}
    assert calls[1]["dependency_context"] == {
        "winner_step": {
            "validated_output": {
                "rows": [{"winning_carrier": "Carrier A", "late_count": 3}],
                "columns": ["winning_carrier", "late_count"],
                "row_count": 1,
                "sql_hash": "sha256:x",
            },
        }
    }
    assert result["tool_results"][0]["status"] == "success"


def test_successful_sql_output_is_preserved_without_predicted_output_contract(
    monkeypatch: pytest.MonkeyPatch, captured_events: list
) -> None:
    calls = 0
    plan = _sql_plan()
    set_runtime_obligation_planner_model(lambda _payload: plan)

    def sql_child(_state: dict) -> dict:
        nonlocal calls
        calls += 1
        return _sql_result("step_1", [{"amount": 100}], ["amount"])

    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow", sql_child)

    result = run_sql_rag_agent(_state())
    normalized = result["tool_results"][0]["validated_output"]["validated_outputs"][0]

    assert calls == 1
    assert result["tool_results"][0]["status"] == "success"
    assert normalized["status"] == "success"
    assert normalized["errors"] == []
    assert "runtime_step_completed" in [event.event_type for event in captured_events]
    assert "runtime_step_coverage_evaluated" not in [event.event_type for event in captured_events]


def test_child_validated_rag_success_is_not_revalidated_by_normalizer(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    set_runtime_obligation_planner_model(lambda _payload: _rag_plan())

    def rag_child(_state: dict) -> dict:
        nonlocal calls
        calls += 1
        return {
            "rag_result": {
                "step_id": "step_1",
                "step_type": "rag",
                "status": "success",
                "validated_output": {"validated_evidence": [], "validated_citations": []},
                "limitations": [],
                "errors": [],
                "audit_metadata": {},
            }
        }

    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_rag_workflow", rag_child)

    result = run_sql_rag_agent(_state())
    normalized = result["tool_results"][0]["validated_output"]["validated_outputs"][0]

    assert calls == 1
    assert result["tool_results"][0]["status"] == "insufficient_evidence"
    assert normalized["status"] == "success"


def test_child_failure_returns_through_executor_and_is_not_retried(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = 0
    set_runtime_obligation_planner_model(lambda _payload: _sql_plan())

    def sql_child(_state: dict) -> dict:
        nonlocal calls
        calls += 1
        return {
            "sql_result": {
                "step_id": "step_1",
                "step_type": "sql",
                "status": "validation_failed",
                "validated_output": {},
                "limitations": [],
                "errors": [{"code": "invalid_sql", "message": "SQL validation failed."}],
                "audit_metadata": {},
            }
        }

    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow", sql_child)

    result = run_sql_rag_agent(_state())

    assert calls == 1
    assert result["tool_results"][0]["status"] == "validation_failed"
    assert result["tool_results"][0]["errors"] == [
        {"code": "invalid_sql", "message": "SQL validation failed."}
    ]


def test_malformed_child_output_returns_through_executor_and_is_not_retried(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0
    set_runtime_obligation_planner_model(lambda _payload: _sql_plan())

    def sql_child(_state: dict) -> dict:
        nonlocal calls
        calls += 1
        return {"sql_result": {"unexpected": True}}

    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow", sql_child)

    result = run_sql_rag_agent(_state())

    assert calls == 1
    assert result["tool_results"][0]["status"] == "validation_failed"
    assert result["tool_results"][0]["errors"] == [
        {"code": "malformed_child_output", "message": "Child workflow output was malformed."}
    ]


@pytest.mark.parametrize(("step_type", "question_key"), [("sql", "sql_question"), ("rag", "rag_question")])
def test_perform_rag_sql_passes_only_step_scoped_contract(
    monkeypatch: pytest.MonkeyPatch, step_type: str, question_key: str
) -> None:
    captured: dict = {}

    def child(child_state: dict) -> dict:
        captured.update(child_state)
        return {}

    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow", child)
    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_rag_workflow", child)
    state = {
        **_state(),
        "user_question": "Count inactive items, and list their names.",
        "conversation_context": {"previous": "sensitive full context"},
        "runtime_plan": {
            "obligations": [{"obligation_id": "o1", "description": "Count inactive items."}],
        },
        "current_step": {
            "step_id": "step_1",
            "step_type": step_type,
            "goal": "Count inactive items.",
            "obligation_ids": ["o1"],
            "depends_on": ["step_0"],
        },
        "completed_steps": ["step_0"],
        "dependency_context": {
            "step_0": {
                "validated_output": {"rows": [{"value": 1}], "columns": ["value"]},
            }
        },
    }

    perform_rag_sql(state)

    assert captured[question_key] == "Count inactive items."
    assert captured["obligations"] == [{"obligation_id": "o1", "description": "Count inactive items."}]
    assert "required_inputs" not in captured
    assert "expected_outputs" not in captured
    assert captured["dependency_context"] == {
        "step_0": {
            "validated_output": {"rows": [{"value": 1}], "columns": ["value"]},
        }
    }
    assert "user_question" not in captured
    assert "conversation_context" not in captured


def test_executor_cannot_complete_with_uncovered_obligations() -> None:
    result = multi_step_runtime_executor(
        {
            **_state(),
            "runtime_plan": _sql_plan(),
            "runtime_plan_status": "running",
            "completed_steps": ["step_1"],
            "covered_obligation_ids": [],
        }
    )

    assert result["runtime_plan_status"] == "invalid_plan"
    assert result["failure_code"] == "uncovered_obligation"


def test_executor_schedules_from_completed_dependencies_without_inspecting_packets() -> None:
    plan = {
        "status": "planned",
        "obligations": [
            {"obligation_id": "o1", "description": "Produce a selector."},
            {"obligation_id": "o2", "description": "Use the selector."},
        ],
        "steps": [
            {
                "step_id": "producer",
                "step_type": "sql",
                "goal": "Produce the selector.",
                "obligation_ids": ["o1"],
            },
            {
                "step_id": "consumer",
                "step_type": "sql",
                "goal": "Use the selector.",
                "obligation_ids": ["o2"],
                "depends_on": ["producer"],
            },
            {
                "step_id": "final",
                "step_type": "final_result",
                "goal": "Bundle outputs.",
                "depends_on": ["producer", "consumer"],
            },
        ],
    }

    result = multi_step_runtime_executor(
        {
            **_state(),
            "runtime_plan": plan,
            "runtime_plan_status": "running",
            "completed_steps": ["producer"],
            "covered_obligation_ids": ["o1"],
            "dependency_context": {},
        }
    )

    assert result["runtime_plan_status"] == "running"
    assert result["current_step"]["step_id"] == "consumer"
    assert "completed_steps" not in result
    assert "covered_obligation_ids" not in result


def test_perform_rag_sql_defense_rejects_missing_dependency_without_child_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow",
        lambda _state: pytest.fail("SQL child should not run"),
    )
    monkeypatch.setattr(
        "app.tools.sql_rag.nodes.perform_rag_sql.run_rag_workflow",
        lambda _state: pytest.fail("RAG child should not run"),
    )
    state = {
        **_state(),
        "current_step": {
            "step_id": "consumer",
            "step_type": "sql",
            "goal": "Use the selector.",
            "obligation_ids": ["o2"],
            "depends_on": ["producer"],
        },
        "runtime_plan": {"obligations": [{"obligation_id": "o2", "description": "Use the selector."}]},
        "completed_steps": ["producer"],
        "dependency_context": {},
    }

    result = perform_rag_sql(state)

    assert result["runtime_plan_status"] == "blocked"
    assert result["failure_code"] == "missing_dependency_context"


@pytest.mark.parametrize("value", [None, 0, False, [], ""])
def test_perform_rag_sql_passes_falsey_present_dependency_values(
    monkeypatch: pytest.MonkeyPatch, value: object
) -> None:
    captured: dict = {}

    def sql_child(child_state: dict) -> dict:
        captured.update(child_state)
        return {}

    monkeypatch.setattr("app.tools.sql_rag.nodes.perform_rag_sql.run_sql_workflow", sql_child)
    state = {
        **_state(),
        "current_step": {
            "step_id": "consumer",
            "step_type": "sql",
            "goal": "Use the selector.",
            "obligation_ids": ["o2"],
            "depends_on": ["producer"],
        },
        "runtime_plan": {"obligations": [{"obligation_id": "o2", "description": "Use the selector."}]},
        "completed_steps": ["producer"],
        "dependency_context": {
            "producer": {
                "validated_output": {"rows": [{"selector": value}], "columns": ["selector"]},
            }
        },
    }

    perform_rag_sql(state)

    assert captured["dependency_context"] == {
        "producer": {
            "validated_output": {"rows": [{"selector": value}], "columns": ["selector"]},
        }
    }
