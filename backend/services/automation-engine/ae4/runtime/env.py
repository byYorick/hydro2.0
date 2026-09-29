"""Конфиг процесса automation-engine 1.0.0."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _env_true(name: str, default: str = "0") -> bool:
    return str(os.getenv(name, default)).strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Ae4RuntimeConfig:
    app_env: str
    host: str
    port: int
    db_dsn: str
    history_logger_url: str
    scheduler_api_token: str
    scheduler_security_baseline_enforce: bool
    scheduler_require_trace_id: bool
    reconcile_poll_interval_sec: float
    stale_task_max_age_sec: float
    rate_limit_enabled: bool
    rate_limit_max_requests: int
    rate_limit_window_sec: int
    verbose_http_logging: bool
    service_version: str = "1.0.0"

    @classmethod
    def from_env(cls) -> "Ae4RuntimeConfig":
        app_env = str(os.getenv("APP_ENV", "local")).strip().lower() or "local"
        default_verbose = "1" if app_env in {"local", "dev", "development"} else "0"
        return cls(
            app_env=app_env,
            host=str(os.getenv("AE_HOST", "0.0.0.0")).strip() or "0.0.0.0",
            port=max(1, int(os.getenv("AUTOMATION_ENGINE_API_PORT", "9405"))),
            db_dsn=str(os.getenv("AE_DB_DSN") or os.getenv("DATABASE_URL") or "").strip(),
            history_logger_url=(
                str(
                    os.getenv("AE_HISTORY_LOGGER_URL")
                    or os.getenv("HISTORY_LOGGER_URL")
                    or "http://history-logger:9300"
                )
                .strip()
                .rstrip("/")
            ),
            scheduler_api_token=str(
                os.getenv("AE_API_TOKEN")
                or os.getenv("SCHEDULER_API_TOKEN")
                or os.getenv("PY_INGEST_TOKEN")
                or os.getenv("PY_API_TOKEN")
                or ""
            ).strip(),
            scheduler_security_baseline_enforce=_env_true(
                "AE_SCHEDULER_SECURITY_BASELINE_ENFORCE", "1"
            ),
            scheduler_require_trace_id=_env_true("AE_SCHEDULER_REQUIRE_TRACE_ID", "1"),
            reconcile_poll_interval_sec=max(
                0.1, float(os.getenv("AE_RECONCILE_POLL_INTERVAL_SEC", "0.5"))
            ),
            stale_task_max_age_sec=max(
                30.0, float(os.getenv("AE4_STALE_TASK_MAX_AGE_SEC", "900"))
            ),
            rate_limit_enabled=_env_true("AE_START_CYCLE_RATE_LIMIT_ENABLED", "1"),
            rate_limit_max_requests=max(
                0, int(os.getenv("AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS", "30"))
            ),
            rate_limit_window_sec=max(
                1, int(os.getenv("AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC", "10"))
            ),
            verbose_http_logging=_env_true("AE_DEV_VERBOSE_HTTP_LOGGING", default_verbose),
            service_version="1.0.0",
        )

    def validate(self) -> None:
        if not str(self.db_dsn or "").strip():
            raise ValueError("AE_DB_DSN / DATABASE_URL не задан")
        if self.scheduler_security_baseline_enforce and not self.scheduler_api_token:
            raise ValueError("При security baseline обязателен scheduler_api_token")
        non_prod = {"local", "dev", "development", "test", "testing"}
        if not self.scheduler_security_baseline_enforce and self.app_env not in non_prod:
            raise ValueError(
                "AE_SCHEDULER_SECURITY_BASELINE_ENFORCE=0 только в non-production"
            )


__all__ = ["Ae4RuntimeConfig"]
