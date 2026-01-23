"""
CLI интерфейс для node-sim.
"""

import asyncio
import argparse
import random
import sys
from pathlib import Path

from .config import SimConfig
from .logging import setup_logging, get_logger

logger = get_logger(__name__)


async def run_simulator(config: SimConfig):
    """
    Запустить симулятор ноды.
    
    Args:
        config: Конфигурация симулятора
    """
    logger.info("Starting node simulator...")
    logger.info(f"Node: {config.node.node_uid} ({config.node.hardware_id})")
    logger.info(f"Mode: {config.node.mode}")
    logger.info(f"MQTT: {config.mqtt.host}:{config.mqtt.port}")
    
    # Импортируем компоненты
    try:
        from .mqtt_client import MqttClient
        from .model import NodeModel, NodeType
        from .commands import CommandHandler
        from .telemetry import TelemetryPublisher
        from .status import StatusPublisher
        from .config_report import publish_config_report
    except ImportError as e:
        logger.error(f"Failed to import components: {e}")
        logger.error("Make sure all dependencies are installed: pip install -r requirements.txt")
        sys.exit(1)

    # Захватываем текущий event loop, чтобы передать его в обработчики
    event_loop = asyncio.get_running_loop()
    
    # Создаем MQTT клиент
    mqtt = MqttClient(
        host=config.mqtt.host,
        port=config.mqtt.port,
        username=config.mqtt.username,
        password=config.mqtt.password,
        client_id=config.mqtt.client_id or f"node-sim-{config.node.node_uid}",
        tls=config.mqtt.tls,
        ca_certs=config.mqtt.ca_certs,
        keepalive=config.mqtt.keepalive
    )

    mqtt.set_node_info(
        gh_uid=config.node.gh_uid,
        zone_uid=config.node.zone_uid,
        node_uid=config.node.node_uid,
        node_hw_id=config.node.hardware_id,
        preconfig_mode=(config.node.mode == "preconfig"),
    )
    
    # Подключаемся к MQTT
    try:
        if not mqtt.connect():
            raise RuntimeError("Failed to connect to MQTT broker")
        logger.info("Connected to MQTT")
    except Exception as e:
        logger.error(f"Failed to connect to MQTT: {e}")
        sys.exit(1)
    
    # Создаем модель ноды
    node = NodeModel(
        gh_uid=config.node.gh_uid,
        zone_uid=config.node.zone_uid,
        node_uid=config.node.node_uid,
        hardware_id=config.node.hardware_id,
        node_type=NodeType(config.node.node_type),
        mode=config.node.mode,
        sensors=config.node.sensors,
        actuators=config.node.actuators,
    )
    
    # Публикуем config_report один раз при старте (если включено)
    if config.node.config_report_on_start:
        publish_config_report(
            node=node,
            mqtt=mqtt,
            telemetry_interval_s=config.telemetry.interval_seconds,
        )
    
    # Создаем публикатор телеметрии
    telemetry = TelemetryPublisher(
        node=node,
        mqtt=mqtt,
        telemetry_interval_s=config.telemetry.interval_seconds
    )
    
    # Создаем публикатор статуса и heartbeat
    status_publisher = StatusPublisher(
        node=node,
        mqtt=mqtt,
        status_interval_s=config.telemetry.status_interval_seconds if hasattr(config.telemetry, 'status_interval_seconds') else 60.0,
        heartbeat_interval_s=config.telemetry.heartbeat_interval_seconds
    )
    
    # Создаем обработчик команд (передаем telemetry_publisher для поддержки hil_request_telemetry)
    command_handler = CommandHandler(node, mqtt, telemetry_publisher=telemetry, event_loop=event_loop)
    offline_task = None
    if config.failure_mode:
        from .state_machine import FailureMode
        failure_mode = FailureMode(
            delay_response=config.failure_mode.delay_response,
            delay_ms=config.failure_mode.delay_ms,
            drop_response=config.failure_mode.drop_response,
            duplicate_response=config.failure_mode.duplicate_response,
            random_drop_rate=config.failure_mode.random_drop_rate,
            random_duplicate_rate=config.failure_mode.random_duplicate_rate,
            random_delay_ms_min=config.failure_mode.random_delay_ms_min,
            random_delay_ms_max=config.failure_mode.random_delay_ms_max
        )
        command_handler.state_machine.set_failure_mode(failure_mode)
        if config.failure_mode.offline_chance > 0 and config.failure_mode.offline_duration_s > 0:
            offline_task = asyncio.create_task(
                _offline_loop(node, mqtt, config.failure_mode)
            )
    
    # Создаем публикатор ошибок и интегрируем с моделью
    from .errors import ErrorPublisher, create_error_callback
    error_publisher = ErrorPublisher(
        mqtt_client=mqtt,
        gh_uid=config.node.gh_uid,
        zone_uid=config.node.zone_uid,
        node_uid=config.node.node_uid,
        hardware_id=config.node.hardware_id,
        mode=config.node.mode,
    )
    # Регистрируем колбэк для автоматической публикации ошибок из модели
    node.register_error_callback(create_error_callback(error_publisher))
    
    # Запускаем компоненты
    try:
        await command_handler.start()
        await telemetry.start()
        await status_publisher.start()
        
        logger.info("Node simulator is running. Press Ctrl+C to stop.")
        
        # Ждем бесконечно
        while True:
            await asyncio.sleep(1)
    
    except KeyboardInterrupt:
        logger.info("Stopping node simulator...")
    finally:
        await telemetry.stop()
        await status_publisher.stop()
        if offline_task:
            offline_task.cancel()
        mqtt.disconnect()
        logger.info("Node simulator stopped")


async def _offline_loop(node: "NodeModel", mqtt, failure_mode):
    """Периодически переводит ноду в offline для тестирования алертов."""
    interval = max(1.0, float(failure_mode.offline_check_interval_s or 30.0))
    duration = max(1.0, float(failure_mode.offline_duration_s))
    while True:
        await asyncio.sleep(interval)
        if node.is_offline():
            continue
        if random.random() < failure_mode.offline_chance:
            node.set_offline(duration)
            mqtt.disconnect()
            logger.warning(
                "Node %s set offline for %.1fs (random failure)",
                node.node_uid,
                duration
            )
            await asyncio.sleep(duration)
            if not mqtt.connect():
                logger.warning("Node %s failed to reconnect after offline window", node.node_uid)


async def run_multi_nodes(config_path: str):
    """
    Запустить multi-node симулятор.
    
    Args:
        config_path: Путь к конфигурационному файлу
    """
    import yaml
    from pathlib import Path
    from .multi import create_orchestrator_from_config
    
    logger.info(f"Loading multi-node configuration from {config_path}")
    
    # Загружаем конфигурацию
    path = Path(config_path)
    if not path.exists():
        logger.error(f"Configuration file not found: {config_path}")
        sys.exit(1)
    
    with open(path, 'r', encoding='utf-8') as f:
        config_data = yaml.safe_load(f)
    
    # Валидация
    if "nodes" not in config_data:
        logger.error("Configuration must contain 'nodes' array")
        sys.exit(1)
    
    nodes_count = len(config_data["nodes"])
    if nodes_count == 0:
        logger.error("At least one node must be defined")
        sys.exit(1)
    
    logger.info(f"Configuration loaded: {nodes_count} nodes")
    
    # Создаем оркестратор
    try:
        orchestrator = await create_orchestrator_from_config(config_data)
        logger.info(f"Orchestrator created with {orchestrator.get_node_count()} nodes")
        
        # Запускаем
        await orchestrator.run_forever()
    
    except Exception as e:
        logger.error(f"Error running multi-node simulator: {e}", exc_info=True)
        sys.exit(1)


async def run_scenario(config: SimConfig, scenario_name: str):
    """
    Запустить сценарий симуляции.
    
    Args:
        config: Конфигурация симулятора
        scenario_name: Имя сценария (например, S_overcurrent)
    """
    logger.info(f"Running scenario: {scenario_name}")
    
    # Применяем настройки сценария
    if scenario_name == "S_overcurrent":
        # Сценарий перегрузки по току
        logger.info("Scenario: Overcurrent - simulating high current draw")
        logger.info("This scenario will trigger infra_overcurrent error after enabling overcurrent mode")
        
        # Импортируем компоненты
        from .mqtt_client import MqttClient
        from .model import NodeModel, NodeType
        from .commands import CommandHandler
        from .telemetry import TelemetryPublisher
        from .status import StatusPublisher
        from .config_report import publish_config_report
        from .errors import ErrorPublisher, create_error_callback, create_overcurrent_error
        # Создаем MQTT клиент
        mqtt = MqttClient(
            host=config.mqtt.host,
            port=config.mqtt.port,
            username=config.mqtt.username,
            password=config.mqtt.password,
            client_id=config.mqtt.client_id or f"node-sim-{config.node.node_uid}",
            tls=config.mqtt.tls,
            ca_certs=config.mqtt.ca_certs,
            keepalive=config.mqtt.keepalive
        )

        mqtt.set_node_info(
            gh_uid=config.node.gh_uid,
            zone_uid=config.node.zone_uid,
            node_uid=config.node.node_uid,
            node_hw_id=config.node.hardware_id,
            preconfig_mode=(config.node.mode == "preconfig"),
        )
        loop = asyncio.get_running_loop()
        
        # Подключаемся к MQTT
        try:
            if not mqtt.connect():
                raise RuntimeError("Failed to connect to MQTT broker")
            logger.info("Connected to MQTT")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            sys.exit(1)
        
        # Создаем модель ноды
        node = NodeModel(
            gh_uid=config.node.gh_uid,
            zone_uid=config.node.zone_uid,
            node_uid=config.node.node_uid,
            hardware_id=config.node.hardware_id,
            node_type=NodeType(config.node.node_type),
            mode=config.node.mode,
            sensors=config.node.sensors,
            actuators=config.node.actuators,
        )
        
        # Публикуем config_report один раз при старте (если включено)
        if config.node.config_report_on_start:
            publish_config_report(
                node=node,
                mqtt=mqtt,
                telemetry_interval_s=config.telemetry.interval_seconds,
            )
        
        # Создаем публикатор ошибок
        error_publisher = ErrorPublisher(
            mqtt_client=mqtt,
            gh_uid=config.node.gh_uid,
            zone_uid=config.node.zone_uid,
            node_uid=config.node.node_uid,
            hardware_id=config.node.hardware_id,
            mode=config.node.mode,
        )
        node.register_error_callback(create_error_callback(error_publisher))
        
        # Создаем публикатор телеметрии
        telemetry = TelemetryPublisher(
            node=node,
            mqtt=mqtt,
            telemetry_interval_s=config.telemetry.interval_seconds
        )
        
        # Создаем публикатор статуса и heartbeat
        status_publisher = StatusPublisher(
            node=node,
            mqtt=mqtt,
            status_interval_s=config.telemetry.status_interval_seconds if hasattr(config.telemetry, 'status_interval_seconds') else 60.0,
            heartbeat_interval_s=config.telemetry.heartbeat_interval_seconds
        )
        
        # Создаем обработчик команд (передаем telemetry_publisher для поддержки hil_request_telemetry)
        command_handler = CommandHandler(node, mqtt, telemetry_publisher=telemetry, event_loop=loop)
        
        # Запускаем компоненты
        try:
            await command_handler.start()
            await telemetry.start()
            await status_publisher.start()
            
            logger.info("Node simulator is running. Press Ctrl+C to stop.")
            logger.info("Waiting 5 seconds before triggering overcurrent scenario...")
            await asyncio.sleep(5)
            
            # Включаем насос для создания базового тока
            logger.info("Enabling main_pump to create base current...")
            node.set_actuator("main_pump", True, pwm_value=255)
            await asyncio.sleep(2)
            
            # Включаем режим перегрузки
            logger.info("Enabling overcurrent mode (this should trigger infra_overcurrent error)...")
            node.set_overcurrent_mode(True, current=600.0)  # 600 мА - выше порога
            await asyncio.sleep(1)
            
            # Публикуем ошибку перегрузки явно
            current_ma = node.get_sensor_value("ina209_ma") or 0.0
            logger.info(f"Current INA209: {current_ma} mA")
            create_overcurrent_error(
                error_publisher,
                current_ma=current_ma,
                threshold_ma=500.0,
                actuator="main_pump"
            )
            logger.info("infra_overcurrent error published. This should create an ACTIVE alert and WS push.")
            
            # Ждем бесконечно
            while True:
                await asyncio.sleep(1)
        
        except KeyboardInterrupt:
            logger.info("Stopping node simulator...")
        finally:
            await telemetry.stop()
            await status_publisher.stop()
            mqtt.disconnect()
            logger.info("Node simulator stopped")
    else:
        # Для других сценариев запускаем обычный симулятор
        await run_simulator(config)


def main():
    """Главная функция CLI."""
    parser = argparse.ArgumentParser(
        description="Node Simulator for Hydro system",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Command to execute")
    
    # Команда run
    run_parser = subparsers.add_parser("run", help="Run node simulator")
    run_parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to configuration YAML file"
    )
    run_parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    # Команда scenario
    scenario_parser = subparsers.add_parser("scenario", help="Run scenario")
    scenario_parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to configuration YAML file"
    )
    scenario_parser.add_argument(
        "--name",
        type=str,
        required=True,
        help="Scenario name (e.g., S_overcurrent)"
    )
    scenario_parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    # Команда multi
    multi_parser = subparsers.add_parser("multi", help="Run multiple nodes")
    multi_parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to multi-node configuration YAML file"
    )
    multi_parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        help="Logging level"
    )
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Настраиваем логирование
    setup_logging(level=args.log_level)
    
    try:
        # Выполняем команду
        if args.command == "run":
            # Загружаем конфигурацию для одной ноды
            config = SimConfig.from_file(args.config)
            config.validate()
            asyncio.run(run_simulator(config))
        elif args.command == "scenario":
            # Загружаем конфигурацию для одной ноды
            config = SimConfig.from_file(args.config)
            config.validate()
            asyncio.run(run_scenario(config, args.name))
        elif args.command == "multi":
            # Multi-node использует другую структуру конфигурации
            asyncio.run(run_multi_nodes(args.config))
    
    except FileNotFoundError as e:
        logger.error(f"Configuration file not found: {e}")
        sys.exit(1)
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
