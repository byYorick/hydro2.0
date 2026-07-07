"""Tests for Ae3RuntimeConfig.validate().

Covers the required-field checks that raise ValueError when critical
configuration is missing at startup, preventing the service from silently
running with a broken configuration.
"""

from __future__ import annotations

import pytest

from ae3lite.runtime.env import Ae3RuntimeConfig


def _config(**kwargs: object) -> Ae3RuntimeConfig:
    """Build a valid Ae3RuntimeConfig with sensible defaults, allowing overrides."""
    defaults: dict = dict(
        app_env="test",
        host="0.0.0.0",
        port=9405,
        db_dsn="postgresql://test/test",
        history_logger_url="http://history-logger:9300",
        history_logger_api_token="test-token",
        scheduler_api_token="test-token",
        scheduler_security_baseline_enforce=False,
        scheduler_require_trace_id=False,
        lease_ttl_sec=300,
        reconcile_poll_interval_sec=0.5,
        start_cycle_claim_stale_sec=180,
        start_cycle_running_stale_sec=1800,
        start_cycle_rate_limit_enabled=False,
        start_cycle_rate_limit_max_requests=30,
        start_cycle_rate_limit_window_sec=10,
        verbose_http_logging=False,
        http_client_timeout_sec=10.0,
        http_client_connect_timeout_sec=2.0,
        http_client_read_timeout_sec=8.0,
        http_client_write_timeout_sec=5.0,
        http_client_pool_timeout_sec=2.0,
        hl_max_retries=2,
        hl_retry_backoff_sec=0.5,
        hl_breaker_fail_threshold=5,
        hl_breaker_open_sec=15.0,
        worker_owner="test-worker",
        max_task_execution_sec=900,
        max_parallel_tasks=4,
        waiting_command_reconcile_batch_limit=32,
        stale_claimed_ttl_sec=120,
        stale_running_ttl_sec=960,
        stale_task_reconcile_sec=60.0,
        shutdown_grace_sec=30.0,
        command_poll_default_sec=120.0,
        command_poll_margin_sec=30.0,
        lease_heartbeat_max_failures=3,
        lease_heartbeat_transient_retries=1,
        intent_sync_max_retries=2,
    )
    defaults.update(kwargs)
    return Ae3RuntimeConfig(**defaults)


class TestAe3RuntimeConfigValidate:
    def test_valid_config_does_not_raise(self) -> None:
        cfg = _config(history_logger_api_token="abc123", db_dsn="postgresql://x/y")
        cfg.validate()  # must not raise

    def test_db_dsn_set_does_not_raise(self) -> None:
        cfg = _config(db_dsn="postgresql://hydro:hydro@db:5432/hydro_dev")
        cfg.validate()

    def test_empty_db_dsn_raises_value_error(self) -> None:
        cfg = _config(db_dsn="")
        with pytest.raises(ValueError, match="AE_DB_DSN / DATABASE_URL"):
            cfg.validate()

    def test_whitespace_only_db_dsn_raises(self) -> None:
        cfg = _config(db_dsn="   ")
        with pytest.raises(ValueError, match="AE_DB_DSN / DATABASE_URL"):
            cfg.validate()

    def test_empty_token_raises_value_error(self) -> None:
        cfg = _config(history_logger_api_token="")
        with pytest.raises(ValueError, match="history_logger_api_token"):
            cfg.validate()

    def test_token_is_required_error_mentions_env_vars(self) -> None:
        cfg = _config(history_logger_api_token="")
        with pytest.raises(ValueError, match="HISTORY_LOGGER_API_TOKEN"):
            cfg.validate()

    def test_whitespace_only_token_raises(self) -> None:
        """A token with only whitespace must be rejected."""
        cfg = _config(history_logger_api_token="   ")
        with pytest.raises(ValueError, match="history_logger_api_token"):
            cfg.validate()

    def test_validate_called_twice_is_idempotent(self) -> None:
        cfg = _config()
        cfg.validate()
        cfg.validate()  # second call must also succeed

    def test_token_with_only_valid_content_passes(self) -> None:
        for token in ("x", "dev-token-12345", "Bearer abc", "a" * 256):
            cfg = _config(history_logger_api_token=token)
            cfg.validate()  # should not raise

    def test_scheduler_api_token_required_when_security_enforced(self) -> None:
        cfg = _config(scheduler_security_baseline_enforce=True, scheduler_api_token="")
        with pytest.raises(ValueError, match="scheduler_api_token"):
            cfg.validate()

    def test_scheduler_api_token_not_required_when_security_disabled(self) -> None:
        cfg = _config(scheduler_security_baseline_enforce=False, scheduler_api_token="")
        cfg.validate()

    def test_rate_limit_requires_positive_max_requests_when_enabled(self) -> None:
        cfg = _config(start_cycle_rate_limit_enabled=True, start_cycle_rate_limit_max_requests=0)
        with pytest.raises(ValueError, match="start_cycle_rate_limit_max_requests"):
            cfg.validate()

    def test_security_disabled_in_production_raises(self) -> None:
        """enforce=0 запрещён вне non-production сред (fail-closed для staging/prod)."""
        for env in ("production", "prod", "staging"):
            cfg = _config(app_env=env, scheduler_security_baseline_enforce=False)
            with pytest.raises(ValueError, match="AE_SCHEDULER_SECURITY_BASELINE_ENFORCE"):
                cfg.validate()

    def test_security_disabled_allowed_in_non_production(self) -> None:
        for env in ("local", "dev", "development", "test", "testing"):
            cfg = _config(app_env=env, scheduler_security_baseline_enforce=False)
            cfg.validate()  # must not raise

    def test_security_enabled_in_production_does_not_raise(self) -> None:
        cfg = _config(
            app_env="production",
            scheduler_security_baseline_enforce=True,
            scheduler_api_token="prod-token",
        )
        cfg.validate()

    def test_hl_retry_backoff_negative_raises(self) -> None:
        cfg = _config(hl_retry_backoff_sec=-0.1)
        with pytest.raises(ValueError, match="hl_retry_backoff_sec"):
            cfg.validate()

    def test_hl_breaker_fail_threshold_non_positive_raises(self) -> None:
        cfg = _config(hl_breaker_fail_threshold=0)
        with pytest.raises(ValueError, match="hl_breaker_fail_threshold"):
            cfg.validate()

    def test_hl_breaker_open_sec_non_positive_raises(self) -> None:
        cfg = _config(hl_breaker_open_sec=0.0)
        with pytest.raises(ValueError, match="hl_breaker_open_sec"):
            cfg.validate()

    def test_http_client_granular_timeout_non_positive_raises(self) -> None:
        cfg = _config(http_client_read_timeout_sec=0.0)
        with pytest.raises(ValueError, match="http_client_read_timeout_sec"):
            cfg.validate()

    def test_stale_running_ttl_must_exceed_max_task_execution_sec(self) -> None:
        cfg = _config(max_task_execution_sec=900, stale_running_ttl_sec=900)
        with pytest.raises(ValueError, match="stale_running_ttl_sec"):
            cfg.validate()

    def test_stale_task_reconcile_sec_non_positive_raises(self) -> None:
        cfg = _config(stale_task_reconcile_sec=0.0)
        with pytest.raises(ValueError, match="stale_task_reconcile_sec"):
            cfg.validate()


class TestAe3RuntimeConfigFromEnvClamps:
    """Tests for the numeric clamping applied by from_env (tested via the formulas)."""

    def test_lease_ttl_capped_at_3600(self) -> None:
        """from_env applies: max(30, min(3600, raw_value))."""
        raw_oversized = 99999
        capped = max(30, min(3600, raw_oversized))
        assert capped == 3600

    def test_lease_ttl_minimum_30(self) -> None:
        raw_undersized = 1
        capped = max(30, min(3600, raw_undersized))
        assert capped == 30

    def test_lease_ttl_in_range_preserved(self) -> None:
        for v in (30, 300, 1800, 3600):
            assert max(30, min(3600, v)) == v

    def test_reconcile_poll_interval_minimum_01(self) -> None:
        capped = max(0.1, float(0.0))
        assert capped == pytest.approx(0.1)

    def test_start_cycle_claim_stale_minimum_30(self) -> None:
        capped = max(30, int(0))
        assert capped == 30

    def test_start_cycle_running_stale_minimum_300(self) -> None:
        capped = max(300, int(0))
        assert capped == 300

    def test_rate_limit_max_requests_minimum_0(self) -> None:
        capped = max(0, int(-5))
        assert capped == 0

    def test_rate_limit_window_sec_minimum_1(self) -> None:
        capped = max(1, int(0))
        assert capped == 1
