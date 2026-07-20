from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.schemas.join_discovery import (
    JOIN_DISCOVERY_STATUSES,
    ApprovedJoinWrite,
    JoinDiscoveryRefreshRequest,
    LLMJoinDiscoveryOutput,
)
from app.services.join_discovery_approved_joins import parse_llm_join_output


def test_refresh_request_schema_is_strict() -> None:
    with pytest.raises(ValidationError):
        JoinDiscoveryRefreshRequest.model_validate({"active_dataset_id": "active", "extra": True})


def test_llm_output_schema_is_strict_and_status_limited() -> None:
    with pytest.raises(ValidationError):
        LLMJoinDiscoveryOutput.model_validate({"status": "maybe", "joins": []})
    with pytest.raises(ValidationError):
        LLMJoinDiscoveryOutput.model_validate({"status": "completed", "joins": [], "extra": True})


def test_parse_llm_join_output_rejects_invalid_json() -> None:
    with pytest.raises(Exception):
        parse_llm_join_output("not json")


def test_approved_join_write_metadata_allowlist_shape() -> None:
    row = ApprovedJoinWrite(
        left_resource_id="res-a",
        left_column_id="col-a",
        right_resource_id="res-b",
        right_column_id="col-b",
        join_type="inner",
        metadata={
            "validation_source": "llm_join_discovery",
            "confidence_label": "high",
            "confidence_score": 0.95,
            "reason": "Consistent identifiers.",
            "active_dataset_id": "active",
            "source_catalog_version": "active",
            "rebuild_run_id": None,
            "sample_policy_summary": {"raw_samples_in_metadata": False},
            "raw_samples_in_metadata": False,
        },
    )

    assert row.validation_status == "approved"
    assert row.is_active is True
    assert row.metadata["raw_samples_in_metadata"] is False


def test_report_status_vocabulary_is_bounded() -> None:
    assert JOIN_DISCOVERY_STATUSES == {"completed", "completed_no_approved_joins", "skipped", "failed"}
