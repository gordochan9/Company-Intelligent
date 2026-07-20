from __future__ import annotations

import pytest

from app.tools.sql_rag.contracts import RuntimePlanValidationError, validate_runtime_plan


def _plan(**overrides):
    plan = {
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
                "step_id": "step_2",
                "step_type": "final_result",
                "goal": "Bundle validated output.",
                "obligation_ids": [],
                "depends_on": ["step_1"],
            },
        ],
    }
    plan.update(overrides)
    return plan


def test_runtime_plan_accepts_complete_obligation_plan() -> None:
    result = validate_runtime_plan(_plan())

    assert set(result) == {"status", "obligations", "steps", "reason"}
    assert result["status"] == "planned"
    assert result["obligations"] == [{"obligation_id": "o1", "description": "Find policy evidence."}]
    assert result["steps"][0]["obligation_ids"] == ["o1"]
    assert result["steps"][1]["depends_on"] == ["step_1"]


@pytest.mark.parametrize(
    ("plan", "code"),
    [
        (_plan(obligations=[]), "runtime_plan_missing_obligations"),
        (
            _plan(
                obligations=[
                    {"obligation_id": "o1", "description": "First."},
                    {"obligation_id": "o1", "description": "Second."},
                ]
            ),
            "runtime_plan_duplicate_obligation_id",
        ),
        (
            _plan(
                steps=[
                    {
                        "step_id": "step_1",
                        "step_type": "rag",
                        "goal": "Find evidence.",
                        "obligation_ids": ["missing"],
                    },
                    {
                        "step_id": "final",
                        "step_type": "final_result",
                        "goal": "Bundle.",
                        "obligation_ids": [],
                        "depends_on": ["step_1"],
                    },
                ]
            ),
            "runtime_plan_unknown_obligation",
        ),
        (
            _plan(
                obligations=[
                    {"obligation_id": "o1", "description": "First."},
                    {"obligation_id": "o2", "description": "Second."},
                ]
            ),
            "uncovered_obligation",
        ),
        (
            _plan(
                steps=[
                    {
                        "step_id": "step_1",
                        "step_type": "sql",
                        "goal": "Return first output.",
                        "obligation_ids": ["o1"],
                    },
                    {
                        "step_id": "step_2",
                        "step_type": "sql",
                        "goal": "Return second output.",
                        "obligation_ids": ["o1"],
                    },
                    {
                        "step_id": "final",
                        "step_type": "final_result",
                        "goal": "Bundle.",
                        "obligation_ids": [],
                        "depends_on": ["step_1", "step_2"],
                    },
                ]
            ),
            "runtime_plan_duplicate_obligation_assignment",
        ),
    ],
)
def test_runtime_plan_rejects_invalid_obligation_coverage(plan: dict, code: str) -> None:
    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(plan)

    assert exc.value.code == code


@pytest.mark.parametrize(
    ("step", "code"),
    [
        (
            {"step_id": "step_1", "step_type": "sql", "goal": "Return a count."},
            "runtime_plan_missing_obligation_ids",
        ),
    ],
)
def test_runtime_plan_rejects_incomplete_executable_step(step: dict, code: str) -> None:
    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(
            _plan(
                steps=[
                    step,
                    {
                        "step_id": "final",
                        "step_type": "final_result",
                        "goal": "Bundle.",
                        "obligation_ids": [],
                        "depends_on": ["step_1"],
                    },
                ]
            )
        )

    assert exc.value.code == code


@pytest.mark.parametrize("field", ["required_inputs", "expected_outputs"])
def test_runtime_plan_rejects_legacy_predictive_fields(field: str) -> None:
    plan = _plan()
    plan["steps"][0][field] = []

    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(plan)

    assert exc.value.code == "runtime_plan_forbidden_field"


@pytest.mark.parametrize(
    ("steps", "code"),
    [
        (
            [
                {
                    "step_id": "step_1",
                    "step_type": "sql",
                    "goal": "Return a count.",
                    "obligation_ids": ["o1"],
                }
            ],
            "runtime_plan_missing_final_result",
        ),
        (
            [
                {
                    "step_id": "step_1",
                    "step_type": "sql",
                    "goal": "Return a count.",
                    "obligation_ids": ["o1"],
                },
                {"step_id": "final_1", "step_type": "final_result", "goal": "Bundle.", "depends_on": ["step_1"]},
                {"step_id": "final_2", "step_type": "final_result", "goal": "Bundle again.", "depends_on": ["step_1"]},
            ],
            "runtime_plan_multiple_final_results",
        ),
        (
            [
                {
                    "step_id": "step_1",
                    "step_type": "sql",
                    "goal": "Return a count.",
                    "obligation_ids": ["o1"],
                },
                {
                    "step_id": "step_2",
                    "step_type": "sql",
                    "goal": "Return names.",
                    "obligation_ids": ["o2"],
                },
                {"step_id": "final", "step_type": "final_result", "goal": "Bundle.", "depends_on": ["step_1"]},
            ],
            "runtime_plan_incomplete_final_dependencies",
        ),
    ],
)
def test_runtime_plan_requires_one_complete_final_result(steps: list[dict], code: str) -> None:
    obligations = [{"obligation_id": "o1", "description": "First."}]
    if any("o2" in step.get("obligation_ids", []) for step in steps):
        obligations.append({"obligation_id": "o2", "description": "Second."})

    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(_plan(obligations=obligations, steps=steps))

    assert exc.value.code == code


def test_runtime_plan_rejects_forbidden_low_level_fields() -> None:
    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(
            _plan(
                steps=[
                    {
                        "step_id": "step_1",
                        "step_type": "sql",
                        "goal": "Query rows.",
                        "obligation_ids": ["o1"],
                        "raw_sql": "SELECT * FROM finance LIMIT 10",
                    }
                ]
            )
        )

    assert exc.value.code == "runtime_plan_forbidden_field"


def test_runtime_plan_rejects_unreadable_output() -> None:
    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan("not json")

    assert exc.value.code == "runtime_plan_unreadable"


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("obligation_ids", 1, "runtime_plan_missing_obligation_ids"),
    ],
)
def test_runtime_plan_rejects_non_list_step_contract_fields(field: str, value: object, code: str) -> None:
    plan = _plan()
    plan["steps"][0][field] = value

    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(plan)

    assert exc.value.code == code


def test_runtime_plan_preserves_step_limit_and_dependency_ordering() -> None:
    too_many = _plan()
    too_many["steps"] = too_many["steps"] * 5
    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(too_many)
    assert exc.value.code == "runtime_plan_too_many_steps"

    future_dependency = _plan()
    future_dependency["steps"][0]["depends_on"] = ["step_2"]
    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(future_dependency)
    assert exc.value.code == "runtime_plan_future_dependency"


def test_runtime_plan_allows_business_prose_with_sql_keyword_words() -> None:
    plan = _plan()
    plan["steps"][0]["goal"] = "Summarize the policy update, volume drop, and available copy formats."

    result = validate_runtime_plan(plan)

    assert result["steps"][0]["goal"] == plan["steps"][0]["goal"]


@pytest.mark.parametrize(
    ("field", "code"),
    [("limitations", "runtime_plan_has_limitations"), ("errors", "runtime_plan_has_errors")],
)
def test_runtime_plan_rejects_non_empty_planner_failure_fields(field: str, code: str) -> None:
    plan = _plan(**{field: [{"message": "Planner could not produce a complete plan."}]})

    with pytest.raises(RuntimePlanValidationError) as exc:
        validate_runtime_plan(plan)

    assert exc.value.code == code
