"""Config mode enum (Phase 5).

A zone's `config_mode` controls whether AE3 honours mid-cycle config edits:

- **LOCKED** (default): AE3 uses the cycle snapshot throughout. Edits made
  via API after cycle start take effect only on the next cycle.
- **LIVE**: AE3 re-reads the current bundle at defined checkpoints. Edits
  take effect within one checkpoint of the save. TTL-bounded — Laravel cron
  auto-reverts to LOCKED when `live_until` expires.

Canonical source: `zones.config_mode` column (Laravel migration
`2026_04_15_142400_add_config_mode_to_zones.php`).
"""

from __future__ import annotations

from enum import Enum


class ConfigMode(str, Enum):
    LOCKED = "locked"
    LIVE = "live"

    @classmethod
    def parse(cls, value: object) -> "ConfigMode":
        """Normalize DB string → ConfigMode. Unknown values fall back to LOCKED
        (fail-safe: legacy zones without the column, typos in edge data)."""
        if isinstance(value, cls):
            return value
        text = str(value or "").strip().lower()
        if text == cls.LIVE.value:
            return cls.LIVE
        return cls.LOCKED
