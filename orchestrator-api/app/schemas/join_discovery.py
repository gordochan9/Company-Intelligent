from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


JOIN_DISCOVERY_STATUSES = {
    "completed",
    "completed_no_approved_joins",
    "skipped",
    "failed",
}
LLM_OUTPUT_STATUSES = {"completed", "no_candidates", "insufficient_evidence", "error"}
JOIN_DISCOVERY_ALLOWED_JOIN_TYPES = {"inner", "left", "right"}
JOIN_DISCOVERY_MIN_CONFIDENCE_SCORE = 0.9
MAX_JOIN_DISCOVERY_RESOURCES = 20
MAX_JOIN_DISCOVERY_COLUMNS_PER_RESOURCE = 80
MAX_SAMPLE_ROWS_PER_RESOURCE = 20
MAX_SAMPLE_VALUES_PER_COLUMN = 20
MAX_SAMPLE_VALUE_LENGTH = 120
MAX_JOIN_DISCOVERY_PROMPT_CHARS = 60000


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class JoinDiscoveryRefreshRequest(StrictModel):
    active_dataset_id: str = "active"
    source_catalog_version: str | None = "active"
    rebuild_run_id: str | None = None
    reason: Literal["initial_dataset_build", "rebuild_dataset_bat", "manual_join_refresh"] = "manual_join_refresh"
    dry_run: bool = False


class JoinDiscoveryColumnPacket(StrictModel):
    column_key: str
    column_id: str
    column_name: str
    data_type: str = "text"
    safe_description: str = ""
    semantic_tags: list[str] = Field(default_factory=list)
    profile: dict[str, Any] = Field(default_factory=dict)
    sample_values: list[str] = Field(default_factory=list)


class JoinDiscoveryResourcePacket(StrictModel):
    resource_key: str
    resource_id: str
    display_name: str
    source_type: str = "structured"
    scope_keys: list[str]
    columns: list[JoinDiscoveryColumnPacket]
    row_context: list[dict[str, str]] = Field(default_factory=list)


class JoinDiscoveryInputPacket(StrictModel):
    active_dataset_id: str
    source_catalog_version: str | None
    resources: list[JoinDiscoveryResourcePacket]
    allowed_join_types: list[Literal["inner", "left", "right"]]
    confidence: dict[str, Any]
    sample_policy_summary: dict[str, Any]


class LLMJoinCandidate(StrictModel):
    status: Literal["approved", "rejected"]
    confidence_label: Literal["high", "medium", "low", "none"]
    confidence_score: float | None = None
    join_type: Literal["inner", "left", "right"]
    left_resource_key: str
    left_column_key: str
    right_resource_key: str
    right_column_key: str
    reason: str
    warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)

    @field_validator("confidence_score")
    @classmethod
    def confidence_score_in_range(cls, value: float | None) -> float | None:
        if value is not None and not 0 <= value <= 1:
            raise ValueError("confidence_score must be between 0 and 1")
        return value


class LLMJoinDiscoveryOutput(StrictModel):
    status: Literal["completed", "no_candidates", "insufficient_evidence", "error"]
    joins: list[LLMJoinCandidate] = Field(default_factory=list)
    global_warnings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)


class ApprovedJoinWrite(StrictModel):
    left_resource_id: str
    left_column_id: str
    right_resource_id: str
    right_column_id: str
    join_type: Literal["inner", "left", "right"]
    validation_status: Literal["approved"] = "approved"
    confidence: Literal["high"] = "high"
    validation_source: Literal["llm_join_discovery"] = "llm_join_discovery"
    metadata: dict[str, Any]
    is_active: bool = True


class SafeApprovedJoinSummary(StrictModel):
    left_resource_key: str
    left_column_key: str
    right_resource_key: str
    right_column_key: str
    join_type: Literal["inner", "left", "right"]
    confidence_label: Literal["high"] = "high"
    reason: str


class JoinDiscoveryReport(StrictModel):
    status: Literal["completed", "completed_no_approved_joins", "skipped", "failed"]
    active_dataset_id: str
    source_catalog_version: str | None = None
    rebuild_run_id: str | None = None
    resources_considered: int = 0
    columns_considered: int = 0
    llm_status: str | None = None
    approved_join_count: int = 0
    rejected_join_count: int = 0
    skipped_join_count: int = 0
    approved_joins: list[SafeApprovedJoinSummary] = Field(default_factory=list)
    validation_errors: list[dict[str, str]] = Field(default_factory=list)
    warnings: list[dict[str, str]] = Field(default_factory=list)
    sample_policy_summary: dict[str, Any] = Field(default_factory=dict)
    audit_event_ids: list[str] = Field(default_factory=list)
    exit_code: int = 0

    def as_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
