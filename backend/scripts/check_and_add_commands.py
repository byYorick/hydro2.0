#!/usr/bin/env python3
import sys
sys.path.insert(0, '/app')

from infrastructure.command_bus import COMMANDS_SENT
from prometheus_client import generate_latest
import random
import httpx

# Добавляем команды
print("Добавляю команды...")
for _ in range(5000):
    zone_id = random.choice([1, 2, 3, 4, 5])
    metric = random.choice(['PH', 'EC', 'TEMPERATURE', 'HUMIDITY'])
    COMMANDS_SENT.labels(zone_id=zone_id, metric=metric).inc()

print(f"Добавлено 5000 команд")

# Проверяем через generate_latest
metrics_text = generate_latest().decode('utf-8')
cmd_lines = [l for l in metrics_text.split('\n') if 'automation_commands_sent_total' in l and not l.startswith('#') and l.strip()]
print(f"\nВ generate_latest(): {len(cmd_lines)} строк с данными")
if cmd_lines:
    print("Примеры:")
    print('\n'.join(cmd_lines[:5]))
    total = sum(float(l.split()[-1]) for l in cmd_lines if l.strip())
    print(f"Сумма всех команд: {total}")

# Проверяем через /metrics endpoint
print("\nПроверяю /metrics endpoint...")
try:
    r = httpx.get('http://localhost:9401/metrics', timeout=5)
    if r.status_code == 200:
        endpoint_lines = [l for l in r.text.split('\n') if 'automation_commands_sent_total' in l and not l.startswith('#') and l.strip()]
        print(f"В /metrics endpoint: {len(endpoint_lines)} строк с данными")
        if endpoint_lines:
            print("Примеры:")
            print('\n'.join(endpoint_lines[:5]))
        else:
            print("⚠️ В /metrics endpoint нет данных (только HELP и TYPE)")
    else:
        print(f"Ошибка HTTP: {r.status_code}")
except Exception as e:
    print(f"Ошибка: {e}")

print("\n✓ Проверка завершена")
