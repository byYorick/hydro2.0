"""Tests for error_handler module."""
import pytest
from unittest.mock import Mock, patch, call
from exceptions import (
    AutomationError,
    ZoneNotFoundError,
    InvalidConfigurationError,
    TelemetryError,
)
from error_handler import (
    handle_zone_error,
    handle_automation_error,
    error_handler,
)


@pytest.mark.asyncio
async def test_handle_zone_error_automation_error():
    """Test handling AutomationError for zone."""
    error = ZoneNotFoundError(1)
    
    with patch("error_handler.logger") as mock_logger, \
         patch("error_handler.ERROR_COUNTER") as mock_counter:
        handle_zone_error(1, error, {"action": "test"})
        
        # Проверяем, что метрика была обновлена
        mock_counter.labels.assert_called_once_with(
            error_type="ZoneNotFoundError",
            zone_id="1"
        )
        mock_counter.labels.return_value.inc.assert_called_once()
        
        # Проверяем логирование
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert "Zone 1" in call_args[0][0]
        assert call_args[1]["extra"]["zone_id"] == 1
        assert call_args[1]["extra"]["error_type"] == "ZoneNotFoundError"


@pytest.mark.asyncio
async def test_handle_zone_error_standard_exception():
    """Test handling standard Exception for zone."""
    error = ValueError("Test error")
    
    with patch("error_handler.logger") as mock_logger, \
         patch("error_handler.ERROR_COUNTER") as mock_counter:
        handle_zone_error(1, error, {"action": "test"})
        
        mock_counter.labels.assert_called_once_with(
            error_type="ValueError",
            zone_id="1"
        )
        mock_logger.error.assert_called_once()
        call_args = mock_logger.error.call_args
        assert "Unexpected error" in call_args[0][0]


@pytest.mark.asyncio
async def test_handle_automation_error():
    """Test handling general automation error."""
    error = InvalidConfigurationError("Invalid config")
    
    with patch("error_handler.logger") as mock_logger, \
         patch("error_handler.ERROR_COUNTER") as mock_counter:
        handle_automation_error(error, {"action": "config_fetch"})
        
        mock_counter.labels.assert_called_once_with(
            error_type="InvalidConfigurationError",
            zone_id="global"
        )
        mock_logger.error.assert_called_once()


@pytest.mark.asyncio
async def test_error_handler_decorator_success():
    """Test error_handler decorator with successful execution."""
    @error_handler(zone_id=1, default_return=None)
    async def test_func(zone_id: int):
        return "success"
    
    result = await test_func(1)
    assert result == "success"


@pytest.mark.asyncio
async def test_error_handler_decorator_with_error():
    """Test error_handler decorator with error."""
    @error_handler(zone_id=1, default_return=None)
    async def test_func(zone_id: int):
        raise ValueError("Test error")
    
    with patch("error_handler.handle_zone_error") as mock_handle:
        result = await test_func(1)
        
        assert result is None
        mock_handle.assert_called_once()
        assert mock_handle.call_args[0][0] == 1
        assert isinstance(mock_handle.call_args[0][1], ValueError)


@pytest.mark.asyncio
async def test_error_handler_decorator_reraise():
    """Test error_handler decorator with reraise=True."""
    @error_handler(zone_id=1, default_return=None, reraise=True)
    async def test_func(zone_id: int):
        raise ValueError("Test error")
    
    with patch("error_handler.handle_zone_error") as mock_handle:
        with pytest.raises(ValueError):
            await test_func(1)
        
        mock_handle.assert_called_once()


@pytest.mark.asyncio
async def test_error_handler_extracts_zone_id_from_args():
    """Test error_handler extracts zone_id from function arguments."""
    @error_handler(default_return=None)
    async def test_func(zone_id: int, other_arg: str):
        raise ValueError("Test error")
    
    with patch("error_handler.handle_zone_error") as mock_handle:
        result = await test_func(1, "test")
        
        assert result is None
        mock_handle.assert_called_once()
        assert mock_handle.call_args[0][0] == 1


@pytest.mark.asyncio
async def test_error_handler_extracts_zone_id_from_kwargs():
    """Test error_handler extracts zone_id from keyword arguments."""
    @error_handler(default_return=None)
    async def test_func(other_arg: str, zone_id: int = 1):
        raise ValueError("Test error")
    
    with patch("error_handler.handle_zone_error") as mock_handle:
        result = await test_func("test", zone_id=2)
        
        assert result is None
        mock_handle.assert_called_once()
        assert mock_handle.call_args[0][0] == 2

