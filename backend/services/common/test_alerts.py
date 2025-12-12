"""Tests for alerts module."""
import pytest
import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch, MagicMock
from common.alerts import AlertSource, AlertCode, create_alert


@pytest.mark.asyncio
async def test_create_alert_with_all_fields():
    """Test creating alert with all fields when no existing alert."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts.execute") as mock_execute:
        # Нет существующих алертов
        mock_fetch.return_value = []
        
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            details={"flow_value": 0.0, "min_flow": 1.0}
        )
        
        # Проверяем, что был поиск существующего алерта
        mock_fetch.assert_called_once()
        
        # Проверяем, что был INSERT
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert "INSERT INTO alerts" in call_args[0][0]
        assert call_args[0][1] == 1  # zone_id
        assert call_args[0][2] == AlertSource.BIZ.value  # source
        assert call_args[0][3] == AlertCode.BIZ_NO_FLOW.value  # code
        assert call_args[0][4] == "No water flow detected"  # type
        
        # Проверяем, что details содержит count=1 и last_seen_at
        details_json = call_args[0][5]
        details = json.loads(details_json)
        assert details["count"] == 1
        assert "last_seen_at" in details
        assert details["flow_value"] == 0.0
        assert details["min_flow"] == 1.0


@pytest.mark.asyncio
async def test_create_alert_without_details():
    """Test creating alert without details when no existing alert."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts.execute") as mock_execute:
        # Нет существующих алертов
        mock_fetch.return_value = []
        
        await create_alert(
            zone_id=1,
            source=AlertSource.INFRA.value,
            code=AlertCode.INFRA_MQTT_DOWN.value,
            type="MQTT connection lost"
        )
        
        # Проверяем, что был INSERT
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        details_json = call_args[0][5]
        details = json.loads(details_json)
        assert details["count"] == 1
        assert "last_seen_at" in details


@pytest.mark.asyncio
async def test_create_alert_with_null_zone_id():
    """Test creating alert with null zone_id (global alert)."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts.execute") as mock_execute:
        # Нет существующих алертов
        mock_fetch.return_value = []
        
        await create_alert(
            zone_id=None,
            source=AlertSource.INFRA.value,
            code=AlertCode.INFRA_SERVICE_DOWN.value,
            type="Service unavailable"
        )
        
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert call_args[0][1] is None  # zone_id is None


def test_alert_source_enum():
    """Test AlertSource enum values."""
    assert AlertSource.BIZ.value == "biz"
    assert AlertSource.INFRA.value == "infra"


def test_alert_code_enum():
    """Test AlertCode enum values."""
    assert AlertCode.BIZ_NO_FLOW.value == "biz_no_flow"
    assert AlertCode.BIZ_OVERCURRENT.value == "biz_overcurrent"
    assert AlertCode.BIZ_DRY_RUN.value == "biz_dry_run"
    assert AlertCode.BIZ_PUMP_STUCK_ON.value == "biz_pump_stuck_on"
    assert AlertCode.BIZ_HIGH_PH.value == "biz_high_ph"
    assert AlertCode.BIZ_LOW_PH.value == "biz_low_ph"
    assert AlertCode.BIZ_HIGH_EC.value == "biz_high_ec"
    assert AlertCode.BIZ_LOW_EC.value == "biz_low_ec"
    assert AlertCode.BIZ_HIGH_TEMP.value == "biz_high_temp"
    assert AlertCode.BIZ_LOW_TEMP.value == "biz_low_temp"
    assert AlertCode.BIZ_HIGH_HUMIDITY.value == "biz_high_humidity"
    assert AlertCode.BIZ_LOW_HUMIDITY.value == "biz_low_humidity"
    assert AlertCode.BIZ_LIGHT_FAILURE.value == "biz_light_failure"
    assert AlertCode.BIZ_NODE_OFFLINE.value == "biz_node_offline"
    assert AlertCode.BIZ_CONFIG_ERROR.value == "biz_config_error"
    assert AlertCode.INFRA_MQTT_DOWN.value == "infra_mqtt_down"
    assert AlertCode.INFRA_DB_UNREACHABLE.value == "infra_db_unreachable"
    assert AlertCode.INFRA_SERVICE_DOWN.value == "infra_service_down"


@pytest.mark.asyncio
async def test_create_alert_deduplicates_existing():
    """Test that create_alert updates existing alert instead of creating new one."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts.execute") as mock_execute:
        # Существует активный алерт
        existing_alert = {
            "id": 123,
            "details": {
                "flow_value": 0.0,
                "min_flow": 1.0,
                "count": 5,
                "last_seen_at": "2024-01-01T12:00:00+00:00"
            }
        }
        mock_fetch.return_value = [existing_alert]
        
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            details={"flow_value": 0.1, "additional_info": "test"}
        )
        
        # Проверяем, что был поиск существующего алерта
        mock_fetch.assert_called_once()
        
        # Проверяем, что был UPDATE, а не INSERT
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert "UPDATE alerts" in call_args[0][0]
        assert call_args[0][2] == 123  # alert_id
        
        # Проверяем, что details обновлены правильно
        details_json = call_args[0][1]
        details = json.loads(details_json)
        assert details["count"] == 6  # Увеличился с 5 до 6
        assert "last_seen_at" in details
        assert details["flow_value"] == 0.1  # Обновилось
        assert details["min_flow"] == 1.0  # Сохранилось старое значение
        assert details["additional_info"] == "test"  # Добавилось новое


@pytest.mark.asyncio
async def test_create_alert_suppression_window():
    """Test that suppression_window prevents updates if last_seen_at is recent."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts.execute") as mock_execute:
        # Существует активный алерт с недавним last_seen_at
        now = datetime.now(timezone.utc)
        recent_time = (now.replace(microsecond=0)).isoformat()
        existing_alert = {
            "id": 123,
            "details": {
                "count": 5,
                "last_seen_at": recent_time
            }
        }
        mock_fetch.return_value = [existing_alert]
        
        # Пытаемся создать алерт с окном подавления 60 секунд
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            suppression_window_sec=60
        )
        
        # Проверяем, что был поиск
        mock_fetch.assert_called_once()
        
        # Проверяем, что UPDATE НЕ был вызван (подавлено)
        mock_execute.assert_not_called()


@pytest.mark.asyncio
async def test_create_alert_suppression_window_expired():
    """Test that suppression_window allows updates if last_seen_at is old."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts.execute") as mock_execute:
        # Существует активный алерт со старым last_seen_at
        old_time = "2024-01-01T12:00:00+00:00"
        existing_alert = {
            "id": 123,
            "details": {
                "count": 5,
                "last_seen_at": old_time
            }
        }
        mock_fetch.return_value = [existing_alert]
        
        # Пытаемся создать алерт с окном подавления 60 секунд
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No water flow detected",
            suppression_window_sec=60
        )
        
        # Проверяем, что был UPDATE (окно подавления истекло)
        mock_execute.assert_called_once()
        call_args = mock_execute.call_args
        assert "UPDATE alerts" in call_args[0][0]
        
        details_json = call_args[0][1]
        details = json.loads(details_json)
        assert details["count"] == 6  # Счетчик увеличился


@pytest.mark.asyncio
async def test_create_alert_deduplication_key_zone_code_status():
    """Test that deduplication uses (zone_id, code, status=ACTIVE) as key."""
    with patch("common.alerts.fetch") as mock_fetch, \
         patch("common.alerts.execute") as mock_execute:
        # Первый вызов - создает новый алерт
        mock_fetch.return_value = []
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,
            type="No flow"
        )
        
        # Второй вызов с тем же zone_id и code - обновляет существующий
        existing_alert = {
            "id": 123,
            "details": {"count": 1, "last_seen_at": "2024-01-01T12:00:00+00:00"}
        }
        mock_fetch.return_value = [existing_alert]
        
        await create_alert(
            zone_id=1,
            source=AlertSource.BIZ.value,
            code=AlertCode.BIZ_NO_FLOW.value,  # Тот же code
            type="Different type"  # Разный type, но это не влияет на дедупликацию
        )
        
        # Проверяем, что fetch был вызван с правильными параметрами (zone_id, code)
        fetch_calls = mock_fetch.call_args_list
        assert len(fetch_calls) == 2
        # Второй вызов должен искать по zone_id=1 и code='biz_no_flow'
        second_call = fetch_calls[1]
        assert "zone_id IS NOT DISTINCT FROM" in second_call[0][0]
        assert second_call[0][1] == 1  # zone_id
        assert second_call[0][2] == AlertCode.BIZ_NO_FLOW.value  # code

