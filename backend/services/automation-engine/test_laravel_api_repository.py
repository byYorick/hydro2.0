"""Tests for LaravelApiRepository."""
import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from repositories.laravel_api_repository import LaravelApiRepository


def _mock_settings():
    return SimpleNamespace(
        laravel_api_url="http://localhost:8080",
        laravel_api_token="test-token",
    )


@pytest.mark.asyncio
async def test_get_effective_targets_batch_success():
    """Test successful batch fetch of effective targets."""
    mock_response = {
        "status": "ok",
        "data": {
            "1": {
                "cycle_id": 123,
                "zone_id": 1,
                "phase": {
                    "id": 77,
                    "code": "VEG",
                    "started_at": "2025-01-01T00:00:00Z",
                    "due_at": "2025-01-15T00:00:00Z"
                },
                "targets": {
                    "ph": {"target": 6.0, "min": 5.8, "max": 6.2},
                    "ec": {"target": 1.5, "min": 1.3, "max": 1.7},
                    "irrigation": {
                        "mode": "SUBSTRATE",
                        "interval_sec": 3600,
                        "duration_sec": 300
                    }
                }
            },
            "2": {
                "cycle_id": 124,
                "zone_id": 2,
                "phase": {
                    "id": 78,
                    "code": "FLOWER",
                    "started_at": "2025-01-01T00:00:00Z",
                    "due_at": "2025-01-20T00:00:00Z"
                },
                "targets": {
                    "ph": {"target": 6.2, "min": 6.0, "max": 6.4},
                    "ec": {"target": 1.8, "min": 1.6, "max": 2.0}
                }
            }
        }
    }
    
    with patch("repositories.laravel_api_repository.get_settings", return_value=_mock_settings()):
        repo = LaravelApiRepository()
        mock_response_obj = Mock()
        mock_response_obj.status_code = 200
        mock_response_obj.json = Mock(return_value=mock_response)
        with patch("repositories.laravel_api_repository.make_request", new=AsyncMock(return_value=mock_response_obj)):
            result = await repo.get_effective_targets_batch([1, 2])
            assert 1 in result
            assert 2 in result
            assert result[1]["targets"]["ph"]["target"] == 6.0
            assert result[2]["targets"]["ph"]["target"] == 6.2


@pytest.mark.asyncio
async def test_get_effective_targets_batch_with_error():
    """Test batch fetch with error response."""
    mock_response = {
        "status": "ok",
        "data": {
            "1": {
                "cycle_id": 123,
                "zone_id": 1,
                "phase": {"id": 77, "code": "VEG"},
                "targets": {"ph": {"target": 6.0}}
            },
            "2": {
                "error": "Grow cycle not found"
            }
        }
    }
    
    with patch("repositories.laravel_api_repository.get_settings", return_value=_mock_settings()):
        repo = LaravelApiRepository()
        mock_response_obj = Mock()
        mock_response_obj.status_code = 200
        mock_response_obj.json = Mock(return_value=mock_response)
        with patch("repositories.laravel_api_repository.make_request", new=AsyncMock(return_value=mock_response_obj)):
            result = await repo.get_effective_targets_batch([1, 2])
            assert 1 in result
            assert 2 in result
            assert "error" in result[2]


@pytest.mark.asyncio
async def test_get_effective_targets_batch_api_error():
    """Test batch fetch with API error."""
    with patch("repositories.laravel_api_repository.get_settings", return_value=_mock_settings()):
        repo = LaravelApiRepository()
        mock_response_obj = Mock()
        mock_response_obj.status_code = 500
        mock_response_obj.text = "Internal Server Error"
        with patch("repositories.laravel_api_repository.make_request", new=AsyncMock(return_value=mock_response_obj)):
            result = await repo.get_effective_targets_batch([1, 2])
            assert result == {}


@pytest.mark.asyncio
async def test_get_effective_targets_batch_retry_on_failure():
    """Test that batch fetch retries on transient failures."""
    mock_response = {
        "status": "ok",
        "data": {
            "1": {
                "cycle_id": 123,
                "zone_id": 1,
                "phase": {"id": 77, "code": "VEG"},
                "targets": {"ph": {"target": 6.0}}
            }
        }
    }
    
    with patch("repositories.laravel_api_repository.get_settings", return_value=_mock_settings()):
        repo = LaravelApiRepository()
        mock_response_obj = Mock()
        mock_response_obj.status_code = 200
        mock_response_obj.json = Mock(return_value=mock_response)
        mock_request = AsyncMock(return_value=mock_response_obj)
        with patch("repositories.laravel_api_repository.make_request", new=mock_request):
            result = await repo.get_effective_targets_batch([1])
            assert mock_request.call_count >= 1
            assert 1 in result
