from __future__ import annotations

import psycopg
import subprocess
import sys

from app.db.runtime_store import PostgresRuntimeStore
from app.schemas.join_discovery import JoinDiscoveryRefreshRequest
from app.services import join_discovery_approved_joins
from app.services.join_discovery_approved_joins import build_join_discovery_input_packet, set_join_discovery_model
from app.services.llm_provider import deepseek_join_discovery
from test_join_discovery_llm_candidate_approval import Store, resources


class _Rows:
    def __init__(self, rows: list[dict]) -> None:
        self._rows = rows

    def fetchall(self) -> list[dict]:
        return self._rows


class _Connection:
    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def execute(self, query):
        if isinstance(query, str):
            return _Rows(
                [
                    {
                        "resource_id": "resource-id",
                        "resource_key": "structured:orders",
                        "runtime_relation_name": "structured_orders",
                        "display_name": "Orders",
                        "permission_scope_key": "finance",
                        "metadata": {},
                        "column_id": "column-id",
                        "column_name": "customer_id",
                        "data_type": "text",
                        "safe_description": "Customer identifier.",
                    }
                ]
            )
        return _Rows([{"customer_id": "C-1"}])


def test_production_resource_contract_keeps_join_discovery_column_ids(monkeypatch) -> None:
    monkeypatch.setattr(psycopg, "connect", lambda *_args, **_kwargs: _Connection())

    resources = PostgresRuntimeStore("postgresql://unused").list_structured_resources()
    column = resources[0]["columns"][0]
    packet, errors = build_join_discovery_input_packet(resources, JoinDiscoveryRefreshRequest())

    assert column["column_id"] == "column-id"
    assert column["column_key"] == "column-id"
    assert errors == []
    assert packet.resources[0].columns[0].column_id == "column-id"


def test_join_discovery_defaults_to_central_llm_provider() -> None:
    assert join_discovery_approved_joins._join_discovery_model is deepseek_join_discovery


def test_join_discovery_model_remains_injectable_for_tests() -> None:
    default_model = join_discovery_approved_joins._join_discovery_model
    fake_model = lambda _prompt: {"status": "no_candidates", "joins": [], "global_warnings": [], "limitations": []}

    set_join_discovery_model(fake_model)

    try:
        assert join_discovery_approved_joins._join_discovery_model is fake_model
    finally:
        set_join_discovery_model(default_model)


def test_default_provider_missing_api_key_fails_closed(monkeypatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    store = Store(resources())

    report = join_discovery_approved_joins.run_approved_join_discovery_refresh(store=store)

    assert report.status == "failed"
    assert report.approved_join_count == 0
    assert store.writes == []


def test_join_refresh_cli_import_has_default_provider_without_app_main() -> None:
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            "import sys; import app.scripts.rebuild_approved_joins; "
            "from app.services.join_discovery_approved_joins import _join_discovery_model; "
            "from app.services.llm_provider import deepseek_join_discovery; "
            "assert 'app.main' not in sys.modules; "
            "assert _join_discovery_model is deepseek_join_discovery",
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
