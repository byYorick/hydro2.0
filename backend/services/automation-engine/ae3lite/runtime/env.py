"""Environment-backed runtime settings for standalone AE3-Lite."""

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
    http_client_timeout_sec: float
    http_client_connect_timeout_sec: float
    http_client_read_timeout_sec: float
    http_client_write_timeout_sec: float
    http_client_pool_timeout_sec: float
    hl_max_retries: int
    hl_retry_backoff_sec: float
    hl_breaker_fail_threshold: int
    hl_breaker_open_sec: float
    worker_owner: str
    max_task_execution_sec: int
    max_parallel_tasks: int
    waiting_command_reconcile_batch_limit: int
    stale_claimed_ttl_sec: int
    stale_running_ttl_sec: int
    waiting_command_stale_ttl_sec: int
    unconfirmed_command_stale_ttl_sec: int
    foreign_lease_skip_escalate_sec: int
    stale_task_reconcile_sec: float
    orphan_intent_reconcile_sec: float
    orphan_intent_reconcile_batch_limit: int
    shutdown_grace_sec: float
    command_poll_default_sec: float
    command_poll_margin_sec: float
    lease_heartbeat_max_failures: int
    lease_heartbeat_transient_retries: int
    intent_sync_max_retries: int
    correction_interrupt_verify_grace_sec: int
    correction_interrupt_irr_state_max_age_sec: int
    correction_interrupt_replay_irrigation: bool

    @classmethod
    def from_env(cls) -> "Ae3RuntimeConfig":
        app_env = str(os.getenv("APP_ENV", "local")).strip().lower() or "local"
        default_verbose = "1" if app_env in {"local", "dev", "development"} else "0"
        lease_ttl_sec = max(30, min(3600, int(os.getenv("AE_LEASE_TTL_SEC", "300"))))
        stale_claimed_ttl_sec = max(1, int(os.getenv("AE_STALE_CLAIMED_TTL_SEC", "120")))
        foreign_lease_escalate_raw = os.getenv("AE_FOREIGN_LEASE_SKIP_ESCALATE_SEC")
        if foreign_lease_escalate_raw is not None and str(foreign_lease_escalate_raw).strip() != "":
            foreign_lease_skip_escalate_sec = max(1, int(foreign_lease_escalate_raw))
        else:
            foreign_lease_skip_escalate_sec = max(lease_ttl_sec * 2, stale_claimed_ttl_sec, 240)
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
            lease_ttl_sec=lease_ttl_sec,
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
            http_client_timeout_sec=max(0.1, float(os.getenv("AE_HTTP_CLIENT_TIMEOUT_SEC", "10.0"))),
            http_client_connect_timeout_sec=cls._http_timeout_component(
                "AE_HTTP_CLIENT_CONNECT_TIMEOUT_SEC",
                legacy_default="10.0",
                granular_default="2.0",
            ),
            http_client_read_timeout_sec=cls._http_timeout_component(
                "AE_HTTP_CLIENT_READ_TIMEOUT_SEC",
                legacy_default="10.0",
                granular_default="8.0",
            ),
            http_client_write_timeout_sec=cls._http_timeout_component(
                "AE_HTTP_CLIENT_WRITE_TIMEOUT_SEC",
                legacy_default="10.0",
                granular_default="5.0",
            ),
            http_client_pool_timeout_sec=cls._http_timeout_component(
                "AE_HTTP_CLIENT_POOL_TIMEOUT_SEC",
                legacy_default="10.0",
                granular_default="2.0",
            ),
            hl_max_retries=max(0, int(os.getenv("AE_HL_MAX_RETRIES", "1"))),
            hl_retry_backoff_sec=max(0.0, float(os.getenv("AE_HL_RETRY_BACKOFF_SEC", "0.5"))),
            hl_breaker_fail_threshold=max(1, int(os.getenv("AE_HL_BREAKER_FAIL_THRESHOLD", "5"))),
            hl_breaker_open_sec=max(0.1, float(os.getenv("AE_HL_BREAKER_OPEN_SEC", "15"))),
            worker_owner=str(os.getenv("AE_WORKER_OWNER", "ae3-runtime-worker")).strip() or "ae3-runtime-worker",
            max_task_execution_sec=max(60, int(os.getenv("AE_MAX_TASK_EXECUTION_SEC", "900"))),
            max_parallel_tasks=max(1, int(os.getenv("AE_MAX_PARALLEL_TASKS", "4"))),
            waiting_command_reconcile_batch_limit=max(
                1,
                min(200, int(os.getenv("AE_WAITING_COMMAND_RECONCILE_BATCH_LIMIT", "32"))),
            ),
            stale_claimed_ttl_sec=stale_claimed_ttl_sec,
            stale_running_ttl_sec=max(
                1,
                int(
                    os.getenv(
                        "AE_STALE_RUNNING_TTL_SEC",
                        str(max(60, int(os.getenv("AE_MAX_TASK_EXECUTION_SEC", "900"))) + 60),
                    )
                ),
            ),
            waiting_command_stale_ttl_sec=max(
                1,
                int(
                    os.getenv(
                        "AE_WAITING_COMMAND_STALE_TTL_SEC",
                        str(
                            int(
                                max(
                                    1.0,
                                    float(os.getenv("AE_COMMAND_POLL_DEFAULT_SEC", "120"))
                                    + float(os.getenv("AE_COMMAND_POLL_MARGIN_SEC", "30"))
                                    + 60.0,
                                )
                            )
                        ),
                    )
                ),
            ),
            unconfirmed_command_stale_ttl_sec=max(
                1,
                int(os.getenv("AE_UNCONFIRMED_COMMAND_STALE_TTL_SEC", "120")),
            ),
            foreign_lease_skip_escalate_sec=foreign_lease_skip_escalate_sec,
            stale_task_reconcile_sec=max(1.0, float(os.getenv("AE_STALE_TASK_RECONCILE_SEC", "60"))),
            orphan_intent_reconcile_sec=max(
                1.0,
                float(os.getenv("AE_ORPHAN_INTENT_RECONCILE_SEC", os.getenv("AE_STALE_TASK_RECONCILE_SEC", "60"))),
            ),
            orphan_intent_reconcile_batch_limit=max(
                1,
                min(32, int(os.getenv("AE_ORPHAN_INTENT_RECONCILE_BATCH_LIMIT", "16"))),
            ),
            shutdown_grace_sec=max(0.0, float(os.getenv("AE_SHUTDOWN_GRACE_SEC", "30"))),
            command_poll_default_sec=max(1.0, float(os.getenv("AE_COMMAND_POLL_DEFAULT_SEC", "120"))),
            command_poll_margin_sec=max(0.0, float(os.getenv("AE_COMMAND_POLL_MARGIN_SEC", "30"))),
            lease_heartbeat_max_failures=max(1, int(os.getenv("AE_LEASE_HEARTBEAT_MAX_FAILURES", "3"))),
            lease_heartbeat_transient_retries=max(0, int(os.getenv("AE_LEASE_HEARTBEAT_TRANSIENT_RETRIES", "1"))),
            intent_sync_max_retries=max(0, int(os.getenv("AE_INTENT_SYNC_MAX_RETRIES", "2"))),
            correction_interrupt_verify_grace_sec=max(
                15,
                int(os.getenv("AE_CORRECTION_INTERRUPT_VERIFY_GRACE_SEC", "120")),
            ),
            correction_interrupt_irr_state_max_age_sec=max(
                5,
                int(os.getenv("AE_CORRECTION_INTERRUPT_IRR_STATE_MAX_AGE_SEC", "90")),
            ),
            # Prod-safe default: auto-replay irrigation после interrupt выключен.
            # Включить явно: AE_CORRECTION_INTERRUPT_REPLAY_IRRIGATION=1.
            correction_interrupt_replay_irrigation=_env_true(
                "AE_CORRECTION_INTERRUPT_REPLAY_IRRIGATION",
                "0",
            ),
        )

    @staticmethod
    def _http_timeout_component(name: str, *, legacy_default: str, granular_default: str) -> float:
        explicit = os.getenv(name)
        if explicit is not None and str(explicit).strip() != "":
            return max(0.1, float(explicit))
        legacy = os.getenv("AE_HTTP_CLIENT_TIMEOUT_SEC")
        if legacy is not None and str(legacy).strip() != "":
            return max(0.1, float(legacy))
        return max(0.1, float(granular_default))

    def validate(self) -> None:
        """Выбрасывает ValueError, если отсутствует обязательная конфигурация."""
        if not str(self.db_dsn or "").strip():
            raise ValueError(
                "AE_DB_DSN / DATABASE_URL не задан. "
                "Set AE_DB_DSN or DATABASE_URL to a PostgreSQL connection string."
            )
        history_logger_api_token = str(self.history_logger_api_token or "").strip()
        scheduler_api_token = str(self.scheduler_api_token or "").strip()
        if not history_logger_api_token:
            raise ValueError(
                "Обязателен history_logger_api_token. "
                "Set HISTORY_LOGGER_API_TOKEN (or AE_API_TOKEN / PY_API_TOKEN)."
            )
        if self.scheduler_security_baseline_enforce and not scheduler_api_token:
            raise ValueError(
                "При включённом scheduler security baseline обязателен scheduler_api_token. "
                "Set AE_API_TOKEN (or SCHEDULER_API_TOKEN / PY_API_TOKEN)."
            )
        # Fail-closed: отключение security baseline допустимо только в non-production средах,
        # чтобы enforce=0 не мог случайно уехать в staging/production.
        non_production_envs = {"local", "dev", "development", "test", "testing"}
        if not self.scheduler_security_baseline_enforce and self.app_env not in non_production_envs:
            raise ValueError(
                "AE_SCHEDULER_SECURITY_BASELINE_ENFORCE=0 разрешён только при "
                "APP_ENV=local|dev|development|test|testing "
                f"(текущий APP_ENV={self.app_env!r}). Включите security baseline или смените APP_ENV."
            )
        if self.start_cycle_rate_limit_enabled:
            if int(self.start_cycle_rate_limit_max_requests) <= 0:
                raise ValueError(
                    "start_cycle_rate_limit_max_requests must be > 0 when rate limiting is enabled. "
                    "Set AE_START_CYCLE_RATE_LIMIT_MAX_REQUESTS to a positive integer."
                )
            if int(self.start_cycle_rate_limit_window_sec) <= 0:
                raise ValueError(
                    "start_cycle_rate_limit_window_sec must be > 0 when rate limiting is enabled. "
                    "Set AE_START_CYCLE_RATE_LIMIT_WINDOW_SEC to a positive integer."
                )
        if float(self.http_client_timeout_sec) <= 0.0:
            raise ValueError(
                "http_client_timeout_sec must be > 0. "
                "Set AE_HTTP_CLIENT_TIMEOUT_SEC to a positive number."
            )
        for field_name, value in (
            ("http_client_connect_timeout_sec", self.http_client_connect_timeout_sec),
            ("http_client_read_timeout_sec", self.http_client_read_timeout_sec),
            ("http_client_write_timeout_sec", self.http_client_write_timeout_sec),
            ("http_client_pool_timeout_sec", self.http_client_pool_timeout_sec),
        ):
            if float(value) <= 0.0:
                raise ValueError(f"{field_name} must be > 0.")
        if int(self.hl_max_retries) < 0:
            raise ValueError("hl_max_retries must be >= 0. Set AE_HL_MAX_RETRIES to a non-negative integer.")
        if int(self.hl_max_retries) > 1:
            raise ValueError(
                "hl_max_retries must be <= 1. AE3 allows at most one transient retry to history-logger. "
                "Set AE_HL_MAX_RETRIES to 0 or 1."
            )
        if float(self.hl_retry_backoff_sec) < 0.0:
            raise ValueError("hl_retry_backoff_sec must be >= 0. Set AE_HL_RETRY_BACKOFF_SEC to a non-negative number.")
        if int(self.hl_breaker_fail_threshold) <= 0:
            raise ValueError(
                "hl_breaker_fail_threshold must be > 0. Set AE_HL_BREAKER_FAIL_THRESHOLD to a positive integer."
            )
        if float(self.hl_breaker_open_sec) <= 0.0:
            raise ValueError("hl_breaker_open_sec must be > 0. Set AE_HL_BREAKER_OPEN_SEC to a positive number.")
        if int(self.stale_claimed_ttl_sec) <= 0:
            raise ValueError(
                "stale_claimed_ttl_sec must be > 0. Set AE_STALE_CLAIMED_TTL_SEC to a positive integer."
            )
        if int(self.stale_running_ttl_sec) <= 0:
            raise ValueError(
                "stale_running_ttl_sec must be > 0. Set AE_STALE_RUNNING_TTL_SEC to a positive integer."
            )
        if int(self.waiting_command_stale_ttl_sec) <= 0:
            raise ValueError(
                "waiting_command_stale_ttl_sec must be > 0. "
                "Set AE_WAITING_COMMAND_STALE_TTL_SEC to a positive integer."
            )
        if int(self.unconfirmed_command_stale_ttl_sec) <= 0:
            raise ValueError(
                "unconfirmed_command_stale_ttl_sec must be > 0. "
                "Set AE_UNCONFIRMED_COMMAND_STALE_TTL_SEC to a positive integer."
            )
        if int(self.foreign_lease_skip_escalate_sec) <= 0:
            raise ValueError(
                "foreign_lease_skip_escalate_sec must be > 0. "
                "Set AE_FOREIGN_LEASE_SKIP_ESCALATE_SEC to a positive integer."
            )
        if int(self.stale_running_ttl_sec) <= int(self.max_task_execution_sec):
            raise ValueError(
                "stale_running_ttl_sec must be > max_task_execution_sec "
                f"(got stale_running_ttl_sec={self.stale_running_ttl_sec}, "
                f"max_task_execution_sec={self.max_task_execution_sec})."
            )
        if float(self.stale_task_reconcile_sec) <= 0.0:
            raise ValueError(
                "stale_task_reconcile_sec must be > 0. Set AE_STALE_TASK_RECONCILE_SEC to a positive number."
            )
        if float(self.orphan_intent_reconcile_sec) <= 0.0:
            raise ValueError(
                "orphan_intent_reconcile_sec must be > 0. Set AE_ORPHAN_INTENT_RECONCILE_SEC to a positive number."
            )
        if int(self.orphan_intent_reconcile_batch_limit) <= 0:
            raise ValueError(
                "orphan_intent_reconcile_batch_limit must be > 0. "
                "Set AE_ORPHAN_INTENT_RECONCILE_BATCH_LIMIT to a positive integer."
            )
        if float(self.command_poll_default_sec) <= 0.0:
            raise ValueError(
                "command_poll_default_sec must be > 0. Set AE_COMMAND_POLL_DEFAULT_SEC to a positive number."
            )
        if float(self.command_poll_margin_sec) < 0.0:
            raise ValueError(
                "command_poll_margin_sec must be >= 0. Set AE_COMMAND_POLL_MARGIN_SEC to a non-negative number."
            )


__all__ = ["Ae3RuntimeConfig"]
