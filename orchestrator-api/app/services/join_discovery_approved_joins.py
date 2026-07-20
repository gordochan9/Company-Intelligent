from __future__ import annotations

import json
import re
from typing import Any, Callable, Protocol

from pydantic import ValidationError

from app.schemas.audit_trace import AuditEventCategory, AuditEventStatus
from app.schemas.join_discovery import (
    JOIN_DISCOVERY_ALLOWED_JOIN_TYPES,
    JOIN_DISCOVERY_MIN_CONFIDENCE_SCORE,
    MAX_JOIN_DISCOVERY_COLUMNS_PER_RESOURCE,
    MAX_JOIN_DISCOVERY_PROMPT_CHARS,
    MAX_JOIN_DISCOVERY_RESOURCES,
    MAX_SAMPLE_ROWS_PER_RESOURCE,
    MAX_SAMPLE_VALUE_LENGTH,
    MAX_SAMPLE_VALUES_PER_COLUMN,
    ApprovedJoinWrite,
    JoinDiscoveryInputPacket,
    JoinDiscoveryRefreshRequest,
    JoinDiscoveryReport,
    LLMJoinCandidate,
    LLMJoinDiscoveryOutput,
    SafeApprovedJoinSummary,
)
from app.services.audit_trace import emit_audit_event
from app.services.llm_provider import (
    LLMProviderResponseEmpty,
    LLMProviderTimeout,
    LLMProviderUnavailable,
    deepseek_join_discovery,
)


SAFE_TEXT_RE = re.compile(r"(?:[A-Za-z]:\\Users\\|/Users/|/mnt/c/Users/|file://|postgres(?:ql)?://|sk-[A-Za-z0-9_-]{8,})", re.IGNORECASE)
RAW_SQL_RE = re.compile(r"\b(select|insert|update|delete|merge|drop|alter)\b.+\b(from|into|table|join|set)\b", re.IGNORECASE | re.DOTALL)
SAFE_APPROVAL_REASON = "Approved by the LLM and backend validation."
_JoinDiscoveryModel = Callable[[dict[str, Any]], dict[str, Any] | str]
_join_discovery_model: _JoinDiscoveryModel | None = deepseek_join_discovery


class JoinDiscoveryStore(Protocol):
    def list_active_structured_resources(self, active_dataset_id: str) -> list[dict[str, Any]]:
        ...

    def replace_approved_joins(self, active_dataset_id: str, joins: list[dict[str, Any]]) -> int:
        ...


def set_join_discovery_model(model: _JoinDiscoveryModel | None) -> None:
    global _join_discovery_model
    _join_discovery_model = model


def run_approved_join_discovery_refresh(
    request: JoinDiscoveryRefreshRequest | dict[str, Any] | None = None,
    *,
    store: JoinDiscoveryStore | None = None,
) -> JoinDiscoveryReport:
    try:
        refresh_request = request if isinstance(request, JoinDiscoveryRefreshRequest) else JoinDiscoveryRefreshRequest.model_validate(request or {})
    except ValidationError:
        return _report("failed", "active", validation_errors=[_error("invalid_refresh_request", "Join discovery request is invalid.")], exit_code=1)

    if store is None:
        return _report(
            "failed",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            validation_errors=[_error("join_discovery_store_not_configured", "Join discovery store is not configured.")],
            exit_code=1,
        )

    try:
        raw_resources = store.list_active_structured_resources(refresh_request.active_dataset_id)
    except Exception:
        return _report(
            "failed",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            validation_errors=[_error("structured_resource_read_failed", "Structured resources could not be read.")],
            exit_code=1,
        )

    packet, input_errors = build_join_discovery_input_packet(raw_resources, refresh_request)
    if input_errors:
        return _report(
            "failed",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            validation_errors=input_errors,
            exit_code=1,
        )
    if not packet.resources:
        return _report(
            "completed_no_approved_joins",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            sample_policy_summary=packet.sample_policy_summary,
        )
    if refresh_request.dry_run:
        return _report(
            "skipped",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            resources_considered=len(packet.resources),
            columns_considered=sum(len(resource.columns) for resource in packet.resources),
            sample_policy_summary=packet.sample_policy_summary,
            warnings=[_warning("dry_run_no_write", "Dry run built the LLM packet but wrote zero joins.")],
        )
    if _join_discovery_model is None:
        return _report(
            "failed",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            resources_considered=len(packet.resources),
            columns_considered=sum(len(resource.columns) for resource in packet.resources),
            sample_policy_summary=packet.sample_policy_summary,
            validation_errors=[_error("join_discovery_model_unavailable", "Join discovery model is unavailable.")],
            exit_code=1,
        )

    try:
        raw_output = _join_discovery_model(build_join_discovery_prompt(packet))
        llm_output = parse_llm_join_output(raw_output)
    except Exception as exc:
        code, message = _classify_llm_failure(exc)
        return _report(
            "failed",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            resources_considered=len(packet.resources),
            columns_considered=sum(len(resource.columns) for resource in packet.resources),
            sample_policy_summary=packet.sample_policy_summary,
            validation_errors=[_error(code, message)],
            exit_code=1,
        )

    approved, summaries, rejected_count, skipped_count, validation_errors = validate_llm_join_output(llm_output, packet, refresh_request)
    if validation_errors:
        return _report(
            "failed",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            resources_considered=len(packet.resources),
            columns_considered=sum(len(resource.columns) for resource in packet.resources),
            llm_status=llm_output.status,
            sample_policy_summary=packet.sample_policy_summary,
            rejected_join_count=rejected_count,
            skipped_join_count=skipped_count,
            validation_errors=validation_errors,
            exit_code=1,
        )

    try:
        written = store.replace_approved_joins(refresh_request.active_dataset_id, [join.model_dump(mode="json") for join in approved])
    except Exception:
        return _report(
            "failed",
            refresh_request.active_dataset_id,
            source_catalog_version=refresh_request.source_catalog_version,
            rebuild_run_id=refresh_request.rebuild_run_id,
            resources_considered=len(packet.resources),
            columns_considered=sum(len(resource.columns) for resource in packet.resources),
            llm_status=llm_output.status,
            sample_policy_summary=packet.sample_policy_summary,
            validation_errors=[_error("approved_join_write_failed", "Approved joins could not be replaced transactionally.")],
            exit_code=1,
        )

    status = "completed" if written else "completed_no_approved_joins"
    audit = emit_audit_event(
        request_id=refresh_request.rebuild_run_id,
        trace_id=None,
        event_category=AuditEventCategory.JOIN_DISCOVERY,
        event_type="approved_join_refresh",
        status=AuditEventStatus.SUCCEEDED,
        workflow_name="join_discovery_approved_joins",
        node_name="run_approved_join_discovery_refresh",
        metadata={
            "active_dataset_id": refresh_request.active_dataset_id,
            "resources_considered": len(packet.resources),
            "columns_considered": sum(len(resource.columns) for resource in packet.resources),
            "approved_join_count": written,
            "raw_samples_in_metadata": False,
        },
    )
    audit_ids = [audit.event.trace_id] if audit.event else []
    return _report(
        status,
        refresh_request.active_dataset_id,
        source_catalog_version=refresh_request.source_catalog_version,
        rebuild_run_id=refresh_request.rebuild_run_id,
        resources_considered=len(packet.resources),
        columns_considered=sum(len(resource.columns) for resource in packet.resources),
        llm_status=llm_output.status,
        approved_join_count=written,
        rejected_join_count=rejected_count,
        skipped_join_count=skipped_count,
        approved_joins=summaries[:written],
        sample_policy_summary=packet.sample_policy_summary,
        audit_event_ids=audit_ids,
    )


def build_join_discovery_input_packet(
    resources: list[dict[str, Any]],
    request: JoinDiscoveryRefreshRequest,
) -> tuple[JoinDiscoveryInputPacket, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    packet_resources = []
    active = [resource for resource in resources if resource.get("is_active", True)]
    if len(active) > MAX_JOIN_DISCOVERY_RESOURCES:
        errors.append(_error("join_discovery_input_too_large", "Structured resource count exceeds join discovery bounds."))
        active = []

    for resource in active:
        resource_id = str(resource.get("resource_id") or "")
        resource_key = str(resource.get("resource_key") or "")
        scope_keys = _scope_keys(resource)
        if not resource_id or not resource_key or not resource.get("runtime_relation_name") or not scope_keys:
            continue
        columns = []
        rows = [_safe_row(row) for row in list(resource.get("rows") or resource.get("safe_row_samples") or [])[:MAX_SAMPLE_ROWS_PER_RESOURCE]]
        for column in list(resource.get("columns") or [])[:MAX_JOIN_DISCOVERY_COLUMNS_PER_RESOURCE]:
            if column.get("is_active", True) is False or column.get("is_queryable", True) is False:
                continue
            column_id = str(column.get("column_id") or "")
            column_name = str(column.get("column_name") or "")
            if not column_id or not column_name:
                continue
            column_key = str(column.get("column_key") or column_id)
            columns.append(
                {
                    "column_key": column_key,
                    "column_id": column_id,
                    "column_name": _safe_text(column_name),
                    "data_type": _safe_text(column.get("data_type") or "text"),
                    "safe_description": _safe_text(column.get("safe_description") or ""),
                    "semantic_tags": [_safe_text(tag) for tag in list(column.get("semantic_tags") or [])[:10]],
                    "profile": _safe_mapping((column.get("metadata") or {}).get("profile") or column.get("profile") or {}),
                    "sample_values": _sample_values(rows, column_name),
                }
            )
        if columns:
            packet_resources.append(
                {
                    "resource_key": resource_key,
                    "resource_id": resource_id,
                    "display_name": _safe_text(resource.get("display_name") or resource_key),
                    "source_type": _safe_text(resource.get("source_type") or "structured"),
                    "scope_keys": [_safe_text(scope) for scope in scope_keys],
                    "columns": columns,
                    "row_context": rows,
                }
            )
    sample_policy = {
        "max_resources": MAX_JOIN_DISCOVERY_RESOURCES,
        "max_columns_per_resource": MAX_JOIN_DISCOVERY_COLUMNS_PER_RESOURCE,
        "max_rows_per_resource": MAX_SAMPLE_ROWS_PER_RESOURCE,
        "max_values_per_column": MAX_SAMPLE_VALUES_PER_COLUMN,
        "max_value_length": MAX_SAMPLE_VALUE_LENGTH,
        "raw_samples_in_metadata": False,
    }
    return (
        JoinDiscoveryInputPacket(
            active_dataset_id=request.active_dataset_id,
            source_catalog_version=request.source_catalog_version,
            resources=packet_resources,
            allowed_join_types=sorted(JOIN_DISCOVERY_ALLOWED_JOIN_TYPES),
            confidence={"required_label": "high", "minimum_score": JOIN_DISCOVERY_MIN_CONFIDENCE_SCORE},
            sample_policy_summary=sample_policy,
        ),
        errors,
    )


def build_join_discovery_prompt(packet: JoinDiscoveryInputPacket) -> dict[str, Any]:
    payload = packet.model_dump(mode="json")
    prompt = {
        "system_prompt": (
            "You are discovering approved join relationships for a governed SQL system. "
            "Propose and approve joins only between resources and columns in the packet. "
            "Use bounded real sample values, row context, profiles, data types, semantic tags, and names. "
            "Do not approve joins from matching headers alone. Do not invent IDs. Do not output SQL. "
            "Return only the strict JSON contract."
        ),
        "payload": payload,
        "output_schema": LLMJoinDiscoveryOutput.model_json_schema(),
    }
    if len(json.dumps(prompt, sort_keys=True)) > MAX_JOIN_DISCOVERY_PROMPT_CHARS:
        raise ValueError("join_discovery_prompt_too_large")
    return prompt


def parse_llm_join_output(raw_output: dict[str, Any] | str | None) -> LLMJoinDiscoveryOutput:
    if raw_output is None or isinstance(raw_output, str) and not raw_output.strip():
        raise LLMProviderResponseEmpty("Join discovery model response was empty.")
    if isinstance(raw_output, str):
        raw_output = json.loads(raw_output)
    return LLMJoinDiscoveryOutput.model_validate(raw_output)


def _classify_llm_failure(exc: Exception) -> tuple[str, str]:
    if isinstance(exc, (LLMProviderTimeout, TimeoutError)):
        return "join_discovery_provider_timeout", "Join discovery provider timed out."
    if isinstance(exc, LLMProviderResponseEmpty):
        return "join_discovery_llm_response_empty", "Join discovery model response was empty."
    if isinstance(exc, LLMProviderUnavailable):
        return "join_discovery_provider_unavailable", "Join discovery provider is unavailable."
    if isinstance(exc, json.JSONDecodeError):
        return "join_discovery_llm_json_invalid", "Join discovery model response was not valid JSON."
    if isinstance(exc, ValidationError):
        return "join_discovery_llm_schema_invalid", "Join discovery model response did not match the required schema."
    if isinstance(exc, ValueError) and str(exc) == "join_discovery_prompt_too_large":
        return "join_discovery_input_too_large", "Join discovery input exceeds the configured prompt bound."
    return "join_discovery_provider_unavailable", "Join discovery provider is unavailable."


def validate_llm_join_output(
    output: LLMJoinDiscoveryOutput,
    packet: JoinDiscoveryInputPacket,
    request: JoinDiscoveryRefreshRequest,
) -> tuple[list[ApprovedJoinWrite], list[SafeApprovedJoinSummary], int, int, list[dict[str, str]]]:
    errors: list[dict[str, str]] = []
    if output.status == "error":
        return [], [], 0, len(output.joins), [_error("join_discovery_llm_error_status", "Join discovery model returned error status.")]
    if output.global_warnings:
        return [], [], 0, len(output.joins), [_error("join_discovery_global_warnings", "Join discovery model returned global warnings.")]
    if output.limitations:
        return [], [], 0, len(output.joins), [_error("join_discovery_global_limitations", "Join discovery model returned global limitations.")]

    resource_index = {resource.resource_key: resource for resource in packet.resources}
    column_index = {
        (resource.resource_key, column.column_key): (resource, column)
        for resource in packet.resources
        for column in resource.columns
    }
    approved: list[ApprovedJoinWrite] = []
    summaries: list[SafeApprovedJoinSummary] = []
    rejected_count = 0
    skipped_count = 0
    seen_pairs: set[tuple[tuple[str, str], tuple[str, str]]] = set()
    for candidate in output.joins:
        if candidate.status != "approved":
            rejected_count += 1
            continue
        skip_reason = _candidate_skip_reason(candidate, resource_index, column_index, seen_pairs)
        if skip_reason:
            skipped_count += 1
            continue
        left_resource, left_column = column_index[(candidate.left_resource_key, candidate.left_column_key)]
        right_resource, right_column = column_index[(candidate.right_resource_key, candidate.right_column_key)]
        pair = _normalized_pair(candidate)
        seen_pairs.add(pair)
        metadata = {
            "validation_source": "llm_join_discovery",
            "confidence_label": "high",
            "confidence_score": float(candidate.confidence_score or 0),
            "reason": SAFE_APPROVAL_REASON,
            "active_dataset_id": request.active_dataset_id,
            "source_catalog_version": request.source_catalog_version,
            "rebuild_run_id": request.rebuild_run_id,
            "sample_policy_summary": packet.sample_policy_summary,
            "raw_samples_in_metadata": False,
        }
        approved.append(
            ApprovedJoinWrite(
                left_resource_id=left_resource.resource_id,
                left_column_id=left_column.column_id,
                right_resource_id=right_resource.resource_id,
                right_column_id=right_column.column_id,
                join_type=candidate.join_type,
                metadata=metadata,
            )
        )
        summaries.append(
            SafeApprovedJoinSummary(
                left_resource_key=candidate.left_resource_key,
                left_column_key=candidate.left_column_key,
                right_resource_key=candidate.right_resource_key,
                right_column_key=candidate.right_column_key,
                join_type=candidate.join_type,
                reason=SAFE_APPROVAL_REASON,
            )
        )
    return approved, summaries, rejected_count, skipped_count, errors


def _candidate_skip_reason(
    candidate: LLMJoinCandidate,
    resource_index: dict[str, Any],
    column_index: dict[tuple[str, str], Any],
    seen_pairs: set[tuple[tuple[str, str], tuple[str, str]]],
) -> str | None:
    if candidate.confidence_label != "high":
        return "confidence_not_high"
    if candidate.confidence_score is None or candidate.confidence_score < JOIN_DISCOVERY_MIN_CONFIDENCE_SCORE:
        return "confidence_below_threshold"
    if candidate.warnings:
        return "warnings_present"
    if candidate.limitations:
        return "limitations_present"
    if candidate.left_resource_key not in resource_index or candidate.right_resource_key not in resource_index:
        return "unknown_resource"
    if (candidate.left_resource_key, candidate.left_column_key) not in column_index:
        return "unknown_left_column"
    if (candidate.right_resource_key, candidate.right_column_key) not in column_index:
        return "unknown_right_column"
    if (candidate.left_resource_key, candidate.left_column_key) == (candidate.right_resource_key, candidate.right_column_key):
        return "same_column_self_join"
    if _normalized_pair(candidate) in seen_pairs:
        return "duplicate_join"
    if _unsafe_text(candidate.reason):
        return "unsafe_reason"
    return None


def _normalized_pair(candidate: LLMJoinCandidate) -> tuple[tuple[str, str], tuple[str, str]]:
    left = (candidate.left_resource_key, candidate.left_column_key)
    right = (candidate.right_resource_key, candidate.right_column_key)
    return tuple(sorted([left, right]))  # type: ignore[return-value]


def _scope_keys(resource: dict[str, Any]) -> list[str]:
    raw = resource.get("scope_keys") or resource.get("permission_scope_keys") or []
    if isinstance(raw, str):
        return [raw]
    if not raw and resource.get("permission_scope_key"):
        return [str(resource["permission_scope_key"])]
    return [str(item) for item in raw if item]


def _sample_values(rows: list[dict[str, str]], column_name: str) -> list[str]:
    values = []
    for row in rows:
        value = row.get(column_name)
        if value and value not in values:
            values.append(value)
        if len(values) >= MAX_SAMPLE_VALUES_PER_COLUMN:
            break
    return values


def _safe_row(row: Any) -> dict[str, str]:
    if not isinstance(row, dict):
        return {}
    return {str(key): _safe_text(value) for key, value in row.items()}


def _safe_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        return {}
    return {str(key): _safe_text(item) if isinstance(item, str) else item for key, item in value.items()}


def _safe_text(value: Any) -> str:
    text = str(value or "")[:MAX_SAMPLE_VALUE_LENGTH]
    return "[REDACTED]" if SAFE_TEXT_RE.search(text) else text


def _unsafe_text(value: str) -> bool:
    return bool(SAFE_TEXT_RE.search(value) or RAW_SQL_RE.search(value))


def _error(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _warning(code: str, message: str) -> dict[str, str]:
    return {"code": code, "message": message}


def _report(
    status: str,
    active_dataset_id: str,
    *,
    source_catalog_version: str | None = None,
    rebuild_run_id: str | None = None,
    resources_considered: int = 0,
    columns_considered: int = 0,
    llm_status: str | None = None,
    approved_join_count: int = 0,
    rejected_join_count: int = 0,
    skipped_join_count: int = 0,
    approved_joins: list[SafeApprovedJoinSummary] | None = None,
    validation_errors: list[dict[str, str]] | None = None,
    warnings: list[dict[str, str]] | None = None,
    sample_policy_summary: dict[str, Any] | None = None,
    audit_event_ids: list[str] | None = None,
    exit_code: int = 0,
) -> JoinDiscoveryReport:
    return JoinDiscoveryReport(
        status=status,  # type: ignore[arg-type]
        active_dataset_id=active_dataset_id,
        source_catalog_version=source_catalog_version,
        rebuild_run_id=rebuild_run_id,
        resources_considered=resources_considered,
        columns_considered=columns_considered,
        llm_status=llm_status,
        approved_join_count=approved_join_count,
        rejected_join_count=rejected_join_count,
        skipped_join_count=skipped_join_count,
        approved_joins=approved_joins or [],
        validation_errors=validation_errors or [],
        warnings=warnings or [],
        sample_policy_summary=sample_policy_summary or {},
        audit_event_ids=audit_event_ids or [],
        exit_code=exit_code,
    )
