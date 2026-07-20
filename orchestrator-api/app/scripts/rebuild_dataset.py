from __future__ import annotations

import argparse
import json
import os
import sys

from app.schemas.join_discovery import JoinDiscoveryRefreshRequest
from app.db.runtime_store import PostgresRuntimeStore
from app.services.join_discovery_approved_joins import run_approved_join_discovery_refresh
from app.services.source_catalog_dataset_rebuild import run_rebuild


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rebuild Project 3.0 active dataset.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--dataset-root")
    parser.add_argument("--skip-join-refresh", action="store_true")
    args = parser.parse_args(argv)

    store = None if args.dry_run or not os.getenv("DATABASE_URL") else PostgresRuntimeStore()
    if store is None:
        report = run_rebuild(args.dataset_root, dry_run=args.dry_run)
    else:
        report = run_rebuild(args.dataset_root, dry_run=args.dry_run, store=store)
    output = report.as_dict()
    if report.exit_code == 0 and report.join_refresh_required and not args.dry_run and not args.skip_join_refresh:
        request = JoinDiscoveryRefreshRequest(
            active_dataset_id=report.active_dataset_id,
            source_catalog_version=report.source_catalog_version,
            reason="rebuild_dataset_bat",
        )
        join_report = run_approved_join_discovery_refresh(request, store=store) if store else run_approved_join_discovery_refresh(request)
        output["join_discovery_report"] = join_report.as_dict()
    print(json.dumps(output, indent=2, sort_keys=True))
    return report.exit_code


if __name__ == "__main__":
    sys.exit(main())
