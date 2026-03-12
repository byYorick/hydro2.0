"""Runtime configuration for standalone AE3-Lite app."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_true(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Ae3RuntimeConfig:
    app_env: str
    host: str
    port: int
    db_dsn: str
    history_logger_url: str
    history_logger_api_token: str
    scheduler_api_token: str
    scheduler_security_baseline_enforce: bool
    scheduler_require_trace_id: bool
    lease_ttl_sec: int
    reconcile_poll_interval_sec: float
    start_cycle_claim_stale_sec: int
    start_cycle_running_stale_sec: int
    start_cycle_rate_limit_enabled: bool
    start_cycle_rate_limit_max_requests: int
    start_cycle_rate_limit_window_sec: int
    verbose_http_logging: bool
    worker_owner: str

    @classmethod
    def from_env(cls) -> "Ae3RuntimeConfig":
        app_env = str(os.getenv("APP_ENV", "local")).strip().lower() or "local"
        default_verbose = "1" if app_env in {"local", "dev", "development"} else "0"
        return cls(
            app_env=app_env,
            host=str(os.getenv("AE_HOST", "0.0.0.0")).strip() or "0.0.0.0",
            port=max(1, int(os.getenv("AUTOMATION_ENGINE_API_PORT", "9405"))),
            db_dsn=str(os.getenv("AE_DB_DSN") or os.getenv("DATABASE_URL") or "").strip(),
            history_logger_url=(
                str(os.getenv("AE_HISTORY_LOGGER_URL") or os.getenv("HISTORY_LOGGER_URL") or "http://history-logger:9300")
                .strip()
                .rstrip("/")
            ),
            history_logger_api_token=str(
                os.getenv("HISTORY_LOGGER_API_TOKEN")
                or os.getenv("AE_API_TOKEN")
                or os.getenv("PY_INGEST_TOKEN")
                or os.getenv("PY_API_TOKEN")
                or ""
            ).strip(),
            scheduler_api_token=str(
                os.getenv("AE_API_TOKEN")
                or os.getenv("SCHEDULER_API_TOKEN")
                or os.getenv("PY_INGEST_TOKEN")
                or os.getenv("PY_API_TOKEN")
                or ""
            ).strip(),
            scheduler_security_baseline_enforce=_env_true("AE_SCHEDULER_SECURITY_BASELINE_ENFORCE", "1"),
            scheduler_require_trace_id=_env_true("AE_SCHEDULER_REQUIRE_TRACE_ID", "1"),
            lease_ttl_sec=max(30, min(3600, int(os.getenv("AE_LEASE_TTL_SEC", "300")))),
            reconcile_poll_interval_sec=max(0.1, float(os.getenv("AE_RECONCILE_POLL_INTERVAL_SEC", "0.5"))),
            start_cycle_claim_stale_sec=max(30, int(os.getenv("AE_START_CYCLE_CLAIM_STALE_SEC", "180"))),
            start_cycle_running_stale_sec=max(
                300,
                int(
                    os.getenv(
                        "AE_START_CYCLE_RUNNING_STALE_SEC",
                        os.getenv("AE_START_CYCLE_ORPHAN_PHASE_AUTO_HEAL_SEC", "1800"),
                    )
                ),
            ),
            start_cycle_rate_limit_enabled=_env_true("AE_START_CYCLE_RATE_LIMIT_ENABLED", "1"),
            start_cycle_rate_limit_max_requests=max(0, int(os.getenv("AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS", "30"))),
            start_cycle_rate_limit_window_sec=max(1, int(os.getenv("AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC", "10"))),
            verbose_http_logging=_env_true("AE_DEV_VERBOSE_HTTP_LOGGING", default_verbose),
            worker_owner=str(os.getenv("AE_WORKER_OWNER", "ae3-runtime-worker")).strip() or "ae3-runtime-worker",
        )

    def validate(self) -> None:
        """Raise ValueError if required config is missing."""
        if not self.history_logger_api_token:
            raise ValueError(
                "history_logger_api_token is required. "
                "Set HISTORY_LOGGER_API_TOKEN (or AE_API_TOKEN / PY_API_TOKEN)."
            )


__all__ = ["Ae3RuntimeConfig"]
