from __future__ import annotations

from pathlib import Path

from test_watchdog_sync_documents import Store

from app.services.watchdog_runtime import normalize_watchdog_event
from app.services.watchdog_sync import apply_watchdog_event_batch


class FailingMaterializationStore(Store):
    def refresh_structured(self, relative_path, permission_scope_key, profiles):
        return {"runtime_relation_validated": False, "columns_changed": False}


class HeaderChangedStore(Store):
    def refresh_structured(self, relative_path, permission_scope_key, profiles):
        self.structured[relative_path] = profiles
        return {"runtime_relation_validated": True, "columns_changed": True}


def test_structured_metadata_not_trusted_when_runtime_relation_validation_fails(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "orders.csv"
    path.parent.mkdir()
    path.write_text("id,amount\n1,10\n", encoding="utf-8")

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "modified", path)], store=FailingMaterializationStore())

    assert report.status == "full_rebuild_required"
    assert report.validation_errors[0]["code"] == "runtime_relation_validation_failed"


def test_header_change_sets_join_refresh_recommended_without_join_discovery(tmp_path: Path) -> None:
    path = tmp_path / "Finance" / "orders.csv"
    path.parent.mkdir()
    path.write_text("id,amount,new_header\n1,10,x\n", encoding="utf-8")

    report = apply_watchdog_event_batch(tmp_path, [normalize_watchdog_event(tmp_path, "modified", path)], store=HeaderChangedStore())

    assert report.status == "ok"
    assert report.join_refresh_recommended is True
    assert "approved_join" not in repr(report.as_dict())
