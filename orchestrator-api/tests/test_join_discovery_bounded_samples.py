from __future__ import annotations

from app.schemas.join_discovery import JoinDiscoveryRefreshRequest, MAX_SAMPLE_ROWS_PER_RESOURCE, MAX_SAMPLE_VALUE_LENGTH, MAX_SAMPLE_VALUES_PER_COLUMN
from app.services.join_discovery_approved_joins import build_join_discovery_input_packet, build_join_discovery_prompt


def test_llm_packet_receives_bounded_real_samples_and_row_context() -> None:
    rows = [{"id": f"C-{index}", "amount": str(index)} for index in range(50)]
    packet, errors = build_join_discovery_input_packet(
        [
            {
                "resource_id": "res",
                "resource_key": "structured:orders",
                "runtime_relation_name": "structured_orders",
                "display_name": "Orders",
                "permission_scope_key": "finance",
                "columns": [{"column_id": "col-id", "column_key": "id", "column_name": "id", "data_type": "text"}],
                "rows": rows,
            }
        ],
        JoinDiscoveryRefreshRequest(),
    )

    assert errors == []
    resource = packet.resources[0]
    assert len(resource.row_context) == MAX_SAMPLE_ROWS_PER_RESOURCE
    assert resource.row_context[0]["id"] == "C-0"
    assert len(resource.columns[0].sample_values) == MAX_SAMPLE_VALUES_PER_COLUMN


def test_prompt_does_not_receive_full_table_dump_or_unbounded_values() -> None:
    long_value = "x" * (MAX_SAMPLE_VALUE_LENGTH + 20)
    packet, _errors = build_join_discovery_input_packet(
        [
            {
                "resource_id": "res",
                "resource_key": "structured:orders",
                "runtime_relation_name": "structured_orders",
                "display_name": "Orders",
                "permission_scope_key": "finance",
                "columns": [{"column_id": "col-id", "column_key": "id", "column_name": "id", "data_type": "text"}],
                "rows": [{"id": long_value}],
            }
        ],
        JoinDiscoveryRefreshRequest(),
    )

    prompt = build_join_discovery_prompt(packet)
    sample = prompt["payload"]["resources"][0]["row_context"][0]["id"]

    assert len(sample) == MAX_SAMPLE_VALUE_LENGTH
    assert prompt["payload"]["sample_policy_summary"]["raw_samples_in_metadata"] is False
