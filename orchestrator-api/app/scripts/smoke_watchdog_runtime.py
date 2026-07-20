from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.services.watchdog_runtime import normalize_watchdog_event


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke test Project 3.0 watchdog runtime contracts.")
    parser.add_argument("--dataset-root", required=True)
    args = parser.parse_args(argv)

    root = Path(args.dataset_root)
    if not root.exists() or not root.is_dir():
        print(json.dumps({"status": "failed", "validation_errors": [{"code": "active_dataset_root_missing"}]}, indent=2, sort_keys=True))
        return 1
    sample = root / "Finance" / "watchdog_smoke.txt"
    sample.parent.mkdir(exist_ok=True)
    item = normalize_watchdog_event(root, "created", sample)
    print(
        json.dumps(
            {
                "status": "ok",
                "dataset_root_label": "active_dataset",
                "event": {
                    "event_type": item.event.event_type,
                    "relative_path": item.event.relative_path,
                    "permission_scope_key": item.event.permission_scope_key,
                    "file_kind": item.event.file_kind,
                },
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
