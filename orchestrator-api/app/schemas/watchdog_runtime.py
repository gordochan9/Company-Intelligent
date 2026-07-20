from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from app.schemas.watchdog_sync import WatchdogEvent


@dataclass
class WatchdogRuntimeReport:
    status: str
    dataset_root_label: str = "active_dataset"
    queued_events: int = 0
    processed_events: int = 0
    validation_errors: list[dict[str, str]] = field(default_factory=list)
    sync_report: dict[str, Any] | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "dataset_root_label": self.dataset_root_label,
            "queued_events": self.queued_events,
            "processed_events": self.processed_events,
            "validation_errors": self.validation_errors,
            "sync_report": self.sync_report,
        }


@dataclass
class WatchdogQueueItem:
    event: WatchdogEvent
    path: Path | None = None
    source_path: Path | None = None
