#!/usr/bin/env python3
"""
Тест совместимости прошивки с эталоном node-sim.

Проверяет:
- Формат телеметрии
- Формат ответов на команды
- Формат heartbeat
- Формат статуса
- Формат ошибок (если есть)

Использование:
    python3 firmware/tests/test_node_compatibility.py --mqtt-host localhost --mqtt-port 1884
"""

import argparse
import json
import time
import paho.mqtt.client as mqtt
import jsonschema
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

# Пути к схемам
SCHEMAS_DIR = Path(__file__).parent.parent / "schemas"

# Цвета для вывода
GREEN = '\033[0;32m'
RED = '\033[0;31m'
YELLOW = '\033[1;33m'
NC = '\033[0m'  # No Color


@dataclass
class TestResult:
    """Результат теста."""
    __test__ = False
    name: str
    passed: bool
    message: str
    details: Optional[Dict] = None


class NodeCompatibilityTester:
    """Тестер совместимости прошивки с эталоном node-sim."""
    
    def __init__(self, mqtt_host: str = "localhost", mqtt_port: int = 1884):
        self.mqtt_host = mqtt_host
        self.mqtt_port = mqtt_port
        self.client = None
        self.results: List[TestResult] = []
        self.received_messages = {
            "telemetry": [],
            "command_response": [],
            "heartbeat": [],
            "status": [],
            "error": []
        }
        self.test_gh_uid = "gh-test-1"
        self.test_zone_uid = "zn-test-1"
        self.test_node_uid = "nd-test-001"
        
    def load_schema(self, schema_name: str) -> Dict:
        """Загрузить JSON схему."""
        schema_path = SCHEMAS_DIR / f"{schema_name}.schema.json"
        if not schema_path.exists():
            raise FileNotFoundError(f"Schema not found: {schema_path}")
        with open(schema_path) as f:
            return json.load(f)
    
    def validate_message(self, message: Dict, schema_name: str) -> tuple[bool, str]:
        """Валидировать сообщение по схеме."""
        try:
            schema = self.load_schema(schema_name)
            jsonschema.validate(instance=message, schema=schema)
            return True, "OK"
        except jsonschema.ValidationError as e:
            return False, f"Schema validation error: {e.message}"
        except Exception as e:
            return False, f"Error: {str(e)}"
    
    def on_connect(self, client, userdata, flags, rc):
        """Callback при подключении к MQTT."""
        if rc == 0:
            print(f"{GREEN}✅ Подключено к MQTT брокеру{NC}")
            
            # Подписка на все топики тестовой ноды
            topics = [
                f"hydro/{self.test_gh_uid}/{self.test_zone_uid}/{self.test_node_uid}/+/telemetry",
                f"hydro/{self.test_gh_uid}/{self.test_zone_uid}/{self.test_node_uid}/+/command_response",
                f"hydro/{self.test_gh_uid}/{self.test_zone_uid}/{self.test_node_uid}/heartbeat",
                f"hydro/{self.test_gh_uid}/{self.test_zone_uid}/{self.test_node_uid}/status",
                f"hydro/{self.test_gh_uid}/{self.test_zone_uid}/{self.test_node_uid}/error",
            ]
            
            for topic in topics:
                client.subscribe(topic, qos=1)
                print(f"  Подписка: {topic}")
        else:
            print(f"{RED}❌ Ошибка подключения к MQTT: {rc}{NC}")
    
    def on_message(self, client, userdata, msg):
        """Callback при получении сообщения."""
        try:
            payload = json.loads(msg.payload.decode('utf-8'))
            topic_parts = msg.topic.split('/')
            
            if len(topic_parts) >= 6:
                message_type = topic_parts[5]  # telemetry, command_response, heartbeat, status, error
                
                if message_type in self.received_messages:
                    self.received_messages[message_type].append({
                        "topic": msg.topic,
                        "payload": payload,
                        "timestamp": time.time()
                    })
                    print(f"{GREEN}📨 Получено: {message_type}{NC}")
                    print(f"   Топик: {msg.topic}")
                    print(f"   Payload: {json.dumps(payload, indent=2)}")
        except Exception as e:
            print(f"{RED}❌ Ошибка обработки сообщения: {e}{NC}")
    
    def connect(self):
        """Подключиться к MQTT брокеру."""
        self.client = mqtt.Client()
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message
        
        try:
            self.client.connect(self.mqtt_host, self.mqtt_port, 60)
            self.client.loop_start()
            time.sleep(2)  # Даем время на подключение
            return True
        except Exception as e:
            print(f"{RED}❌ Ошибка подключения: {e}{NC}")
            return False
    
    def disconnect(self):
        """Отключиться от MQTT брокера."""
        if self.client:
            self.client.loop_stop()
            self.client.disconnect()
    
    def test_telemetry_format(self) -> TestResult:
        """Тест формата телеметрии."""
        print(f"\n{YELLOW}Тест: Формат телеметрии{NC}")
        
        # Ждем получения телеметрии
        time.sleep(8)
        
        if not self.received_messages["telemetry"]:
            return TestResult(
                "telemetry_format",
                False,
                "Телеметрия не получена"
            )
        
        telemetry = self.received_messages["telemetry"][0]["payload"]
        
        # Проверка обязательных полей
        required_fields = ["metric_type", "value", "ts"]
        missing_fields = [f for f in required_fields if f not in telemetry]
        if missing_fields:
            return TestResult(
                "telemetry_format",
                False,
                f"Отсутствуют обязательные поля: {missing_fields}"
            )
        
        # Проверка запрещенных полей
        forbidden_fields = ["node_id", "channel"]
        present_forbidden = [f for f in forbidden_fields if f in telemetry]
        if present_forbidden:
            return TestResult(
                "telemetry_format",
                False,
                f"Присутствуют запрещенные поля: {present_forbidden}"
            )
        
        # Проверка формата metric_type (UPPERCASE)
        if telemetry["metric_type"] != telemetry["metric_type"].upper():
            return TestResult(
                "telemetry_format",
                False,
                f"metric_type должен быть в UPPERCASE, получен: {telemetry['metric_type']}"
            )
        
        # Проверка типа ts (должен быть int)
        if isinstance(telemetry["ts"], float):
            return TestResult(
                "telemetry_format",
                False,
                f"ts должен быть integer, получен float: {telemetry['ts']}"
            )
        
        # Валидация по схеме
        is_valid, error_msg = self.validate_message(telemetry, "telemetry")
        if not is_valid:
            return TestResult(
                "telemetry_format",
                False,
                error_msg
            )
        
        return TestResult(
            "telemetry_format",
            True,
            "Формат телеметрии соответствует эталону",
            {"sample": telemetry}
        )
    
    def test_command_response_format(self) -> TestResult:
        """Тест формата ответов на команды."""
        print(f"\n{YELLOW}Тест: Формат ответов на команды{NC}")
        
        # Отправляем тестовую команду
        cmd_id = f"test-cmd-{int(time.time())}"
        command_topic = f"hydro/{self.test_gh_uid}/{self.test_zone_uid}/{self.test_node_uid}/ph_sensor/command"
        command = {
            "cmd_id": cmd_id,
            "cmd": "set_relay_state",
            "params": {
                "state": True,
                "channel": "ph_sensor"
            }
        }
        
        self.client.publish(command_topic, json.dumps(command), qos=1)
        print(f"  Отправлена команда: {cmd_id}")
        
        # Ждем ответа
        time.sleep(3)
        
        if not self.received_messages["command_response"]:
            return TestResult(
                "command_response_format",
                False,
                "Ответ на команду не получен"
            )
        
        # Ищем ответ с нашим cmd_id
        response = None
        for msg in self.received_messages["command_response"]:
            if msg["payload"].get("cmd_id") == cmd_id:
                response = msg["payload"]
                break
        
        if not response:
            return TestResult(
                "command_response_format",
                False,
                f"Ответ с cmd_id={cmd_id} не найден"
            )
        
        # Проверка обязательных полей
        required_fields = ["cmd_id", "status", "ts"]
        missing_fields = [f for f in required_fields if f not in response]
        if missing_fields:
            return TestResult(
                "command_response_format",
                False,
                f"Отсутствуют обязательные поля: {missing_fields}"
            )
        
        # Проверка cmd_id (должен точно соответствовать команде)
        if response["cmd_id"] != cmd_id:
            return TestResult(
                "command_response_format",
                False,
                f"cmd_id не соответствует команде: ожидалось {cmd_id}, получено {response['cmd_id']}"
            )
        
        # Проверка ts (должен быть в миллисекундах - большое число)
        ts = response["ts"]
        if isinstance(ts, (int, float)) and ts < 1000000000000:
            return TestResult(
                "command_response_format",
                False,
                f"ts похож на секунды, ожидаются миллисекунды: {ts}"
            )
        
        # Валидация по схеме
        is_valid, error_msg = self.validate_message(response, "command_response")
        if not is_valid:
            return TestResult(
                "command_response_format",
                False,
                error_msg
            )
        
        return TestResult(
            "command_response_format",
            True,
            "Формат ответа на команду соответствует эталону",
            {"sample": response}
        )
    
    def test_heartbeat_format(self) -> TestResult:
        """Тест формата heartbeat."""
        print(f"\n{YELLOW}Тест: Формат heartbeat{NC}")
        
        # Ждем получения heartbeat
        time.sleep(20)
        
        if not self.received_messages["heartbeat"]:
            return TestResult(
                "heartbeat_format",
                False,
                "Heartbeat не получен"
            )
        
        heartbeat = self.received_messages["heartbeat"][0]["payload"]
        
        # Проверка обязательных полей
        required_fields = ["uptime", "free_heap"]
        missing_fields = [f for f in required_fields if f not in heartbeat]
        if missing_fields:
            return TestResult(
                "heartbeat_format",
                False,
                f"Отсутствуют обязательные поля: {missing_fields}"
            )
        
        # Проверка запрещенных полей
        if "ts" in heartbeat:
            return TestResult(
                "heartbeat_format",
                False,
                "Поле 'ts' не должно присутствовать в heartbeat"
            )
        
        # Проверка uptime (должен быть в секундах, не миллисекундах)
        uptime = heartbeat["uptime"]
        if isinstance(uptime, (int, float)) and uptime > 1000000:
            return TestResult(
                "heartbeat_format",
                False,
                f"uptime похож на миллисекунды, ожидаются секунды: {uptime}"
            )
        
        # Валидация по схеме
        is_valid, error_msg = self.validate_message(heartbeat, "heartbeat")
        if not is_valid:
            return TestResult(
                "heartbeat_format",
                False,
                error_msg
            )
        
        return TestResult(
            "heartbeat_format",
            True,
            "Формат heartbeat соответствует эталону",
            {"sample": heartbeat}
        )
    
    def test_status_format(self) -> TestResult:
        """Тест формата статуса."""
        print(f"\n{YELLOW}Тест: Формат статуса{NC}")
        
        # Ждем получения статуса
        time.sleep(5)
        
        if not self.received_messages["status"]:
            return TestResult(
                "status_format",
                False,
                "Статус не получен"
            )
        
        status = self.received_messages["status"][0]["payload"]
        
        # Проверка обязательных полей
        required_fields = ["status", "ts"]
        missing_fields = [f for f in required_fields if f not in status]
        if missing_fields:
            return TestResult(
                "status_format",
                False,
                f"Отсутствуют обязательные поля: {missing_fields}"
            )
        
        # Проверка значения status
        if status["status"] not in ["ONLINE", "OFFLINE"]:
            return TestResult(
                "status_format",
                False,
                f"Неверное значение status: {status['status']}, ожидается ONLINE или OFFLINE"
            )
        
        # Проверка типа ts (должен быть int, секунды)
        if isinstance(status["ts"], float):
            return TestResult(
                "status_format",
                False,
                f"ts должен быть integer, получен float: {status['ts']}"
            )
        
        # Валидация по схеме
        is_valid, error_msg = self.validate_message(status, "status")
        if not is_valid:
            return TestResult(
                "status_format",
                False,
                error_msg
            )
        
        return TestResult(
            "status_format",
            True,
            "Формат статуса соответствует эталону",
            {"sample": status}
        )
    
    def run_all_tests(self) -> List[TestResult]:
        """Запустить все тесты."""
        print("=" * 60)
        print("ТЕСТИРОВАНИЕ СОВМЕСТИМОСТИ С ЭТАЛОНОМ NODE-SIM")
        print("=" * 60)
        print()
        
        # Подключение к MQTT
        if not self.connect():
            return [TestResult("connection", False, "Не удалось подключиться к MQTT")]
        
        # Запуск тестов
        tests = [
            self.test_status_format,
            self.test_telemetry_format,
            self.test_command_response_format,
            self.test_heartbeat_format,
        ]
        
        for test_func in tests:
            try:
                result = test_func()
                self.results.append(result)
            except Exception as e:
                self.results.append(TestResult(
                    test_func.__name__,
                    False,
                    f"Ошибка выполнения теста: {str(e)}"
                ))
        
        # Отключение
        self.disconnect()
        
        return self.results
    
    def print_results(self):
        """Вывести результаты тестов."""
        print("\n" + "=" * 60)
        print("РЕЗУЛЬТАТЫ ТЕСТИРОВАНИЯ")
        print("=" * 60)
        print()
        
        passed = 0
        failed = 0
        
        for result in self.results:
            if result.passed:
                print(f"{GREEN}✅ {result.name}: {result.message}{NC}")
                passed += 1
            else:
                print(f"{RED}❌ {result.name}: {result.message}{NC}")
                if result.details:
                    print(f"   Детали: {result.details}")
                failed += 1
        
        print()
        print("=" * 60)
        print(f"Успешно: {GREEN}{passed}{NC}")
        print(f"Ошибок: {RED}{failed}{NC}")
        print("=" * 60)
        
        return failed == 0


def main():
    parser = argparse.ArgumentParser(description="Тест совместимости прошивки с эталоном node-sim")
    parser.add_argument("--mqtt-host", default="localhost", help="MQTT хост")
    parser.add_argument("--mqtt-port", type=int, default=1884, help="MQTT порт")
    parser.add_argument("--gh-uid", default="gh-test-1", help="UID теплицы")
    parser.add_argument("--zone-uid", default="zn-test-1", help="UID зоны")
    parser.add_argument("--node-uid", default="nd-test-001", help="UID ноды")
    
    args = parser.parse_args()
    
    tester = NodeCompatibilityTester(args.mqtt_host, args.mqtt_port)
    tester.test_gh_uid = args.gh_uid
    tester.test_zone_uid = args.zone_uid
    tester.test_node_uid = args.node_uid
    
    results = tester.run_all_tests()
    success = tester.print_results()
    
    exit(0 if success else 1)


if __name__ == "__main__":
    main()
