"""Prometheus counters для dev/monitoring scripts automation-engine.

Команды AE3 публикуются только через history-logger REST API; прямой MQTT publish
удалён вместе с legacy CommandBus.
"""

from prometheus_client import Counter

MQTT_PUBLISH_ERRORS = Counter("mqtt_publish_errors_total", "MQTT publish errors", ["error_type"])
COMMANDS_SENT = Counter("automation_commands_sent_total", "Commands sent by automation", ["zone_id", "metric"])

__all__ = ["COMMANDS_SENT", "MQTT_PUBLISH_ERRORS"]
