from __future__ import annotations

import argparse
import json
import sys

from app.db.runtime_store import PostgresRuntimeStore
from app.services.watchdog_runtime import run_watchdog_once


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Project 3.0 active dataset watchdog.")
    parser.add_argument("--dataset-root")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    report = run_watchdog_once(args.dataset_root, dry_run=args.dry_run, store=None if args.dry_run else PostgresRuntimeStore())
    print(json.dumps(report.as_dict(), indent=2, sort_keys=True))
    return 0 if report.status in {"ok", "dry_run_ok", "skipped"} else 1


if __name__ == "__main__":
    sys.exit(main())
