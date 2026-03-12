"""
Command Bus - централизованная публикация команд через MQTT.
"""
from typing import Optional, Dict, Any
import logging
from common.mqtt import MqttClient
from prometheus_client import Counter

logger = logging.getLogger(__name__)

# Метрики для отслеживания ошибок публикации
MQTT_PUBLISH_ERRORS = Counter("mqtt_publish_errors_total", "MQTT publish errors", ["error_type"])
COMMANDS_SENT = Counter("automation_commands_sent_total", "Commands sent by automation", ["zone_id", "metric"])


class CommandBus:
    """Централизованная публикация команд через MQTT."""
    
    def __init__(self, mqtt: MqttClient, gh_uid: str):
        """
        Инициализация Command Bus.
        
        Args:
            mqtt: MQTT клиент
            gh_uid: UID теплицы
        """
        self.mqtt = mqtt
        self.gh_uid = gh_uid
    
    async def publish_command(
        self,
        zone_id: int,
        node_uid: str,
        channel: str,
        cmd: str,
        params: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        Публикация команды через MQTT.
        
        Args:
            zone_id: ID зоны
            node_uid: UID узла
            channel: Канал узла
            cmd: Команда
            params: Параметры команды
        
        Returns:
            True если команда успешно отправлена, False в противном случае
        """
        try:
            if not self.mqtt.is_connected():
                error_type = "not_connected"
                MQTT_PUBLISH_ERRORS.labels(error_type=error_type).inc()
                logger.error(f"Zone {zone_id}: Cannot publish command - MQTT not connected")
                return False
            
            payload = {"cmd": cmd, **(({"params": params}) if params else {})}
            topic = f"hydro/{self.gh_uid}/zn-{zone_id}/{node_uid}/{channel}/command"
            self.mqtt.publish_json(topic, payload, qos=1, retain=False)
            COMMANDS_SENT.labels(zone_id=zone_id, metric=cmd).inc()
            return True
        except Exception as e:
            error_type = type(e).__name__
            MQTT_PUBLISH_ERRORS.labels(error_type=error_type).inc()
            logger.error(f"Zone {zone_id}: Failed to publish command {cmd} to {topic}: {e}", exc_info=True)
            return False
    
    async def publish_controller_command(
        self,
        zone_id: int,
        command: Dict[str, Any]
    ) -> bool:
        """
        Публикация команды от контроллера.
        
        Args:
            zone_id: ID зоны
            command: Команда от контроллера с полями:
                - node_uid: UID узла
                - channel: Канал узла
                - cmd: Команда
                - params: Параметры команды (опционально)
        
        Returns:
            True если команда успешно отправлена, False в противном случае
        """
        node_uid = command.get('node_uid')
        channel = command.get('channel', 'default')
        cmd = command.get('cmd')
        params = command.get('params')
        
        if not node_uid or not cmd:
            logger.warning(f"Zone {zone_id}: Invalid command structure - missing node_uid or cmd")
            return False
        
        return await self.publish_command(zone_id, node_uid, channel, cmd, params)

