#!/usr/bin/env python3
"""
Эмулятор нод для нагрузочного тестирования.
Имитирует поведение реальных нод: отправляет телеметрию и heartbeat через MQTT.
"""

import asyncio
import json
import random
import time
import os
from datetime import datetime
from typing import Dict, List, Optional
import paho.mqtt.client as mqtt
import logging
from dataclasses import dataclass

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class NodeConfig:
    """Конфигурация эмулируемой ноды."""
    greenhouse_uid: str
    zone_uid: str
    node_uid: str
    node_type: str
    channels: List[str]
    telemetry_interval: float = 5.0  # Интервал отправки телеметрии в секундах
    heartbeat_interval: float = 30.0  # Интервал отправки heartbeat в секундах


class NodeEmulator:
    """Эмулятор одной ноды."""
    
    def __init__(self, config: NodeConfig, mqtt_client: mqtt.Client):
        self.config = config
        self.mqtt = mqtt_client
        self.running = False
        self.telemetry_task: Optional[asyncio.Task] = None
        self.heartbeat_task: Optional[asyncio.Task] = None
        
    async def start(self):
        """Запустить эмуляцию ноды."""
        self.running = True
        self.telemetry_task = asyncio.create_task(self._telemetry_loop())
        self.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(f"Node {self.config.node_uid} started")
        
    async def stop(self):
        """Остановить эмуляцию ноды."""
        self.running = False
        if self.telemetry_task:
            self.telemetry_task.cancel()
        if self.heartbeat_task:
            self.heartbeat_task.cancel()
        logger.info(f"Node {self.config.node_uid} stopped")
        
    async def _telemetry_loop(self):
        """Цикл отправки телеметрии."""
        while self.running:
            try:
                await self._send_telemetry()
                await asyncio.sleep(self.config.telemetry_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in telemetry loop for {self.config.node_uid}: {e}")
                await asyncio.sleep(1)
                
    async def _heartbeat_loop(self):
        """Цикл отправки heartbeat."""
        while self.running:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(self.config.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error in heartbeat loop for {self.config.node_uid}: {e}")
                await asyncio.sleep(1)
                
    async def _send_telemetry(self):
        """Отправить телеметрию."""
        # Отправляем телеметрию для каждого канала отдельно
        # Формат топика: hydro/{gh}/{zone}/{node}/{channel}/telemetry
        for channel in self.config.channels:
            topic = f"hydro/{self.config.greenhouse_uid}/{self.config.zone_uid}/{self.config.node_uid}/{channel}/telemetry"
            
            # Генерируем значение для канала
            channel_lower = channel.lower()
            if channel_lower in ("ph", "ph_sensor"):
                value = round(random.uniform(5.5, 7.5), 2)
                metric_type = "PH"
            elif channel_lower in ("ec", "ec_sensor"):
                value = round(random.uniform(1.0, 3.0), 2)
                metric_type = "EC"
            elif channel_lower in ("temperature", "air_temp_c", "temp_air", "temp"):
                value = round(random.uniform(18.0, 28.0), 1)
                metric_type = "TEMPERATURE"
            elif channel_lower in ("humidity", "air_rh", "humidity_air", "rh"):
                value = round(random.uniform(40.0, 80.0), 1)
                metric_type = "HUMIDITY"
            elif "co2" in channel_lower:
                value = round(random.uniform(400.0, 1200.0), 0)
                metric_type = "CO2"
            elif "lux" in channel_lower or "light" in channel_lower:
                value = round(random.uniform(0, 1000), 1)
                metric_type = "LIGHT_INTENSITY"
            elif channel_lower in ("water_level", "level"):
                value = round(random.uniform(0, 100), 1)
                metric_type = "WATER_LEVEL"
            elif channel_lower in ("flow_present", "flow"):
                value = round(random.uniform(0, 5), 2)
                metric_type = "FLOW_RATE"
            elif channel_lower in ("ina209_ma", "current_ma", "current", "pump_bus_current"):
                value = round(random.uniform(0, 500), 1)
                metric_type = "PUMP_CURRENT"
            else:
                value = round(random.uniform(0, 100), 2)
                metric_type = channel.upper()
            
            # Формат payload согласно MQTT_SPEC_FULL.md
            payload = {
                "metric_type": metric_type,
                "value": value,
                "ts": time.time(),
                "channel": channel,
                "node_id": self.config.node_uid,
                "stable": True,
                "stub": False
            }
            
            message = json.dumps(payload)
            result = self.mqtt.publish(topic, message, qos=1)
            
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning(f"Failed to publish telemetry for {self.config.node_uid}/{channel}: {result.rc}")
            
    async def _send_heartbeat(self):
        """Отправить heartbeat."""
        topic = f"hydro/{self.config.greenhouse_uid}/{self.config.zone_uid}/{self.config.node_uid}/heartbeat"
        
        payload = {
            "ts": int(time.time()),
            "uptime_seconds": random.randint(1000, 100000),
            "free_heap_bytes": random.randint(50000, 200000),
            "rssi": random.randint(-90, -30),
        }
        
        message = json.dumps(payload)
        result = self.mqtt.publish(topic, message, qos=1)
        
        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            logger.warning(f"Failed to publish heartbeat for {self.config.node_uid}: {result.rc}")


class NodeEmulatorManager:
    """Менеджер для управления множеством эмулируемых нод."""
    
    def __init__(self, mqtt_host: str = "localhost", mqtt_port: int = 1883,
                 mqtt_user: Optional[str] = None, mqtt_password: Optional[str] = None):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.mqtt_user = mqtt_user
        self.mqtt_password = mqtt_password
        self.mqtt_client: Optional[mqtt.Client] = None
        self.nodes: List[NodeEmulator] = []
        self.running = False
        
    def _on_connect(self, client, userdata, flags, rc):
        """Callback при подключении к MQTT."""
        if rc == 0:
            logger.info("Connected to MQTT broker")
        else:
            logger.error(f"Failed to connect to MQTT broker: {rc}")
            
    def _on_disconnect(self, client, userdata, rc):
        """Callback при отключении от MQTT."""
        logger.warning(f"Disconnected from MQTT broker: {rc}")
        
    async def connect_mqtt(self):
        """Подключиться к MQTT брокеру."""
        self.mqtt_client = mqtt.Client(client_id=f"node-emulator-{os.getpid()}")
        
        if self.mqtt_user and self.mqtt_password:
            self.mqtt_client.username_pw_set(self.mqtt_user, self.mqtt_password)
            
        self.mqtt_client.on_connect = self._on_connect
        self.mqtt_client.on_disconnect = self._on_disconnect
        
        try:
            self.mqtt_client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.mqtt_client.loop_start()
            await asyncio.sleep(1)  # Даем время на подключение
            logger.info(f"MQTT client connected to {self.mqtt_host}:{self.mqtt_port}")
        except Exception as e:
            logger.error(f"Failed to connect to MQTT: {e}")
            raise
            
    async def load_nodes_from_api(self, api_url: str, token: Optional[str] = None) -> List[NodeConfig]:
        """Загрузить конфигурацию нод из API."""
        import httpx
        
        headers = {}
        if token:
            headers["Authorization"] = f"Bearer {token}"
            
        async with httpx.AsyncClient() as client:
            try:
                response = await client.get(
                    f"{api_url}/api/nodes",
                    headers=headers,
                    timeout=30.0
                )
                
                if response.status_code != 200:
                    logger.error(f"Failed to load nodes: {response.status_code}")
                    return []
                    
                data = response.json()
                # Может быть data.data или просто data
                nodes_data = data.get("data", [])
                if not nodes_data and isinstance(data, list):
                    nodes_data = data
                
                configs = []
                for node_data in nodes_data:
                    # Получаем zone_id и загружаем зону отдельно
                    zone_id = node_data.get("zone_id")
                    if not zone_id:
                        continue
                    
                    # Загружаем зону через API или используем данные из ответа
                    zone_uid = node_data.get("zone", {}).get("uid") if isinstance(node_data.get("zone"), dict) else None
                    greenhouse_uid = None
                    
                    if zone_uid:
                        # Пытаемся получить greenhouse_uid из zone
                        zone_data = node_data.get("zone", {})
                        if isinstance(zone_data, dict):
                            greenhouse_data = zone_data.get("greenhouse")
                            if isinstance(greenhouse_data, dict):
                                greenhouse_uid = greenhouse_data.get("uid")
                    
                    # Если не удалось получить из ответа, используем значения по умолчанию
                    if not greenhouse_uid:
                        greenhouse_uid = "gh-load-test"
                    if not zone_uid:
                        zone_uid = f"zone-{zone_id}"
                        
                    config = NodeConfig(
                        greenhouse_uid=greenhouse_uid,
                        zone_uid=zone_uid,
                        node_uid=node_data.get("uid", f"node-{node_data.get('id')}"),
                        node_type=node_data.get("type", "sensor"),
                        channels=["ph", "ec", "temperature", "humidity"],
                        telemetry_interval=random.uniform(3.0, 7.0),
                        heartbeat_interval=random.uniform(25.0, 35.0)
                    )
                    configs.append(config)
                    
                logger.info(f"Loaded {len(configs)} nodes from API")
                return configs
                
            except Exception as e:
                logger.error(f"Error loading nodes from API: {e}")
                return []
                
    def create_test_nodes(self, count: int, greenhouse_uid: str = "gh-load-test",
                         zones_per_greenhouse: int = 20) -> List[NodeConfig]:
        """Создать тестовые конфигурации нод."""
        configs = []
        
        for i in range(count):
            zone_index = i % zones_per_greenhouse
            zone_uid = f"zone-load-test-{zone_index}"
            node_uid = f"node-load-test-{i}"
            
            # Разные типы нод
            node_types = ["ph", "ec", "sensor", "controller"]
            node_type = node_types[i % len(node_types)]
            
            # Разные наборы каналов
            if node_type == "ph":
                channels = ["ph", "temperature"]
            elif node_type == "ec":
                channels = ["ec", "temperature"]
            else:
                channels = ["ph", "ec", "temperature", "humidity"]
                
            config = NodeConfig(
                greenhouse_uid=greenhouse_uid,
                zone_uid=zone_uid,
                node_uid=node_uid,
                node_type=node_type,
                channels=channels,
                telemetry_interval=random.uniform(3.0, 7.0),
                heartbeat_interval=random.uniform(25.0, 35.0)
            )
            configs.append(config)
            
        logger.info(f"Created {len(configs)} test node configurations")
        return configs
        
    async def start_nodes(self, configs: List[NodeConfig]):
        """Запустить эмуляцию всех нод."""
        if not self.mqtt_client:
            await self.connect_mqtt()
            
        self.nodes = []
        for config in configs:
            node = NodeEmulator(config, self.mqtt_client)
            self.nodes.append(node)
            await node.start()
            # Небольшая задержка между запусками для избежания перегрузки
            await asyncio.sleep(0.01)
            
        self.running = True
        logger.info(f"Started {len(self.nodes)} node emulators")
        
    async def stop_nodes(self):
        """Остановить эмуляцию всех нод."""
        self.running = False
        for node in self.nodes:
            await node.stop()
        self.nodes = []
        
        if self.mqtt_client:
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            
        logger.info("All node emulators stopped")
        
    async def run_for_duration(self, duration_seconds: int):
        """Запустить эмуляцию на определенное время."""
        await asyncio.sleep(duration_seconds)
        await self.stop_nodes()


async def main():
    """Основная функция."""
    import argparse
    
    parser = argparse.ArgumentParser(description='Node emulator for load testing')
    parser.add_argument('--nodes', type=int, default=500, help='Number of nodes to emulate')
    parser.add_argument('--duration', type=int, default=300, help='Test duration in seconds')
    parser.add_argument('--mqtt-host', default='localhost', help='MQTT broker host')
    parser.add_argument('--mqtt-port', type=int, default=1883, help='MQTT broker port')
    parser.add_argument('--mqtt-user', default=None, help='MQTT username')
    parser.add_argument('--mqtt-password', default=None, help='MQTT password')
    parser.add_argument('--api-url', default='http://localhost:8080', help='Laravel API URL')
    parser.add_argument('--api-token', default=None, help='API token for loading nodes')
    parser.add_argument('--load-from-api', action='store_true', help='Load nodes from API instead of creating test nodes')
    
    args = parser.parse_args()
    
    print("=" * 60)
    print("NODE EMULATOR FOR LOAD TESTING")
    print("=" * 60)
    print(f"Nodes: {args.nodes}")
    print(f"Duration: {args.duration}s")
    print(f"MQTT: {args.mqtt_host}:{args.mqtt_port}")
    print("=" * 60)
    
    manager = NodeEmulatorManager(
        mqtt_host=args.mqtt_host,
        mqtt_port=args.mqtt_port,
        mqtt_user=args.mqtt_user,
        mqtt_password=args.mqtt_password
    )
    
    try:
        # Загружаем или создаем конфигурации нод
        if args.load_from_api:
            print("\n[1/3] Loading nodes from API...")
            configs = await manager.load_nodes_from_api(args.api_url, args.api_token)
            if len(configs) < args.nodes:
                print(f"Warning: Only {len(configs)} nodes loaded from API, creating additional test nodes...")
                additional = manager.create_test_nodes(args.nodes - len(configs))
                configs.extend(additional)
        else:
            print("\n[1/3] Creating test node configurations...")
            configs = manager.create_test_nodes(args.nodes)
            
        print(f"✓ Prepared {len(configs)} node configurations")
        
        # Запускаем эмуляцию
        print("\n[2/3] Starting node emulation...")
        await manager.start_nodes(configs)
        print(f"✓ Started {len(configs)} node emulators")
        
        # Запускаем на определенное время
        print(f"\n[3/3] Running for {args.duration} seconds...")
        print("Press Ctrl+C to stop early")
        await manager.run_for_duration(args.duration)
        
        print("\n" + "=" * 60)
        print("LOAD TEST COMPLETED")
        print("=" * 60)
        
    except KeyboardInterrupt:
        print("\n\nStopping emulators...")
        await manager.stop_nodes()
        print("Stopped")
    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)
        await manager.stop_nodes()
        raise


if __name__ == "__main__":
    asyncio.run(main())
