from __future__ import annotations

import argparse
import json
import sys

from app.schemas.join_discovery import JoinDiscoveryRefreshRequest
from app.db.runtime_store import PostgresRuntimeStore
from app.services.join_discovery_approved_joins import run_approved_join_discovery_refresh


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Refresh Project 3.0 approved join relationships.")
    parser.add_argument("--active-dataset-id", default="active")
    parser.add_argument("--source-catalog-version", default="active")
    parser.add_argument("--rebuild-run-id")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    report = run_approved_join_discovery_refresh(
        JoinDiscoveryRefreshRequest(
            active_dataset_id=args.active_dataset_id,
            source_catalog_version=args.source_catalog_version,
            rebuild_run_id=args.rebuild_run_id,
            reason="manual_join_refresh",
            dry_run=args.dry_run,
        ),
        store=PostgresRuntimeStore(),
    )
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
