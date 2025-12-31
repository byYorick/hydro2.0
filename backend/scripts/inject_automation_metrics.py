#!/usr/bin/env python3
"""
Скрипт для инъекции тестовых метрик в automation-engine через прямое обращение к prometheus_client.
Запускается внутри контейнера automation-engine.
"""
import sys
import os
sys.path.insert(0, '/app')

# Импортируем метрики из automation-engine
try:
    from services.zone_automation_service import ZONE_CHECKS, CHECK_LAT
    from infrastructure.command_bus import COMMANDS_SENT
    from main import CONFIG_FETCH_SUCCESS, CONFIG_FETCH_ERRORS, LOOP_ERRORS
    from error_handler import ERROR_COUNTER
    from infrastructure.command_bus import MQTT_PUBLISH_ERRORS
except ImportError as e:
    print(f"Ошибка импорта: {e}")
    print("Скрипт должен запускаться внутри контейнера automation-engine")
    sys.exit(1)

import random
import time

def inject_test_metrics():
    """Инъекция тестовых метрик."""
    print("Инъекция тестовых метрик для Automation Engine...")
    
    # Генерируем данные для zone_checks_total
    print("\n1. Генерация zone_checks_total...")
    for i in range(50):
        ZONE_CHECKS.inc()
        # Добавляем случайную задержку для histogram
        duration = random.uniform(0.01, 0.5)
        CHECK_LAT.observe(duration)
    print(f"   ✓ Добавлено 50 проверок зон")
    
    # Генерируем данные для automation_commands_sent_total
    print("\n2. Генерация automation_commands_sent_total...")
    zone_ids = [1, 2, 3, 4, 5]
    metrics = ['PH', 'EC', 'TEMPERATURE', 'HUMIDITY']
    for i in range(100):
        zone_id = random.choice(zone_ids)
        metric = random.choice(metrics)
        COMMANDS_SENT.labels(zone_id=zone_id, metric=metric).inc()
    print(f"   ✓ Добавлено 100 команд")
    
    # Генерируем данные для config_fetch_success_total
    print("\n3. Генерация config_fetch_success_total...")
    for i in range(30):
        CONFIG_FETCH_SUCCESS.inc()
    print(f"   ✓ Добавлено 30 успешных загрузок конфигурации")
    
    # Генерируем несколько ошибок
    print("\n4. Генерация ошибок...")
    for i in range(5):
        CONFIG_FETCH_ERRORS.labels(error_type="timeout").inc()
    for i in range(3):
        LOOP_ERRORS.labels(error_type="config_error").inc()
    for i in range(2):
        MQTT_PUBLISH_ERRORS.labels(error_type="connection_error").inc()
    print(f"   ✓ Добавлено несколько ошибок")
    
    print("\n✓ Метрики успешно инъектированы!")
    print("\nПроверьте dashboard Automation Engine - данные должны появиться.")

if __name__ == "__main__":
    inject_test_metrics()
