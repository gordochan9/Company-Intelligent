from __future__ import annotations

from app.services.join_discovery_approved_joins import run_approved_join_discovery_refresh, set_join_discovery_model
from test_join_discovery_llm_candidate_approval import Store, resources


def setup_function() -> None:
    set_join_discovery_model(None)


def teardown_function() -> None:
    set_join_discovery_model(None)


def _approval(left: str = "orders_customer", right: str = "customers_id") -> dict:
    return {
        "status": "completed",
        "joins": [
            {
                "status": "approved",
                "confidence_label": "high",
                "confidence_score": 0.96,
                "join_type": "inner",
                "left_resource_key": "structured:orders",
                "left_column_key": left,
                "right_resource_key": "structured:customers",
                "right_column_key": right,
                "reason": "Stable identifier relationship.",
                "warnings": [],
                "limitations": [],
            }
        ],
        "global_warnings": [],
        "limitations": [],
    }


def test_written_row_uses_db_compatible_contract_and_safe_metadata() -> None:
    store = Store(resources())
    set_join_discovery_model(lambda _payload: _approval())

    report = run_approved_join_discovery_refresh(store=store)
    row = store.writes[0][0]

    assert report.approved_join_count == 1
    assert row["validation_status"] == "approved"
    assert row["validation_source"] == "llm_join_discovery"
    assert row["confidence"] == "high"
    assert row["is_active"] is True
    assert row["metadata"]["raw_samples_in_metadata"] is False
    assert "C-100" not in repr(row["metadata"])


def test_refresh_replaces_prior_approved_joins_transactionally() -> None:
    store = Store(resources())
    set_join_discovery_model(lambda _payload: _approval())

    run_approved_join_discovery_refresh(store=store)
    run_approved_join_discovery_refresh(store=store)

    assert len(store.writes) == 2
    assert len(store.writes[-1]) == 1


def test_invented_resource_or_column_is_not_persisted() -> None:
    store = Store(resources())
    set_join_discovery_model(lambda _payload: _approval(left="missing"))

    report = run_approved_join_discovery_refresh(store=store)

    assert report.approved_join_count == 0
    assert store.writes == [[]]


def test_duplicate_reverse_pairs_are_deduped() -> None:
    output = _approval()
    output["joins"].append(
        {
            "status": "approved",
            "confidence_label": "high",
            "confidence_score": 0.96,
            "join_type": "inner",
            "left_resource_key": "structured:customers",
            "left_column_key": "customers_id",
            "right_resource_key": "structured:orders",
            "right_column_key": "orders_customer",
            "reason": "Same relationship reversed.",
            "warnings": [],
            "limitations": [],
        }
    )
    store = Store(resources())
    set_join_discovery_model(lambda _payload: output)

    report = run_approved_join_discovery_refresh(store=store)

    assert report.approved_join_count == 1
    assert len(store.writes[0]) == 1


def test_dry_run_writes_zero_rows() -> None:
    store = Store(resources())
    set_join_discovery_model(lambda _payload: _approval())

    report = run_approved_join_discovery_refresh({"dry_run": True}, store=store)

    assert report.status == "skipped"
    assert store.writes == []
