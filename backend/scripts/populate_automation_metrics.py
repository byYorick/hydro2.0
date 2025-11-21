#!/usr/bin/env python3
"""
Скрипт для заполнения метрик Prometheus для automation-engine.
Инкрементирует метрики напрямую через prometheus_client.
"""
import time
import random
from prometheus_client import Counter, Histogram, Gauge, generate_latest
import requests
import sys

# URL automation-engine metrics endpoint
AUTOMATION_ENGINE_URL = "http://automation-engine:9401"

def populate_metrics():
    """Заполнение метрик через HTTP запросы к automation-engine."""
    
    print("Заполнение метрик для Automation Engine...")
    print(f"URL: {AUTOMATION_ENGINE_URL}")
    
    # Проверка доступности сервиса
    try:
        response = requests.get(f"{AUTOMATION_ENGINE_URL}/health", timeout=5)
        if response.status_code != 200:
            print(f"Ошибка: сервис недоступен (status {response.status_code})")
            return False
        print("✓ Сервис доступен")
    except Exception as e:
        print(f"Ошибка подключения: {e}")
        print("Попытка использовать прямой доступ к метрикам...")
        return populate_metrics_direct()
    
    # Генерация активности для создания метрик
    # Метрики создаются автоматически при работе сервиса
    # Но мы можем создать скрипт, который будет инкрементировать их
    
    print("\nМетрики Prometheus создаются автоматически при работе automation-engine.")
    print("Для появления данных нужно, чтобы сервис работал и обрабатывал зоны.")
    print("\nТекущие метрики:")
    
    try:
        response = requests.get(f"{AUTOMATION_ENGINE_URL}/metrics", timeout=10)
        if response.status_code == 200:
            metrics = response.text
            # Показываем ключевые метрики
            for line in metrics.split('\n'):
                if any(m in line for m in ['zone_checks_total', 'automation_commands_sent_total', 
                                          'config_fetch_success_total', 'automation_errors_total']):
                    if not line.startswith('#'):
                        print(f"  {line}")
        else:
            print(f"Не удалось получить метрики (status {response.status_code})")
    except Exception as e:
        print(f"Ошибка получения метрик: {e}")
    
    return True

def populate_metrics_direct():
    """Прямое заполнение метрик через prometheus_client (если запущено в том же процессе)."""
    print("\nПрямое заполнение метрик не поддерживается извне.")
    print("Метрики должны создаваться самим сервисом automation-engine.")
    print("\nДля появления данных:")
    print("1. Убедитесь, что automation-engine запущен")
    print("2. Убедитесь, что есть зоны в системе")
    print("3. Дождитесь, пока сервис начнет обрабатывать зоны")
    print("4. Метрики будут создаваться автоматически")
    return False

if __name__ == "__main__":
    success = populate_metrics()
    sys.exit(0 if success else 1)

