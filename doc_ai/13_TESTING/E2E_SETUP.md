# E2E Test Setup - Настройка End-to-End тестового контура

## Быстрый старт

### 1. Запуск E2E окружения

```bash
./tools/testing/run_e2e.sh
```

Скрипт автоматически:
- Поднимает все сервисы через Docker Compose
- Дожидается readiness всех компонентов
- Запускает миграции и seeders
- Прогоняет все обязательные сценарии
- Генерирует отчеты

### 2. Структура E2E контура

```
tests/e2e/
├── docker-compose.e2e.yml    # Docker Compose конфигурация
├── .env.e2e.example          # Пример переменных окружения
├── node-sim-config.yaml      # Конфигурация node-sim
├── runner/                   # E2E runner (Python)
│   ├── e2e_runner.py        # Главный раннер
│   ├── api_client.py        # HTTP клиент
│   ├── ws_client.py          # WebSocket клиент
│   ├── db_probe.py          # Проверки БД
│   ├── mqtt_probe.py        # Проверки MQTT
│   ├── assertions.py         # Assertions
│   └── reporting.py         # Генерация отчетов
├── scenarios/                # YAML сценарии (по категориям)
│   ├── core/
│   ├── commands/
│   ├── alerts/
│   ├── snapshot/
│   ├── infrastructure/
│   ├── grow_cycle/
│   ├── automation_engine/
│   └── chaos/
└── reports/                  # Отчеты (JUnit XML, JSON timeline)
```

### 3. Обязательные сценарии (DoD)

Минимальный P0 набор (smoke):
| Код | Сценарий | DoD |
|-----|----------|-----|
| E01 | core/E01_bootstrap | telemetry в БД + online статус |
| E10 | commands/E10_command_happy | команда → DONE + WS событие |

Полный список сценариев и DoD: `E2E_SCENARIOS.md`.

### 4. Инварианты пайплайна

#### Команды
- Статусы: `QUEUED → SENT → ACCEPTED → DONE/FAILED/TIMEOUT`
- Без откатов (монотонность)
- Идемпотентность по `cmd_id`

#### Ошибки
- Либо `alerts`
- Либо `unassigned_node_errors`
- Либо `DLQ`
- Ничего не теряется

#### Realtime
- Каждое событие имеет `event_id`
- Reconnect: snapshot содержит `last_event_id`
- `/events?after_id` догоняет gap

### 5. Компоненты системы

#### Сервисы (docker-compose.e2e.yml)
- `postgres` - TimescaleDB
- `redis` - Redis для очередей
- `mosquitto` - MQTT брокер
- `laravel` - Laravel приложение + Reverb (WebSocket)
- `history-logger` - Обработка телеметрии
- `mqtt-bridge` - HTTP → MQTT мост
- `telemetry-aggregator` - Агрегация телеметрии
- `automation-engine` - Автоматизация (опционально)
- `node-sim` - Эмулятор ноды

#### Node Simulator (node-sim)
- Поддержка `normal` и `temp` (preconfig) топиков
- Публикация: telemetry, status, heartbeat, error
- Прием команд и ответы: ACCEPTED → DONE/FAILED
- Идемпотентность по `cmd_id` (LRU cache)
- Режимы отказов: overcurrent, no_flow, duplicate response, delayed response

### 6. Отчеты

После выполнения тестов генерируются:
- `tests/e2e/reports/junit.xml` - JUnit XML для CI/CD
- `tests/e2e/reports/timeline.json` - Детальная timeline с WS/MQTT/SQL событиями

### 7. Отладка

#### Просмотр логов
```bash
docker compose -f tests/e2e/docker-compose.e2e.yml logs laravel
docker compose -f tests/e2e/docker-compose.e2e.yml logs history-logger
docker compose -f tests/e2e/docker-compose.e2e.yml logs node-sim
```

#### Проверка БД
```bash
docker compose -f tests/e2e/docker-compose.e2e.yml exec postgres psql -U hydro -d hydro_e2e
```

#### Проверка MQTT
```bash
docker compose -f tests/e2e/docker-compose.e2e.yml exec mosquitto mosquitto_sub -h localhost -t "#" -v
```

### 8. Автофикс до GREEN

Скрипт `run_e2e.sh` запускает все сценарии и выводит результаты.
При падении теста:
1. Проверьте отчеты в `tests/e2e/reports/`
2. Изучите timeline.json для понимания последовательности событий
3. Проверьте логи сервисов
4. Исправьте ошибку в коде
5. Повторите запуск

### 9. Переменные окружения

Создайте `tests/e2e/.env.e2e` на основе `.env.e2e.example` для переопределения настроек.

### 10. Требования

- Docker и Docker Compose (docker compose или docker-compose)
- Python 3.11+ с зависимостями из `tests/e2e/requirements.txt`
- Доступ к портам: 5433 (Postgres), 6380 (Redis), 1884 (MQTT), 8081 (Laravel), 6002 (Reverb)
