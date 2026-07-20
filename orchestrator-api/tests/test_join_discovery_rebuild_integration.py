from __future__ import annotations

import json

from app.scripts import rebuild_dataset
from app.schemas.dataset_rebuild import RebuildReport
from app.schemas.join_discovery import JoinDiscoveryReport


def test_rebuild_script_triggers_join_discovery_after_successful_structured_import(monkeypatch, capsys) -> None:
    def fake_rebuild(_dataset_root=None, *, dry_run=False):
        return RebuildReport(
            status="ok",
            active_dataset_id="active",
            dataset_root_label="active_dataset",
            source_catalog_version="v1",
            join_refresh_required=True,
            exit_code=0,
        )

    calls = []

    def fake_join_refresh(request):
        calls.append(request)
        return JoinDiscoveryReport(status="completed_no_approved_joins", active_dataset_id=request.active_dataset_id)

    monkeypatch.setattr(rebuild_dataset, "run_rebuild", fake_rebuild)
    monkeypatch.setattr(rebuild_dataset, "run_approved_join_discovery_refresh", fake_join_refresh)

    exit_code = rebuild_dataset.main([])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert calls[0].reason == "rebuild_dataset_bat"
    assert output["join_discovery_report"]["status"] == "completed_no_approved_joins"


def test_rebuild_script_does_not_trigger_join_discovery_before_structured_resources(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        rebuild_dataset,
        "run_rebuild",
        lambda _dataset_root=None, *, dry_run=False: RebuildReport(
            status="ok",
            active_dataset_id="active",
            dataset_root_label="active_dataset",
            source_catalog_version="v1",
            join_refresh_required=False,
            exit_code=0,
        ),
    )
    monkeypatch.setattr(rebuild_dataset, "run_approved_join_discovery_refresh", lambda _request: (_ for _ in ()).throw(AssertionError("should not run")))

    exit_code = rebuild_dataset.main([])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert "join_discovery_report" not in output
