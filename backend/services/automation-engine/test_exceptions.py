"""Tests for exceptions module."""
import pytest
from exceptions import (
    AutomationError,
    ZoneNotFoundError,
    InvalidConfigurationError,
    InvalidZoneDataError,
    NodeNotFoundError,
    TelemetryError,
    CommandPublishError,
    DatabaseError,
    MQTTError,
)


def test_automation_error():
    """Test AutomationError base exception."""
    error = AutomationError("Test error", {"key": "value"})
    assert str(error) == "Test error"
    assert error.message == "Test error"
    assert error.details == {"key": "value"}


def test_zone_not_found_error():
    """Test ZoneNotFoundError."""
    error = ZoneNotFoundError(1, {"reason": "deleted"})
    assert "Zone 1 not found" in str(error)
    assert error.zone_id == 1
    assert error.details == {"reason": "deleted"}


def test_invalid_configuration_error():
    """Test InvalidConfigurationError."""
    config = {"greenhouses": []}
    error = InvalidConfigurationError("Missing greenhouses", config)
    assert "Invalid configuration" in str(error)
    assert error.config == config
    assert "Missing greenhouses" in error.message


def test_invalid_zone_data_error():
    """Test InvalidZoneDataError."""
    data = {"targets": None}
    error = InvalidZoneDataError(1, "Invalid targets", data)
    assert "Invalid zone data for zone 1" in str(error)
    assert error.zone_id == 1
    assert error.details["data"] == data


def test_node_not_found_error():
    """Test NodeNotFoundError."""
    error = NodeNotFoundError(1, "irrigation", {"channel": "default"})
    assert "Node of type 'irrigation' not found for zone 1" in str(error)
    assert error.zone_id == 1
    assert error.node_type == "irrigation"


def test_telemetry_error():
    """Test TelemetryError."""
    error = TelemetryError(1, "No data", "PH")
    assert "Telemetry error for zone 1" in str(error)
    assert error.zone_id == 1
    assert error.metric == "PH"
    assert error.details["metric"] == "PH"


def test_command_publish_error():
    """Test CommandPublishError."""
    error = CommandPublishError(1, "irrigate", "MQTT disconnected", {"node": "nd-1"})
    assert "Failed to publish command 'irrigate' for zone 1" in str(error)
    assert error.zone_id == 1
    assert error.command == "irrigate"
    assert error.reason == "MQTT disconnected"


def test_database_error():
    """Test DatabaseError."""
    query = "SELECT * FROM zones WHERE id = $1"
    error = DatabaseError("Connection failed", query, {"zone_id": 1})
    assert "Database error" in str(error)
    assert error.query == query
    assert error.details["query"] == query


def test_mqtt_error():
    """Test MQTTError."""
    topic = "hydro/gh-1/zn-1/command"
    error = MQTTError("Publish failed", topic, {"retry_count": 3})
    assert "MQTT error" in str(error)
    assert error.topic == topic
    assert error.details["topic"] == topic

