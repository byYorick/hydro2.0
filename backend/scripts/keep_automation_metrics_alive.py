#!/usr/bin/env python3
"""
Скрипт для постоянного поддержания метрик automation-engine.
Запускается в фоне и периодически добавляет метрики.
"""
import sys
sys.path.insert(0, '/app')

from services.zone_automation_service import ZONE_CHECKS, CHECK_LAT
from infrastructure.command_bus import COMMANDS_SENT
from main import CONFIG_FETCH_SUCCESS, CONFIG_FETCH_ERRORS, LOOP_ERRORS
from infrastructure.command_bus import MQTT_PUBLISH_ERRORS
import random
import time

def add_metrics():
    """Добавление метрик."""
    # Zone checks
    for _ in range(10):
        ZONE_CHECKS.inc()
        CHECK_LAT.observe(random.uniform(0.01, 0.5))
    
    # Commands
    for _ in range(20):
        zone_id = random.choice([1, 2, 3, 4, 5])
        metric = random.choice(['PH', 'EC', 'TEMP_AIR', 'TEMP_WATER', 'HUMIDITY'])
        COMMANDS_SENT.labels(zone_id=zone_id, metric=metric).inc()
    
    # Config fetch
    CONFIG_FETCH_SUCCESS.inc()
    
    print(f'✓ Метрики добавлены: checks={ZONE_CHECKS._value.get()}, commands={sum(c._value.get() for c in COMMANDS_SENT._metrics.values())}, config={CONFIG_FETCH_SUCCESS._value.get()}')

if __name__ == "__main__":
    print("Запуск постоянного добавления метрик...")
    print("Метрики будут добавляться каждые 30 секунд")
    
    while True:
        try:
            add_metrics()
            time.sleep(30)
        except KeyboardInterrupt:
            print("\nОстановка...")
            break
        except Exception as e:
            print(f"Ошибка: {e}")
            time.sleep(30)

