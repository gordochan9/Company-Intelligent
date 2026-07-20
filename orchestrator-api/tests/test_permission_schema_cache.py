from datetime import UTC, datetime, timedelta

from app.graphs.permission_schema.graph import run_get_user_permission_schema
from app.services.permissions.cache import clear_permission_schema_cache, force_cache_entry
from app.services.permissions.schema_builder import build_cache_key


def _state() -> dict:
    return {
        "request_id": "req-cache",
        "trace_id": "trace-cache",
        "openwebui_user_identity": {"email": "user@demo.com", "auth_source": "openwebui"},
        "active_dataset_id": "dataset-1",
        "source_catalog_version": "catalog-1",
    }


def setup_function() -> None:
    clear_permission_schema_cache()


def test_cache_miss_builds_schema_then_second_call_uses_valid_cache() -> None:
    first = run_get_user_permission_schema(_state())
    second = run_get_user_permission_schema(_state())

    assert first["access_status"] == "ok"
    assert first["cache_validation_result"]["status"] == "miss"
    assert second["access_status"] == "ok"
    assert second["cache_validation_result"]["status"] == "valid"


def test_expired_cache_rebuilds_schema() -> None:
    built = run_get_user_permission_schema(_state())
    key = build_cache_key(
        built["trusted_user_context"],
        active_dataset_id="dataset-1",
        source_catalog_version="catalog-1",
        schema_version="3.0",
    )
    force_cache_entry(key, built["user_permission_schema"], datetime.now(UTC) - timedelta(seconds=1))

    result = run_get_user_permission_schema(_state())

    assert result["access_status"] == "ok"
    assert result["cache_validation_result"]["status"] == "expired"


def test_corrupted_cache_fails_closed() -> None:
    built = run_get_user_permission_schema(_state())
    key = build_cache_key(
        built["trusted_user_context"],
        active_dataset_id="dataset-1",
        source_catalog_version="catalog-1",
        schema_version="3.0",
    )
    force_cache_entry(key, {"schema_version": "bad"}, datetime.now(UTC) + timedelta(seconds=300))

    result = run_get_user_permission_schema(_state())

    assert result["access_status"] == "permission_schema_failed"
    assert result["tool_capability_cards"] == []
    assert result["permission_errors"][0]["code"] == "corrupted_cache"


def test_wrong_identity_cache_fails_closed() -> None:
    built = run_get_user_permission_schema(_state())
    key = build_cache_key(
        built["trusted_user_context"],
        active_dataset_id="dataset-1",
        source_catalog_version="catalog-1",
        schema_version="3.0",
    )
    wrong = dict(built["user_permission_schema"])
    wrong["trusted_user_context"] = {**wrong["trusted_user_context"], "email": "other@project3.local"}
    force_cache_entry(key, wrong, datetime.now(UTC) + timedelta(seconds=300))

    result = run_get_user_permission_schema(_state())

    assert result["access_status"] == "permission_schema_failed"
    assert result["permission_errors"][0]["code"] == "wrong_identity_cache"
