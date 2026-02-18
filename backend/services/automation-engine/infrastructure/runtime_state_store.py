"""File-backed runtime-state snapshot store for AE crash-recovery."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, Optional


logger = logging.getLogger(__name__)
SNAPSHOT_SCHEMA_VERSION = 1


class RuntimeStateStore:
    """Persists/restores runtime state snapshot in a local JSON file."""

    def __init__(self, snapshot_path: str):
        self.snapshot_path = Path(str(snapshot_path).strip())

    def load(self) -> Optional[Dict[str, Any]]:
        try:
            if not self.snapshot_path.exists():
                return None
            raw = json.loads(self.snapshot_path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                return None
            return raw
        except Exception:
            logger.warning(
                "Failed to load runtime snapshot from %s",
                self.snapshot_path,
                exc_info=True,
            )
            return None

    def save(self, payload: Dict[str, Any]) -> bool:
        try:
            self.snapshot_path.parent.mkdir(parents=True, exist_ok=True)
            data = dict(payload or {})
            data.setdefault("schema_version", SNAPSHOT_SCHEMA_VERSION)
            tmp_path = self.snapshot_path.with_suffix(f"{self.snapshot_path.suffix}.tmp")
            tmp_path.write_text(
                json.dumps(data, ensure_ascii=True, separators=(",", ":")),
                encoding="utf-8",
            )
            tmp_path.replace(self.snapshot_path)
            return True
        except Exception:
            logger.warning(
                "Failed to save runtime snapshot to %s",
                self.snapshot_path,
                exc_info=True,
            )
            return False


__all__ = ["RuntimeStateStore", "SNAPSHOT_SCHEMA_VERSION"]
