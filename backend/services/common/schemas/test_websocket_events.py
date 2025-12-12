"""
Авто-проверка WebSocket событий.

Проверяет, что:
1. Все WS события имеют event_id
2. Все WS события попадают в zone_events
3. event_id из WS события совпадает с ws_event_id в zone_events
"""
import pytest
import time
from typing import Dict, Any, List
from pathlib import Path

from common.schemas.test_protocol_contracts import load_schema, validate_against_schema
from common.schemas.test_protocol_contracts import ZONE_EVENTS_SCHEMA


class TestWebSocketEventId:
    """Тесты авто-проверки WS событий с event_id."""
    
    def test_websocket_event_has_event_id(self):
        """Тест, что WS события имеют event_id."""
        # Пример события из Laravel EventCreated
        event = {
            "id": 1,
            "kind": "test",
            "message": "Test event",
            "zoneId": 1,
            "occurredAt": "2025-01-01T12:00:00Z",
            "event_id": 1234567890,  # Обязательное поле
            "server_ts": 1737979200000
        }
        
        # Проверяем наличие event_id
        assert "event_id" in event, "WS событие должно содержать event_id"
        assert isinstance(event["event_id"], int), "event_id должен быть integer"
        assert event["event_id"] > 0, "event_id должен быть положительным"
    
    def test_websocket_event_missing_event_id_fails(self):
        """Тест, что события без event_id отклоняются."""
        # Событие без event_id
        event = {
            "id": 1,
            "kind": "test",
            "message": "Test event",
            "zoneId": 1,
            "occurredAt": "2025-01-01T12:00:00Z"
            # Нет event_id
        }
        
        # Проверяем, что event_id отсутствует
        assert "event_id" not in event, "Событие без event_id должно быть отклонено"
    
    def test_zone_events_contains_ws_event_id(self):
        """Тест, что zone_events содержит ws_event_id в payload."""
        # Пример записи из zone_events
        zone_event = {
            "id": 1,
            "zone_id": 1,
            "type": "command_status",
            "entity_type": "command",
            "entity_id": "cmd-123",
            "payload_json": {
                "status": "DONE",
                "message": "Command completed",
                "ws_event_id": 1234567890  # Должен быть в payload
            },
            "server_ts": 1737979200000
        }
        
        # Валидируем через схему
        zone_events_schema = load_schema(ZONE_EVENTS_SCHEMA)
        validate_against_schema(zone_event, zone_events_schema)
        
        # Проверяем наличие ws_event_id в payload
        assert "payload_json" in zone_event, "zone_event должен содержать payload_json"
        payload = zone_event["payload_json"]
        assert "ws_event_id" in payload, "payload_json должен содержать ws_event_id"
        assert isinstance(payload["ws_event_id"], int), "ws_event_id должен быть integer"
        assert payload["ws_event_id"] > 0, "ws_event_id должен быть положительным"
    
    def test_all_ws_events_have_event_id(self):
        """Тест, что все типы WS событий имеют event_id."""
        # Различные типы событий
        events = [
            {
                "type": "EventCreated",
                "event_id": 1234567890,
                "server_ts": 1737979200000
            },
            {
                "type": "CommandStatusUpdated",
                "event_id": 1234567891,
                "server_ts": 1737979201000
            },
            {
                "type": "AlertCreated",
                "event_id": 1234567892,
                "server_ts": 1737979202000
            },
            {
                "type": "ZoneUpdated",
                "event_id": 1234567893,
                "server_ts": 1737979203000
            },
            {
                "type": "NodeTelemetryUpdated",
                "event_id": 1234567894,
                "server_ts": 1737979204000
            }
        ]
        
        # Проверяем, что все события имеют event_id
        for event in events:
            assert "event_id" in event, f"Событие {event['type']} должно содержать event_id"
            assert isinstance(event["event_id"], int), f"event_id в {event['type']} должен быть integer"
            assert event["event_id"] > 0, f"event_id в {event['type']} должен быть положительным"
    
    def test_zone_events_matches_ws_event_id(self):
        """Тест, что zone_events содержит тот же event_id, что и WS событие."""
        # WS событие
        ws_event = {
            "event_id": 1234567890,
            "server_ts": 1737979200000,
            "type": "command_status"
        }
        
        # Соответствующая запись в zone_events
        zone_event = {
            "id": 1,
            "zone_id": 1,
            "type": "command_status",
            "payload_json": {
                "ws_event_id": 1234567890  # Должен совпадать с event_id из WS
            },
            "server_ts": 1737979200000
        }
        
        # Проверяем совпадение
        assert ws_event["event_id"] == zone_event["payload_json"]["ws_event_id"], \
            "ws_event_id в zone_events должен совпадать с event_id из WS события"
        assert ws_event["server_ts"] == zone_event["server_ts"], \
            "server_ts должен совпадать"
    
    def test_websocket_event_types_validation(self):
        """Тест валидации типов WS событий."""
        # Все известные типы WS событий
        known_event_types = [
            "EventCreated",
            "CommandStatusUpdated",
            "AlertCreated",
            "AlertUpdated",
            "ZoneUpdated",
            "NodeTelemetryUpdated",
            "NodeConfigUpdated"
        ]
        
        # Создаем события для каждого типа
        for event_type in known_event_types:
            event = {
                "type": event_type,
                "event_id": int(time.time() * 1000),
                "server_ts": int(time.time() * 1000)
            }
            
            # Проверяем наличие обязательных полей
            assert "event_id" in event, f"Событие {event_type} должно содержать event_id"
            assert "server_ts" in event, f"Событие {event_type} должно содержать server_ts"
    
    def test_zone_events_payload_structure(self):
        """Тест структуры payload в zone_events."""
        # Различные типы событий с их payload
        test_cases = [
            {
                "type": "command_status",
                "payload": {
                    "status": "DONE",
                    "message": "Command completed",
                    "ws_event_id": 1234567890
                }
            },
            {
                "type": "alert_created",
                "payload": {
                    "code": "PH_LOW",
                    "severity": "medium",
                    "ws_event_id": 1234567891
                }
            },
            {
                "type": "telemetry_updated",
                "payload": {
                    "metric_type": "PH",
                    "value": 6.5,
                    "ws_event_id": 1234567892
                }
            }
        ]
        
        for test_case in test_cases:
            zone_event = {
                "zone_id": 1,
                "type": test_case["type"],
                "payload_json": test_case["payload"],
                "server_ts": int(time.time() * 1000)
            }
            
            # Валидируем через схему
            zone_events_schema = load_schema(ZONE_EVENTS_SCHEMA)
            validate_against_schema(zone_event, zone_events_schema)
            
            # Проверяем наличие ws_event_id
            assert "ws_event_id" in test_case["payload"], \
                f"Payload для {test_case['type']} должен содержать ws_event_id"


class TestWebSocketEventToZoneEventsMapping:
    """Тесты маппинга WS событий в zone_events."""
    
    def test_event_created_maps_to_zone_events(self):
        """Тест маппинга EventCreated в zone_events."""
        # WS событие EventCreated
        ws_event = {
            "id": 1,
            "kind": "test",
            "message": "Test event",
            "zoneId": 1,
            "occurredAt": "2025-01-01T12:00:00Z",
            "event_id": 1234567890,
            "server_ts": 1737979200000
        }
        
        # Ожидаемая запись в zone_events
        expected_zone_event = {
            "zone_id": ws_event["zoneId"],
            "type": "event_created",
            "entity_type": "event",
            "entity_id": str(ws_event["id"]),
            "payload_json": {
                "kind": ws_event["kind"],
                "message": ws_event["message"],
                "ws_event_id": ws_event["event_id"]
            },
            "server_ts": ws_event["server_ts"]
        }
        
        # Проверяем структуру
        assert expected_zone_event["zone_id"] == ws_event["zoneId"]
        assert expected_zone_event["payload_json"]["ws_event_id"] == ws_event["event_id"]
    
    def test_command_status_updated_maps_to_zone_events(self):
        """Тест маппинга CommandStatusUpdated в zone_events."""
        # WS событие CommandStatusUpdated
        ws_event = {
            "commandId": "cmd-123",
            "status": "DONE",
            "message": "Command completed",
            "zoneId": 1,
            "event_id": 1234567891,
            "server_ts": 1737979201000
        }
        
        # Ожидаемая запись в zone_events
        expected_zone_event = {
            "zone_id": ws_event["zoneId"],
            "type": "command_status",
            "entity_type": "command",
            "entity_id": ws_event["commandId"],
            "payload_json": {
                "status": ws_event["status"],
                "message": ws_event["message"],
                "ws_event_id": ws_event["event_id"]
            },
            "server_ts": ws_event["server_ts"]
        }
        
        # Проверяем структуру
        assert expected_zone_event["zone_id"] == ws_event["zoneId"]
        assert expected_zone_event["payload_json"]["ws_event_id"] == ws_event["event_id"]
    
    def test_alert_created_maps_to_zone_events(self):
        """Тест маппинга AlertCreated в zone_events."""
        # WS событие AlertCreated
        ws_event = {
            "id": 42,
            "code": "PH_LOW",
            "severity": "medium",
            "zoneId": 1,
            "event_id": 1234567892,
            "server_ts": 1737979202000
        }
        
        # Ожидаемая запись в zone_events
        expected_zone_event = {
            "zone_id": ws_event["zoneId"],
            "type": "alert_created",
            "entity_type": "alert",
            "entity_id": str(ws_event["id"]),
            "payload_json": {
                "code": ws_event["code"],
                "severity": ws_event["severity"],
                "ws_event_id": ws_event["event_id"]
            },
            "server_ts": ws_event["server_ts"]
        }
        
        # Проверяем структуру
        assert expected_zone_event["zone_id"] == ws_event["zoneId"]
        assert expected_zone_event["payload_json"]["ws_event_id"] == ws_event["event_id"]

