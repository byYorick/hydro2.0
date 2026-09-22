"""Интервал опроса воркера AE4.

Берётся та же переменная ``AE_RECONCILE_POLL_INTERVAL_SEC``, что и у процесса.
Своего интервала нет.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Ae4RuntimeConfig:
    reconcile_poll_interval_sec: float

    @classmethod
    def from_env(cls) -> "Ae4RuntimeConfig":
        raw = os.getenv("AE_RECONCILE_POLL_INTERVAL_SEC", "0.5")
        return cls(reconcile_poll_interval_sec=max(0.1, float(raw)))


__all__ = ["Ae4RuntimeConfig"]
