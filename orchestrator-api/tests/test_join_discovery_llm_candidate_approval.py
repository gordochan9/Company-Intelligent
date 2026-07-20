from __future__ import annotations

import pytest

from app.services.join_discovery_approved_joins import run_approved_join_discovery_refresh, set_join_discovery_model


class Store:
    def __init__(self, resources: list[dict]) -> None:
        self.resources = resources
        self.writes: list[list[dict]] = []

    def list_active_structured_resources(self, active_dataset_id: str) -> list[dict]:
        return self.resources

    def replace_approved_joins(self, active_dataset_id: str, joins: list[dict]) -> int:
        self.writes.append(joins)
        return len(joins)


@pytest.fixture(autouse=True)
def reset_model():
    set_join_discovery_model(None)
    yield
    set_join_discovery_model(None)


def resources() -> list[dict]:
    return [
        {
            "resource_id": "res-orders",
            "resource_key": "structured:orders",
            "runtime_relation_name": "structured_orders",
            "display_name": "Orders",
            "permission_scope_key": "finance",
            "columns": [
                {"column_id": "col-orders-customer", "column_key": "orders_customer", "column_name": "customer_ref", "data_type": "text"},
                {"column_id": "col-orders-amount", "column_key": "orders_amount", "column_name": "amount", "data_type": "numeric"},
            ],
            "rows": [{"customer_ref": "C-100", "amount": "20"}, {"customer_ref": "C-200", "amount": "35"}],
        },
        {
            "resource_id": "res-customers",
            "resource_key": "structured:customers",
            "runtime_relation_name": "structured_customers",
            "display_name": "Customers",
            "permission_scope_key": "finance",
            "columns": [
                {"column_id": "col-customers-id", "column_key": "customers_id", "column_name": "account_code", "data_type": "text"},
                {"column_id": "col-customers-name", "column_key": "customers_name", "column_name": "name", "data_type": "text"},
            ],
            "rows": [{"account_code": "C-100", "name": "A"}, {"account_code": "C-200", "name": "B"}],
        },
    ]


def test_llm_can_approve_different_headers_when_sample_data_supports_join() -> None:
    store = Store(resources())
    set_join_discovery_model(
        lambda _payload: {
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
                    "reason": "Values consistently identify the same entities.",
                    "warnings": [],
                    "limitations": [],
                }
            ],
            "global_warnings": [],
            "limitations": [],
        }
    )

    report = run_approved_join_discovery_refresh(store=store)

    assert report.status == "completed"
    assert report.approved_join_count == 1
    assert store.writes[0][0]["left_resource_id"] == "res-orders"
    assert store.writes[0][0]["right_column_id"] == "col-customers-id"


def test_same_header_pair_does_not_write_without_llm_approval() -> None:
    store = Store(resources())
    set_join_discovery_model(lambda _payload: {"status": "no_candidates", "joins": [], "global_warnings": [], "limitations": []})

    report = run_approved_join_discovery_refresh(store=store)

    assert report.status == "completed_no_approved_joins"
    assert store.writes == [[]]


@pytest.mark.parametrize("label,score", [("medium", 0.95), ("low", 0.95), ("high", 0.89)])
def test_confidence_gate_writes_zero_for_non_high_or_low_score(label: str, score: float) -> None:
    store = Store(resources())
    set_join_discovery_model(
        lambda _payload: {
            "status": "completed",
            "joins": [
                {
                    "status": "approved",
                    "confidence_label": label,
                    "confidence_score": score,
                    "join_type": "inner",
                    "left_resource_key": "structured:orders",
                    "left_column_key": "orders_customer",
                    "right_resource_key": "structured:customers",
                    "right_column_key": "customers_id",
                    "reason": "Candidate evidence.",
                    "warnings": [],
                    "limitations": [],
                }
            ],
            "global_warnings": [],
            "limitations": [],
        }
    )

    report = run_approved_join_discovery_refresh(store=store)

    assert report.approved_join_count == 0
    assert store.writes == [[]]


def test_warnings_present_write_zero_approved_joins() -> None:
    store = Store(resources())
    set_join_discovery_model(
        lambda _payload: {
            "status": "completed",
            "joins": [
                {
                    "status": "approved",
                    "confidence_label": "high",
                    "confidence_score": 0.99,
                    "join_type": "inner",
                    "left_resource_key": "structured:orders",
                    "left_column_key": "orders_customer",
                    "right_resource_key": "structured:customers",
                    "right_column_key": "customers_id",
                    "reason": "Candidate evidence.",
                    "warnings": ["ambiguous"],
                    "limitations": [],
                }
            ],
            "global_warnings": [],
            "limitations": [],
        }
    )

    report = run_approved_join_discovery_refresh(store=store)

    assert report.approved_join_count == 0
    assert store.writes == [[]]


def test_llm_unavailable_fails_closed_without_writes() -> None:
    store = Store(resources())

    report = run_approved_join_discovery_refresh(store=store)

    assert report.status == "failed"
    assert report.validation_errors[0]["code"] == "join_discovery_model_unavailable"
    assert store.writes == []
