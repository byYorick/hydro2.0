"""Tests for command audit safeguards."""
import pytest
from unittest.mock import AsyncMock, patch

from infrastructure.command_audit import CommandAudit


@pytest.mark.asyncio
async def test_audit_command_writes_when_zone_exists():
    """Audit record should be inserted when zone exists."""
    audit = CommandAudit()

    with patch("infrastructure.command_audit.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("infrastructure.command_audit.execute", new_callable=AsyncMock) as mock_execute:
        mock_fetch.return_value = [{"?column?": 1}]

        await audit.audit_command(
            327,
            {"cmd": "run_pump", "params": {"duration_ms": 1000}},
            {"current_value": 5.8, "target_value": 6.0, "trace_id": "t-1"},
        )

        mock_execute.assert_called_once()
        assert mock_execute.call_args[0][1] == 327


@pytest.mark.asyncio
async def test_audit_command_skips_when_zone_missing_and_logs_once():
    """Missing zone must skip insert and avoid repetitive warning spam."""
    audit = CommandAudit()

    with patch("infrastructure.command_audit.fetch", new_callable=AsyncMock) as mock_fetch, \
         patch("infrastructure.command_audit.execute", new_callable=AsyncMock) as mock_execute, \
         patch("infrastructure.command_audit.logger.warning") as mock_warning:
        mock_fetch.return_value = []

        await audit.audit_command(1, {"cmd": "run_pump"}, None)
        await audit.audit_command(1, {"cmd": "run_pump"}, None)

        mock_execute.assert_not_called()
        mock_warning.assert_called_once()
