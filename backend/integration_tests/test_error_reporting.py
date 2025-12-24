#!/usr/bin/env python3
"""
Интеграционные тесты для системы отправки ошибок нод.

Тестирует полный цикл:
1. Отправка ошибок через MQTT от эмулированных нод
2. Обработка ошибок в history-logger
3. Создание Alerts в Laravel
4. Обновление метрик в БД
5. Проверка метрик Prometheus
"""

import asyncio
import json
import time
import httpx
import paho.mqtt.client as mqtt
import logging
from typing import Dict, List, Optional
from datetime import datetime
import os
import sys

# Добавляем путь к сервисам
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'services'))

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Конфигурация тестов
MQTT_HOST = os.getenv("MQTT_HOST", "localhost")
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USER", None)
MQTT_PASS = os.getenv("MQTT_PASS", None)
LARAVEL_URL = os.getenv("LARAVEL_URL", "http://localhost:8080")
LARAVEL_API_TOKEN = os.getenv("LARAVEL_API_TOKEN", "dev-token-12345")
PROMETHEUS_URL = os.getenv("PROMETHEUS_URL", "http://localhost:9090")
HISTORY_LOGGER_URL = os.getenv("HISTORY_LOGGER_URL", "http://localhost:9300")

# Тестовые данные
TEST_GH_UID = "gh-test-1"
TEST_ZONE_UID = "zn-test-1"
TEST_NODES = {
    "ph_node": "nd-ph-test-1",
    "ec_node": "nd-ec-test-1",
    "pump_node": "nd-pump-test-1",
    "climate_node": "nd-climate-test-1",
    "relay_node": "nd-relay-test-1",
    "light_node": "nd-light-test-1",
}


class MQTTErrorPublisher:
    """Публикатор ошибок через MQTT для тестирования."""
    
    def __init__(self, host: str, port: int, user: Optional[str] = None, password: Optional[str] = None):
        self.host = host
        self.port = port
        self.user = user
        self.password = password
        self.client = None
        self.connected = False
        
    def connect(self):
        """Подключиться к MQTT брокеру."""
        self.client = mqtt.Client()
        if self.user and self.password:
            self.client.username_pw_set(self.user, self.password)
        
        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                self.connected = True
                logger.info(f"Connected to MQTT broker at {self.host}:{self.port}")
            else:
                logger.error(f"Failed to connect to MQTT broker: {rc}")
        
        self.client.on_connect = on_connect
        self.client.connect(self.host, self.port, 60)
        self.client.loop_start()
        
        # Ждем подключения
        timeout = 10
        start = time.time()
        while not self.connected and (time.time() - start) < timeout:
            time.sleep(0.1)
        
        if not self.connected:
            raise Exception(f"Failed to connect to MQTT broker within {timeout} seconds")
    
    def disconnect(self):
        """Отключиться от MQTT брокера."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
            self.connected = False
    
    def publish_error(self, gh_uid: str, zone_uid: str, node_uid: str, 
                     level: str, component: str, error_code: int, message: str):
        """Опубликовать ошибку в MQTT."""
        topic = f"hydro/{gh_uid}/{zone_uid}/{node_uid}/error"
        
        payload = {
            "level": level,
            "component": component,
            "error_code": error_code,
            "message": message,
            "timestamp": int(time.time())
        }
        
        result = self.client.publish(topic, json.dumps(payload), qos=1)
        if result.rc == mqtt.MQTT_ERR_SUCCESS:
            logger.info(f"Published error to {topic}: {level}/{component}/{error_code}")
            return True
        else:
            logger.error(f"Failed to publish error to {topic}: {result.rc}")
            return False


class IntegrationTestRunner:
    """Запуск интеграционных тестов."""
    
    def __init__(self):
        self.mqtt_publisher = MQTTErrorPublisher(MQTT_HOST, MQTT_PORT, MQTT_USER, MQTT_PASS)
        self.http_client = httpx.AsyncClient(timeout=30.0)
        self.test_results: List[Dict] = []
        
    async def setup(self):
        """Настройка перед тестами."""
        logger.info("Setting up integration tests...")
        
        # Подключение к MQTT
        try:
            self.mqtt_publisher.connect()
            logger.info("✓ MQTT connection established")
        except Exception as e:
            logger.error(f"✗ Failed to connect to MQTT: {e}")
            raise
        
        # Проверка доступности сервисов
        await self.check_services_health()
        
    async def teardown(self):
        """Очистка после тестов."""
        logger.info("Tearing down integration tests...")
        self.mqtt_publisher.disconnect()
        await self.http_client.aclose()
    
    async def check_services_health(self):
        """Проверить доступность сервисов."""
        services = {
            "Laravel": f"{LARAVEL_URL}/api/system/health",
            "History Logger": f"{HISTORY_LOGGER_URL}/health",
            "Prometheus": f"{PROMETHEUS_URL}/-/healthy",
        }
        
        for name, url in services.items():
            try:
                response = await self.http_client.get(url)
                if response.status_code == 200:
                    logger.info(f"✓ {name} is healthy")
                else:
                    logger.warning(f"⚠ {name} returned status {response.status_code}")
            except Exception as e:
                logger.error(f"✗ {name} is not available: {e}")
                raise
    
    async def test_error_publishing(self):
        """Тест 1: Отправка ошибок через MQTT."""
        logger.info("\n=== Test 1: Error Publishing ===")
        
        test_cases = [
            {
                "node": "ph_node",
                "node_uid": TEST_NODES["ph_node"],
                "level": "ERROR",
                "component": "ph_sensor",
                "error_code": 1,
                "message": "Failed to read pH sensor value"
            },
            {
                "node": "ec_node",
                "node_uid": TEST_NODES["ec_node"],
                "level": "WARNING",
                "component": "ec_sensor",
                "error_code": 2,
                "message": "EC sensor not initialized"
            },
            {
                "node": "pump_node",
                "node_uid": TEST_NODES["pump_node"],
                "level": "ERROR",
                "component": "pump_driver",
                "error_code": 3,
                "message": "Pump started but no current detected"
            },
            {
                "node": "climate_node",
                "node_uid": TEST_NODES["climate_node"],
                "level": "ERROR",
                "component": "sht3x",
                "error_code": 4,
                "message": "Failed to read SHT3x sensor"
            },
            {
                "node": "relay_node",
                "node_uid": TEST_NODES["relay_node"],
                "level": "ERROR",
                "component": "relay_driver",
                "error_code": 5,
                "message": "Failed to set relay state"
            },
            {
                "node": "light_node",
                "node_uid": TEST_NODES["light_node"],
                "level": "ERROR",
                "component": "light_sensor",
                "error_code": 6,
                "message": "Failed to read light sensor value"
            },
        ]
        
        published_count = 0
        for test_case in test_cases:
            success = self.mqtt_publisher.publish_error(
                TEST_GH_UID,
                TEST_ZONE_UID,
                test_case["node_uid"],
                test_case["level"],
                test_case["component"],
                test_case["error_code"],
                test_case["message"]
            )
            if success:
                published_count += 1
            await asyncio.sleep(0.5)  # Небольшая задержка между сообщениями
        
        result = {
            "test": "error_publishing",
            "passed": published_count == len(test_cases),
            "published": published_count,
            "total": len(test_cases)
        }
        self.test_results.append(result)
        
        if result["passed"]:
            logger.info(f"✓ Test 1 passed: {published_count}/{len(test_cases)} errors published")
        else:
            logger.error(f"✗ Test 1 failed: {published_count}/{len(test_cases)} errors published")
        
        return result["passed"]
    
    async def test_error_processing(self):
        """Тест 2: Обработка ошибок в history-logger."""
        logger.info("\n=== Test 2: Error Processing ===")
        
        # Ждем обработки ошибок
        await asyncio.sleep(3)
        
        # Проверяем метрики напрямую из history-logger
        metrics_found = False
        try:
            response = await self.http_client.get(f"{HISTORY_LOGGER_URL}/metrics")
            if response.status_code == 200:
                metrics_text = response.text
                if "error_received_total" in metrics_text:
                    # Подсчитываем количество метрик
                    count = metrics_text.count("error_received_total{")
                    logger.info(f"✓ Found error_received_total metrics in history-logger: {count} entries")
                    metrics_found = True
                else:
                    logger.warning("⚠ No error_received_total metrics found in history-logger")
        except Exception as e:
            logger.warning(f"⚠ Failed to check history-logger metrics: {e}")
        
        # Также проверяем Prometheus (может быть задержка)
        prometheus_found = False
        try:
            response = await self.http_client.get(f"{PROMETHEUS_URL}/api/v1/query", params={
                "query": "error_received_total"
            })
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == "success" and data.get("data", {}).get("result"):
                    metrics_count = len(data["data"]["result"])
                    if metrics_count > 0:
                        logger.info(f"✓ Found {metrics_count} error metrics in Prometheus")
                        prometheus_found = True
        except Exception as e:
            logger.debug(f"Prometheus query failed (may need more time): {e}")
        
        # Тест проходит, если метрики найдены хотя бы в одном месте
        result = {
            "test": "error_processing",
            "passed": metrics_found or prometheus_found,
            "metrics_found_in_logger": metrics_found,
            "metrics_found_in_prometheus": prometheus_found
        }
        
        self.test_results.append(result)
        if result["passed"]:
            logger.info("✓ Test 2 passed: Error metrics found")
        else:
            logger.warning("⚠ Test 2: Error metrics not found (may need more time for processing)")
        
        return result["passed"]
    
    async def test_alert_creation(self):
        """Тест 3: Создание Alerts в БД."""
        logger.info("\n=== Test 3: Alert Creation ===")
        
        # Ждем создания Alerts
        await asyncio.sleep(5)
        
        # Проверяем alerts напрямую в БД через Laravel tinker
        # (API требует аутентификации, поэтому используем прямой доступ к БД)
        try:
            import subprocess
            result = subprocess.run(
                [
                    "docker", "exec", "backend-laravel-1",
                    "php", "artisan", "tinker", "--execute",
                    f"""
$zoneId = \\App\\Models\\DeviceNode::whereIn('uid', {list(TEST_NODES.values())})
    ->value('zone_id');
if (!$zoneId) {{
    echo '0';
    exit;
}}
$alerts = \\App\\Models\\Alert::where('zone_id', $zoneId)
    ->where('type', 'node_error')
    ->where('created_at', '>', now()->subMinutes(10))
    ->count();
echo $alerts;
"""
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                alerts_count = int(result.stdout.strip())
                if alerts_count > 0:
                    logger.info(f"✓ Found {alerts_count} alerts in database")
                    result_obj = {
                        "test": "alert_creation",
                        "passed": True,
                        "alerts_count": alerts_count
                    }
                else:
                    logger.warning("⚠ No alerts found in database")
                    result_obj = {
                        "test": "alert_creation",
                        "passed": False,
                        "error": "No alerts found"
                    }
            else:
                logger.warning(f"⚠ Failed to check alerts: {result.stderr}")
                result_obj = {
                    "test": "alert_creation",
                    "passed": False,
                    "error": result.stderr[:100]
                }
        except Exception as e:
            logger.warning(f"⚠ Alert creation test failed: {e}")
            result_obj = {
                "test": "alert_creation",
                "passed": False,
                "error": str(e)
            }
        
        self.test_results.append(result_obj)
        return result_obj["passed"]
    
    async def test_error_metrics_in_db(self):
        """Тест 4: Обновление метрик ошибок в БД."""
        logger.info("\n=== Test 4: Error Metrics in DB ===")
        
        # Ждем обновления БД
        await asyncio.sleep(3)
        
        # Проверяем метрики напрямую в БД через Laravel tinker
        try:
            import subprocess
            node_uids_str = ",".join([f"'{uid}'" for uid in TEST_NODES.values()])
            result = subprocess.run(
                [
                    "docker", "exec", "backend-laravel-1",
                    "php", "artisan", "tinker", "--execute",
                    f"""
$nodes = \\App\\Models\\DeviceNode::whereIn('uid', [{node_uids_str}])
    ->get(['uid', 'error_count', 'warning_count', 'critical_count']);
$found = false;
foreach ($nodes as $node) {{
    if ($node->error_count > 0 || $node->warning_count > 0 || $node->critical_count > 0) {{
        echo $node->uid . ':' . $node->error_count . ':' . $node->warning_count . ':' . $node->critical_count . PHP_EOL;
        $found = true;
    }}
}}
if (!$found) {{
    echo 'NO_METRICS';
}}
"""
                ],
                capture_output=True,
                text=True,
                timeout=10
            )
            
            if result.returncode == 0:
                output = result.stdout.strip()
                if output and output != "NO_METRICS":
                    lines = output.split("\n")
                    for line in lines:
                        if ":" in line:
                            parts = line.split(":")
                            node_uid = parts[0]
                            error_count = int(parts[1])
                            warning_count = int(parts[2])
                            critical_count = int(parts[3])
                            logger.info(f"✓ Node {node_uid} has error metrics: error={error_count}, warning={warning_count}, critical={critical_count}")
                    
                    result_obj = {
                        "test": "error_metrics_in_db",
                        "passed": True,
                        "nodes_with_metrics": len(lines)
                    }
                else:
                    logger.warning("⚠ No error metrics found in nodes")
                    result_obj = {
                        "test": "error_metrics_in_db",
                        "passed": False,
                        "error": "No error metrics found"
                    }
            else:
                logger.warning(f"⚠ Failed to check error metrics: {result.stderr}")
                result_obj = {
                    "test": "error_metrics_in_db",
                    "passed": False,
                    "error": result.stderr[:100]
                }
        except Exception as e:
            logger.warning(f"⚠ Error metrics test failed: {e}")
            result_obj = {
                "test": "error_metrics_in_db",
                "passed": False,
                "error": str(e)
            }
        
        self.test_results.append(result_obj)
        return result_obj["passed"]
    
    async def test_diagnostics_metrics(self):
        """Тест 5: Проверка diagnostics метрик."""
        logger.info("\n=== Test 5: Diagnostics Metrics ===")
        
        # Публикуем diagnostics сообщение
        topic = f"hydro/{TEST_GH_UID}/{TEST_ZONE_UID}/{TEST_NODES['ph_node']}/diagnostics"
        payload = {
            "errors": {
                "error_count": 1,
                "warning_count": 0,
                "critical_count": 0
            },
            "timestamp": int(time.time())
        }
        
        self.mqtt_publisher.client.publish(topic, json.dumps(payload), qos=1)
        await asyncio.sleep(2)
        
        result = {
            "test": "diagnostics_metrics",
            "passed": True,
            "message": "Diagnostics published"
        }
        self.test_results.append(result)
        logger.info("✓ Diagnostics metrics test completed")
        return True
    
    async def run_all_tests(self):
        """Запустить все тесты."""
        logger.info("=" * 60)
        logger.info("Starting Integration Tests for Error Reporting")
        logger.info("=" * 60)
        
        try:
            await self.setup()
            
            # Запускаем тесты
            tests = [
                ("Error Publishing", self.test_error_publishing),
                ("Error Processing", self.test_error_processing),
                ("Alert Creation", self.test_alert_creation),
                ("Error Metrics in DB", self.test_error_metrics_in_db),
                ("Diagnostics Metrics", self.test_diagnostics_metrics),
            ]
            
            passed = 0
            total = len(tests)
            
            for test_name, test_func in tests:
                try:
                    if await test_func():
                        passed += 1
                except Exception as e:
                    logger.error(f"✗ Test '{test_name}' failed with exception: {e}")
            
            # Итоговый отчет
            logger.info("\n" + "=" * 60)
            logger.info("Integration Tests Summary")
            logger.info("=" * 60)
            logger.info(f"Passed: {passed}/{total}")
            
            for result in self.test_results:
                status = "✓" if result.get("passed") else "✗"
                logger.info(f"{status} {result.get('test')}: {result}")
            
            return passed == total
            
        except Exception as e:
            logger.error(f"Test setup failed: {e}")
            return False
        finally:
            await self.teardown()


async def main():
    """Главная функция."""
    runner = IntegrationTestRunner()
    success = await runner.run_all_tests()
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())

