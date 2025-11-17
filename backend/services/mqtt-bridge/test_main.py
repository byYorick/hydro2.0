"""Tests for mqtt-bridge endpoints."""
import pytest
from httpx import AsyncClient
from unittest.mock import patch, Mock, AsyncMock
from main import app


@pytest.fixture
def mock_auth():
    """Mock authentication."""
    with patch("main._auth") as mock:
        yield mock


@pytest.fixture
def mock_mqtt_client():
    """Mock MQTT client."""
    mqtt = Mock()
    mqtt.start = Mock()
    mqtt.publish_json = Mock()
    with patch("main.MqttClient", return_value=mqtt):
        yield mqtt


@pytest.mark.asyncio
async def test_zone_fill_success(mock_auth, mock_mqtt_client):
    """Test fill endpoint when successful."""
    mock_auth.return_value = None  # Auth passed
    
    with patch("main.get_gh_uid_for_zone") as mock_gh, \
         patch("main.execute_fill_mode") as mock_fill:
        
        mock_gh.return_value = "gh-1"
        mock_fill.return_value = {
            "success": True,
            "target_level": 0.9,
            "final_level": 0.9,
            "elapsed_sec": 30.5
        }
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/1/fill",
                json={"target_level": 0.9},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["data"]["success"] is True
            assert data["data"]["target_level"] == 0.9


@pytest.mark.asyncio
async def test_zone_fill_invalid_target_level(mock_auth):
    """Test fill endpoint with invalid target_level."""
    mock_auth.return_value = None
    
    # target_level слишком низкий
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/bridge/zones/1/fill",
            json={"target_level": 0.05},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "target_level must be between 0.1 and 1.0" in response.json()["detail"]


@pytest.mark.asyncio
async def test_zone_fill_zone_not_found(mock_auth):
    """Test fill endpoint when zone not found."""
    mock_auth.return_value = None
    
    with patch("main.get_gh_uid_for_zone") as mock_gh:
        mock_gh.return_value = None
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/1/fill",
                json={"target_level": 0.9},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 404


@pytest.mark.asyncio
async def test_zone_drain_success(mock_auth, mock_mqtt_client):
    """Test drain endpoint when successful."""
    mock_auth.return_value = None
    
    with patch("main.get_gh_uid_for_zone") as mock_gh, \
         patch("main.execute_drain_mode") as mock_drain:
        
        mock_gh.return_value = "gh-1"
        mock_drain.return_value = {
            "success": True,
            "target_level": 0.1,
            "final_level": 0.1,
            "elapsed_sec": 25.3
        }
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/1/drain",
                json={"target_level": 0.1},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["data"]["success"] is True
            assert data["data"]["target_level"] == 0.1


@pytest.mark.asyncio
async def test_zone_drain_invalid_target_level(mock_auth):
    """Test drain endpoint with invalid target_level."""
    mock_auth.return_value = None
    
    # target_level слишком высокий
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post(
            "/bridge/zones/1/drain",
            json={"target_level": 0.95},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "target_level must be between 0.0 and 0.9" in response.json()["detail"]


@pytest.mark.asyncio
async def test_zone_drain_with_max_duration(mock_auth, mock_mqtt_client):
    """Test drain endpoint with max_duration_sec parameter."""
    mock_auth.return_value = None
    
    with patch("main.get_gh_uid_for_zone") as mock_gh, \
         patch("main.execute_drain_mode") as mock_drain:
        
        mock_gh.return_value = "gh-1"
        mock_drain.return_value = {"success": True}
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/1/drain",
                json={"target_level": 0.1, "max_duration_sec": 120},
                headers={"Authorization": "Bearer test-token"}
            )
            
        assert response.status_code == 200
        # Проверяем, что max_duration_sec был передан
        mock_drain.assert_called_once()
        call_args = mock_drain.call_args
        # call_args[0] - позиционные аргументы: (zone_id, target_level, mqtt, gh_uid, max_duration_sec)
        # max_duration_sec передается как 5-й позиционный аргумент
        assert len(call_args[0]) >= 5
        assert call_args[0][4] == 120  # 5-й аргумент (индекс 4)


@pytest.mark.asyncio
async def test_zone_calibrate_flow_success(mock_auth, mock_mqtt_client):
    """Test calibrate-flow endpoint when successful."""
    mock_auth.return_value = None  # Auth passed
    
    with patch("main.get_gh_uid_for_zone") as mock_gh, \
         patch("main.calibrate_flow") as mock_calibrate:
        
        mock_gh.return_value = "gh-1"
        mock_calibrate.return_value = {
            "success": True,
            "K": 0.5,
            "avg_flow_l_per_min": 2.0,
            "samples_count": 10,
            "pump_duration_sec": 10,
            "calibrated_at": "2025-01-01T12:00:00Z"
        }
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/1/calibrate-flow",
                json={"node_id": 1, "channel": "flow_sensor", "pump_duration_sec": 10},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "ok"
            assert data["data"]["success"] is True
            assert data["data"]["K"] == 0.5
            assert data["data"]["avg_flow_l_per_min"] == 2.0


@pytest.mark.asyncio
async def test_zone_calibrate_flow_invalid_duration(mock_auth):
    """Test calibrate-flow endpoint with invalid pump duration."""
    mock_auth.return_value = None
    
    async with AsyncClient(app=app, base_url="http://test") as client:
        # Слишком короткая длительность
        response = await client.post(
            "/bridge/zones/1/calibrate-flow",
            json={"node_id": 1, "channel": "flow_sensor", "pump_duration_sec": 3},
            headers={"Authorization": "Bearer test-token"}
        )
        
        assert response.status_code == 400
        assert "pump_duration_sec must be between 5 and 60" in response.json()["detail"]


@pytest.mark.asyncio
async def test_zone_calibrate_flow_zone_not_found(mock_auth):
    """Test calibrate-flow endpoint when zone not found."""
    mock_auth.return_value = None
    
    with patch("main.get_gh_uid_for_zone") as mock_gh:
        mock_gh.return_value = None  # Зона не найдена
        
        async with AsyncClient(app=app, base_url="http://test") as client:
            response = await client.post(
                "/bridge/zones/999/calibrate-flow",
                json={"node_id": 1, "channel": "flow_sensor"},
                headers={"Authorization": "Bearer test-token"}
            )
            
            assert response.status_code == 404
            assert "Zone not found" in response.json()["detail"]

