from __future__ import annotations

from app.schemas.join_discovery import JoinDiscoveryRefreshRequest
from app.services.join_discovery_approved_joins import build_join_discovery_input_packet, run_approved_join_discovery_refresh, set_join_discovery_model
from test_join_discovery_llm_candidate_approval import Store, resources


def teardown_function() -> None:
    set_join_discovery_model(None)


def test_unsafe_paths_are_redacted_from_llm_packet() -> None:
    packet, errors = build_join_discovery_input_packet(
        [
            {
                "resource_id": "res",
                "resource_key": "structured:path",
                "runtime_relation_name": "structured_path",
                "display_name": r"C:\Users\Redacted\secret.csv",
                "permission_scope_key": "finance",
                "columns": [{"column_id": "col", "column_key": "id", "column_name": "id", "data_type": "text"}],
                "rows": [{"id": r"C:\Users\Redacted\secret.csv"}],
            }
        ],
        JoinDiscoveryRefreshRequest(),
    )

    assert errors == []
    assert packet.resources[0].display_name == "[REDACTED]"
    assert packet.resources[0].row_context[0]["id"] == "[REDACTED]"


def test_inactive_or_scope_missing_resources_are_not_sent_to_llm() -> None:
    packet, errors = build_join_discovery_input_packet(
        [
            {
                "resource_id": "inactive",
                "resource_key": "structured:inactive",
                "runtime_relation_name": "structured_inactive",
                "display_name": "Inactive",
                "permission_scope_key": "finance",
                "is_active": False,
                "columns": [{"column_id": "col", "column_key": "id", "column_name": "id"}],
            },
            {
                "resource_id": "missing-scope",
                "resource_key": "structured:missing",
                "runtime_relation_name": "structured_missing",
                "display_name": "Missing",
                "columns": [{"column_id": "col", "column_key": "id", "column_name": "id"}],
            },
        ],
        JoinDiscoveryRefreshRequest(),
    )

    assert errors == []
    assert packet.resources == []


def test_raw_sql_in_llm_reason_is_rejected_and_not_written() -> None:
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
                    "reason": "SELECT * FROM private_table JOIN other_table",
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
    assert "SELECT" not in repr(report.as_dict())


def test_sample_values_in_llm_reason_are_not_persisted_or_reported() -> None:
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
                    "reason": "Sample values C-100 and C-200 overlap.",
                    "warnings": [],
                    "limitations": [],
                }
            ],
            "global_warnings": [],
            "limitations": [],
        }
    )

    report = run_approved_join_discovery_refresh(store=store)

    assert report.approved_join_count == 1
    assert "C-100" not in repr(report.as_dict())
    assert "C-100" not in repr(store.writes)
