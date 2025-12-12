"""
Генерация отчетов для E2E тестов: JUnit XML, JSON timeline, артефакты.
"""

import json
import logging
import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)


class TestReporter:
    """Генератор отчетов для E2E тестов."""
    
    def __init__(self, output_dir: str = "tests/e2e/reports"):
        """
        Инициализация репортера.
        
        Args:
            output_dir: Директория для сохранения отчетов
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        self.test_suite_name = "E2E Tests"
        self.test_cases: List[Dict[str, Any]] = []
        self.timeline: List[Dict[str, Any]] = []
        self.artifacts: Dict[str, Any] = {}
    
    def add_test_case(
        self,
        name: str,
        status: str,
        duration: float,
        error_message: Optional[str] = None,
        steps: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Добавить тест-кейс в отчет.
        
        Args:
            name: Имя тест-кейса
            status: Статус (passed, failed, skipped)
            duration: Длительность в секундах
            error_message: Сообщение об ошибке (если есть)
            steps: Список шагов теста
        """
        test_case = {
            "name": name,
            "status": status,
            "duration": duration,
            "error_message": error_message,
            "steps": steps or [],
            "timestamp": datetime.now().isoformat()
        }
        self.test_cases.append(test_case)
    
    def add_timeline_event(
        self,
        event_type: str,
        description: str,
        data: Optional[Dict[str, Any]] = None
    ):
        """
        Добавить событие в timeline.
        
        Args:
            event_type: Тип события (api_call, ws_event, db_query, etc.)
            description: Описание события
            data: Дополнительные данные события
        """
        event = {
            "timestamp": datetime.now().isoformat(),
            "type": event_type,
            "description": description,
            "data": data or {}
        }
        self.timeline.append(event)
    
    def add_artifacts(
        self,
        name: str,
        ws_messages: Optional[List[Dict[str, Any]]] = None,
        mqtt_messages: Optional[List[Dict[str, Any]]] = None,
        api_responses: Optional[List[Dict[str, Any]]] = None
    ):
        """
        Добавить артефакты (последние сообщения).
        
        Args:
            name: Имя артефакта (обычно имя теста)
            ws_messages: Последние WebSocket сообщения
            mqtt_messages: Последние MQTT сообщения
            api_responses: Последние API ответы
        """
        self.artifacts[name] = {
            "ws_messages": (ws_messages or [])[-50:],  # Последние 50
            "mqtt_messages": (mqtt_messages or [])[-50:],  # Последние 50
            "api_responses": (api_responses or [])[-50:]  # Последние 50
        }
    
    def generate_junit_xml(self, filename: str = "junit.xml") -> str:
        """
        Сгенерировать JUnit XML отчет.
        
        Args:
            filename: Имя файла для сохранения
            
        Returns:
            Путь к созданному файлу
        """
        testsuites = ET.Element("testsuites")
        testsuites.set("name", self.test_suite_name)
        testsuites.set("tests", str(len(self.test_cases)))
        
        passed = sum(1 for tc in self.test_cases if tc["status"] == "passed")
        failed = sum(1 for tc in self.test_cases if tc["status"] == "failed")
        skipped = sum(1 for tc in self.test_cases if tc["status"] == "skipped")
        
        testsuites.set("failures", str(failed))
        testsuites.set("skipped", str(skipped))
        testsuites.set("time", str(sum(tc["duration"] for tc in self.test_cases)))
        
        testsuite = ET.SubElement(testsuites, "testsuite")
        testsuite.set("name", self.test_suite_name)
        testsuite.set("tests", str(len(self.test_cases)))
        testsuite.set("failures", str(failed))
        testsuite.set("skipped", str(skipped))
        testsuite.set("time", str(sum(tc["duration"] for tc in self.test_cases)))
        
        for test_case in self.test_cases:
            testcase = ET.SubElement(testsuite, "testcase")
            testcase.set("name", test_case["name"])
            testcase.set("time", str(test_case["duration"]))
            
            if test_case["status"] == "failed":
                failure = ET.SubElement(testcase, "failure")
                failure.set("message", test_case.get("error_message", "Test failed"))
                failure.text = test_case.get("error_message", "")
            elif test_case["status"] == "skipped":
                skipped_elem = ET.SubElement(testcase, "skipped")
                skipped_elem.text = test_case.get("error_message", "")
        
        filepath = self.output_dir / filename
        tree = ET.ElementTree(testsuites)
        tree.write(filepath, encoding="utf-8", xml_declaration=True)
        
        logger.info(f"Generated JUnit XML report: {filepath}")
        return str(filepath)
    
    def generate_json_timeline(self, filename: str = "timeline.json") -> str:
        """
        Сгенерировать JSON timeline отчет.
        
        Args:
            filename: Имя файла для сохранения
            
        Returns:
            Путь к созданному файлу
        """
        report = {
            "test_suite": self.test_suite_name,
            "generated_at": datetime.now().isoformat(),
            "test_cases": self.test_cases,
            "timeline": self.timeline,
            "artifacts": self.artifacts
        }
        
        filepath = self.output_dir / filename
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"Generated JSON timeline report: {filepath}")
        return str(filepath)
    
    def generate_all(self) -> Dict[str, str]:
        """
        Сгенерировать все отчеты.
        
        Returns:
            Словарь с путями к созданным файлам
        """
        return {
            "junit_xml": self.generate_junit_xml(),
            "timeline_json": self.generate_json_timeline()
        }

