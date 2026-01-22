"""
Multi-node orchestration для node-sim.
Управляет множеством нод в одном процессе.
"""

import asyncio
import logging
import random
from typing import List, Dict, Optional
from dataclasses import dataclass

from .mqtt_client import MqttClient
from .model import NodeModel, NodeType
from .commands import CommandHandler
from .telemetry import TelemetryPublisher
from .config_report import publish_config_report
from .state_machine import FailureMode
from .config import MqttConfig, NodeConfig, TelemetryConfig, FailureModeConfig

logger = logging.getLogger(__name__)


@dataclass
class NodeInstance:
    """Экземпляр ноды с её компонентами."""
    node: NodeModel
    mqtt: MqttClient
    command_handler: CommandHandler
    telemetry: TelemetryPublisher
    config: Dict  # Оригинальная конфигурация ноды


class MultiNodeOrchestrator:
    """
    Оркестратор для управления множеством нод.
    
    Один процесс управляет N нодами (5-50), по разным зонам.
    Все ноды публикуют telemetry параллельно без падений.
    """
    
    def __init__(self, mqtt_config: MqttConfig):
        """
        Инициализация оркестратора.
        
        Args:
            mqtt_config: Общая конфигурация MQTT для всех нод
        """
        self.mqtt_config = mqtt_config
        self.nodes: List[NodeInstance] = []
        self._running = False
        self._tasks: List[asyncio.Task] = []
    
    async def add_node(
        self,
        node_config: NodeConfig,
        telemetry_config: TelemetryConfig,
        failure_mode: Optional[FailureModeConfig] = None
    ):
        """
        Добавить ноду в оркестратор.
        
        Args:
            node_config: Конфигурация ноды
            telemetry_config: Конфигурация телеметрии
            failure_mode: Режим отказов (опционально)
        """
        # Создаем уникальный MQTT клиент для каждой ноды
        mqtt = MqttClient(
            host=self.mqtt_config.host,
            port=self.mqtt_config.port,
            username=self.mqtt_config.username,
            password=self.mqtt_config.password,
            client_id=f"node-sim-{node_config.node_uid}",
            tls=self.mqtt_config.tls,
            ca_certs=self.mqtt_config.ca_certs,
            keepalive=self.mqtt_config.keepalive
        )

        mqtt.set_node_info(
            gh_uid=node_config.gh_uid,
            zone_uid=node_config.zone_uid,
            node_uid=node_config.node_uid,
            node_hw_id=node_config.hardware_id,
            preconfig_mode=(node_config.mode == "preconfig"),
        )
        
        # Подключаемся к MQTT
        try:
            if not mqtt.connect():
                raise RuntimeError("Failed to connect to MQTT broker")
            logger.info(f"Connected MQTT for node {node_config.node_uid}")
        except Exception as e:
            logger.error(f"Failed to connect MQTT for node {node_config.node_uid}: {e}")
            raise
        
        # Создаем модель ноды
        node = NodeModel(
            gh_uid=node_config.gh_uid,
            zone_uid=node_config.zone_uid,
            node_uid=node_config.node_uid,
            hardware_id=node_config.hardware_id,
            node_type=NodeType(node_config.node_type),
            mode=node_config.mode,
            sensors=node_config.sensors,
            actuators=node_config.actuators,
        )
        
        # Публикуем config_report один раз при старте (если включено)
        if node_config.config_report_on_start:
            publish_config_report(
                node=node,
                mqtt=mqtt,
                telemetry_interval_s=telemetry_config.interval_seconds,
            )
        
        # Создаем публикатор телеметрии
        telemetry = TelemetryPublisher(
            node=node,
            mqtt=mqtt,
            telemetry_interval_s=telemetry_config.interval_seconds
        )
        
        # Создаем публикатор статуса и heartbeat
        from .status import StatusPublisher
        status_publisher = StatusPublisher(
            node=node,
            mqtt=mqtt,
            status_interval_s=telemetry_config.heartbeat_interval_seconds * 2,  # status реже heartbeat
            heartbeat_interval_s=telemetry_config.heartbeat_interval_seconds
        )

        loop = asyncio.get_running_loop()
        
        # Создаем обработчик команд (передаем telemetry_publisher для поддержки hil_request_telemetry)
        command_handler = CommandHandler(node, mqtt, telemetry_publisher=telemetry, event_loop=loop)
        
        # Настраиваем режим отказов, если указан
        if failure_mode:
            fm = FailureMode(
                delay_response=failure_mode.delay_response,
                delay_ms=failure_mode.delay_ms,
                drop_response=failure_mode.drop_response,
                duplicate_response=failure_mode.duplicate_response,
                random_drop_rate=failure_mode.random_drop_rate,
                random_duplicate_rate=failure_mode.random_duplicate_rate,
                random_delay_ms_min=failure_mode.random_delay_ms_min,
                random_delay_ms_max=failure_mode.random_delay_ms_max
            )
            command_handler.state_machine.set_failure_mode(fm)
        
        # Создаем публикатор ошибок и интегрируем с моделью
        from .errors import ErrorPublisher, create_error_callback
        error_publisher = ErrorPublisher(
            mqtt_client=mqtt,
            gh_uid=node_config.gh_uid,
            zone_uid=node_config.zone_uid,
            node_uid=node_config.node_uid,
            hardware_id=node_config.hardware_id,
            mode=node_config.mode,
        )
        # Регистрируем колбэк для автоматической публикации ошибок из модели
        node.register_error_callback(create_error_callback(error_publisher))
        
        # Создаем экземпляр ноды
        node_instance = NodeInstance(
            node=node,
            mqtt=mqtt,
            command_handler=command_handler,
            telemetry=telemetry,
            config={
                "node": node_config,
                "telemetry": telemetry_config,
                "failure_mode": failure_mode,
                "status_publisher": status_publisher,
                "error_publisher": error_publisher
            }
        )
        
        self.nodes.append(node_instance)
        logger.info(f"Added node {node_config.node_uid} to orchestrator")
    
    async def start(self):
        """Запустить все ноды."""
        if self._running:
            logger.warning("Orchestrator is already running")
            return
        
        self._running = True
        logger.info(f"Starting orchestrator with {len(self.nodes)} nodes")
        
        # Запускаем все ноды параллельно
        for node_instance in self.nodes:
            try:
                await node_instance.command_handler.start()
                await node_instance.telemetry.start()
                # Запускаем status_publisher если есть
                if "status_publisher" in node_instance.config:
                    await node_instance.config["status_publisher"].start()
                logger.info(f"Started node {node_instance.node.node_uid}")
            except Exception as e:
                logger.error(f"Failed to start node {node_instance.node.node_uid}: {e}", exc_info=True)

        # Запускаем offline-симуляцию, если настроена
        for node_instance in self.nodes:
            failure_mode = node_instance.config.get("failure_mode")
            if not failure_mode:
                continue
            if failure_mode.offline_chance > 0 and failure_mode.offline_duration_s > 0:
                self._tasks.append(
                    asyncio.create_task(self._offline_loop(node_instance, failure_mode))
                )
        
        logger.info(f"Orchestrator started. {len(self.nodes)} nodes running.")
    
    async def stop(self):
        """Остановить все ноды."""
        if not self._running:
            return
        
        self._running = False
        logger.info("Stopping orchestrator...")
        
        # Останавливаем фоновые задачи
        for task in self._tasks:
            task.cancel()
        self._tasks.clear()

        # Останавливаем все ноды
        stop_tasks = []
        for node_instance in self.nodes:
            stop_tasks.append(node_instance.telemetry.stop())
            if "status_publisher" in node_instance.config:
                stop_tasks.append(node_instance.config["status_publisher"].stop())
            stop_tasks.append(node_instance.mqtt.disconnect())
        
        await asyncio.gather(*stop_tasks, return_exceptions=True)
        
        logger.info("Orchestrator stopped")

    async def _offline_loop(self, node_instance: NodeInstance, failure_mode: FailureModeConfig):
        """Периодически переводит ноду в offline для тестирования алертов."""
        interval = max(1.0, float(failure_mode.offline_check_interval_s or 30.0))
        duration = max(1.0, float(failure_mode.offline_duration_s))
        while self._running:
            await asyncio.sleep(interval)
            if not self._running:
                break
            if node_instance.node.is_offline():
                continue
            if random.random() < failure_mode.offline_chance:
                node_instance.node.set_offline(duration)
                logger.warning(
                    "Node %s set offline for %.1fs (random failure)",
                    node_instance.node.node_uid,
                    duration
                )
    
    async def run_forever(self):
        """Запустить оркестратор и работать бесконечно."""
        await self.start()
        
        try:
            # Ждем бесконечно
            while self._running:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            await self.stop()
    
    def get_node_count(self) -> int:
        """Получить количество нод."""
        return len(self.nodes)
    
    def get_node_by_uid(self, node_uid: str) -> Optional[NodeInstance]:
        """Получить ноду по UID."""
        for node_instance in self.nodes:
            if node_instance.node.node_uid == node_uid:
                return node_instance
        return None


async def create_orchestrator_from_config(config_data: Dict) -> MultiNodeOrchestrator:
    """
    Создать оркестратор из конфигурации.
    
    Args:
        config_data: Словарь с конфигурацией (из YAML)
    
    Returns:
        MultiNodeOrchestrator
    """
    # Общая конфигурация MQTT
    mqtt_data = config_data.get("mqtt", {})
    mqtt_config = MqttConfig(
        host=mqtt_data.get("host", "localhost"),
        port=mqtt_data.get("port", 1883),
        username=mqtt_data.get("username"),
        password=mqtt_data.get("password"),
        tls=mqtt_data.get("tls", False),
        ca_certs=mqtt_data.get("ca_certs"),
        client_id=mqtt_data.get("client_id"),
        keepalive=mqtt_data.get("keepalive", 60)
    )
    
    # Создаем оркестратор
    orchestrator = MultiNodeOrchestrator(mqtt_config)
    
    # Общие настройки по умолчанию
    default_telemetry = TelemetryConfig(
        interval_seconds=config_data.get("telemetry", {}).get("interval_seconds", 5.0),
        heartbeat_interval_seconds=config_data.get("telemetry", {}).get("heartbeat_interval_seconds", 30.0)
    )
    
    default_failure_mode = None
    if "failure_mode" in config_data:
        fm_data = config_data["failure_mode"]
        default_failure_mode = FailureModeConfig(
            delay_response=fm_data.get("delay_response", False),
            delay_ms=fm_data.get("delay_ms", 0),
            drop_response=fm_data.get("drop_response", False),
            duplicate_response=fm_data.get("duplicate_response", False),
            random_drop_rate=fm_data.get("random_drop_rate", 0.0),
            random_duplicate_rate=fm_data.get("random_duplicate_rate", 0.0),
            random_delay_ms_min=fm_data.get("random_delay_ms_min", 0),
            random_delay_ms_max=fm_data.get("random_delay_ms_max", 0),
            offline_chance=fm_data.get("offline_chance", 0.0),
            offline_duration_s=fm_data.get("offline_duration_s", 0.0),
            offline_check_interval_s=fm_data.get("offline_check_interval_s", 30.0)
        )
    
    # Добавляем ноды из конфигурации
    nodes_data = config_data.get("nodes", [])
    if not nodes_data:
        raise ValueError("No nodes defined in configuration")

    default_node = NodeConfig()
    
    for node_data in nodes_data:
        # Конфигурация ноды
        node_config = NodeConfig(
            gh_uid=node_data.get("gh_uid", "gh-1"),
            zone_uid=node_data.get("zone_uid", "zn-1"),
            node_uid=node_data.get("node_uid"),
            hardware_id=node_data.get("hardware_id"),
            node_type=node_data.get("node_type", "unknown"),
            mode=node_data.get("mode", "preconfig"),
            config_report_on_start=node_data.get("config_report_on_start", True),
            sensors=node_data.get("sensors", node_data.get("channels", default_node.sensors)),
            actuators=node_data.get("actuators", default_node.actuators),
        )
        
        # Проверяем обязательные поля
        if not node_config.node_uid:
            raise ValueError("node.node_uid is required for each node")
        if not node_config.hardware_id:
            raise ValueError("node.hardware_id is required for each node")
        
        # Конфигурация телеметрии для этой ноды (может переопределять общую)
        telemetry_config = default_telemetry
        if "telemetry" in node_data:
            telemetry_data = node_data["telemetry"]
            telemetry_config = TelemetryConfig(
                interval_seconds=telemetry_data.get("interval_seconds", default_telemetry.interval_seconds),
                heartbeat_interval_seconds=telemetry_data.get("heartbeat_interval_seconds", default_telemetry.heartbeat_interval_seconds)
            )
        
        # Режим отказов для этой ноды (может переопределять общий)
        failure_mode = default_failure_mode
        if "failure_mode" in node_data:
            fm_data = node_data["failure_mode"]
            failure_mode = FailureModeConfig(
                delay_response=fm_data.get("delay_response", False),
                delay_ms=fm_data.get("delay_ms", 0),
                drop_response=fm_data.get("drop_response", False),
                duplicate_response=fm_data.get("duplicate_response", False),
                random_drop_rate=fm_data.get("random_drop_rate", 0.0),
                random_duplicate_rate=fm_data.get("random_duplicate_rate", 0.0),
                random_delay_ms_min=fm_data.get("random_delay_ms_min", 0),
                random_delay_ms_max=fm_data.get("random_delay_ms_max", 0),
                offline_chance=fm_data.get("offline_chance", 0.0),
                offline_duration_s=fm_data.get("offline_duration_s", 0.0),
                offline_check_interval_s=fm_data.get("offline_check_interval_s", 30.0)
            )
        
        # Добавляем ноду
        await orchestrator.add_node(node_config, telemetry_config, failure_mode)
    
    return orchestrator
