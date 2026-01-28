"""
MQTT step execution for E2E tests.
"""

import logging
from typing import Dict, Any, Optional

logger = logging.getLogger(__name__)


class MQTTStepExecutor:
    """Executes MQTT-related steps in E2E scenarios."""

    def __init__(self, mqtt_probe, variable_resolver):
        self.mqtt_probe = mqtt_probe
        self.variable_resolver = variable_resolver

    async def execute_mqtt_step(self, step_type: str, config: Dict[str, Any]) -> Any:
        """
        Execute an MQTT step.

        Args:
            step_type: Type of MQTT step
            config: Step configuration

        Returns:
            Step result
        """
        if step_type == "mqtt_publish":
            return await self._execute_mqtt_publish(config)
        elif step_type == "mqtt_subscribe":
            return await self._execute_mqtt_subscribe(config)
        elif step_type == "mqtt_wait_message":
            return await self._execute_mqtt_wait_message(config)
        else:
            raise ValueError(f"Unknown MQTT step type: {step_type}")

    async def _execute_mqtt_publish(self, config: Dict[str, Any]) -> None:
        """Publish MQTT message."""
        topic = config.get("topic", "")
        payload = config.get("payload", {})
        qos = config.get("qos", 0)
        retain = config.get("retain", False)

        # Resolve variables
        resolved_topic = self.variable_resolver.resolve_variables(topic)
        resolved_payload = self.variable_resolver.resolve_variables(payload)

        await self.mqtt_probe.publish(resolved_topic, resolved_payload, qos=qos, retain=retain)

    async def _execute_mqtt_subscribe(self, config: Dict[str, Any]) -> None:
        """Subscribe to MQTT topic."""
        topic = config.get("topic", "")
        qos = config.get("qos", 0)

        # Resolve variables
        resolved_topic = self.variable_resolver.resolve_variables(topic)

        await self.mqtt_probe.subscribe(resolved_topic, qos=qos)

    async def _execute_mqtt_wait_message(self, config: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Wait for MQTT message."""
        topic = config.get("topic")
        timeout = config.get("timeout", 10.0)
        filter_dict = config.get("filter", {})

        # Resolve variables
        resolved_topic = self.variable_resolver.resolve_variables(topic) if topic else None
        resolved_filter = self.variable_resolver.resolve_variables(filter_dict)

        return await self.mqtt_probe.wait_message(
            topic=resolved_topic,
            timeout=timeout,
            filter_dict=resolved_filter
        )
