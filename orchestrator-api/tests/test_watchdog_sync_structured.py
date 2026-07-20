from __future__ import annotations

from pathlib import Path

from test_watchdog_sync_documents import Store

from app.services.watchdog_runtime import normalize_watchdog_event
from app.services.watchdog_sync import apply_watchdog_event_batch


def test_created_csv_refreshes_structured_metadata_and_runtime_relation(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "orders.csv"
    path.parent.mkdir()
    path.write_text("id,amount\n1,10\n", encoding="utf-8")
    store = Store()

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "created", path)], store=store)

    assert report.status == "ok"
    assert report.structured_resources_refreshed == 1
    assert store.structured["Finance/orders.csv"][0].resource_key == "structured:finance:orders"
    assert [column["data_type"] for column in store.structured["Finance/orders.csv"][0].columns] == ["integer", "integer"]
    assert store.structured["Finance/orders.csv"][0].rows == [{"id": 1, "amount": 10}]


def test_invalid_csv_header_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "bad.csv"
    path.parent.mkdir()
    path.write_text(",amount\n1,10\n", encoding="utf-8")

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "created", path)], store=Store())

    assert report.status == "validation_failed"
    assert report.validation_errors[0]["code"] == "invalid_structured_headers"


def test_duplicate_csv_header_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "bad.csv"
    path.parent.mkdir()
    path.write_text("id,id\n1,2\n", encoding="utf-8")

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "created", path)], store=Store())

    assert report.status == "validation_failed"
    assert report.validation_errors[0]["code"] == "duplicate_structured_headers"


def test_deleted_csv_removes_structured_runtime_visibility_and_recommends_join_refresh(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "orders.csv"
    path.parent.mkdir()
    path.write_text("id,amount\n1,10\n", encoding="utf-8")
    store = Store()

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "deleted", path)], store=store)

    assert report.structured_resources_deleted == 1
    assert report.join_refresh_recommended is True
    assert store.deleted_structured == ["Finance/orders.csv"]
