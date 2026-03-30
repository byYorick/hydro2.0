# E2E Test Suite - End-to-End тестовый контур

Полностью рабочий, воспроизводимый end-to-end тестовый контур с эмулятором нод и автоисправлением ошибок до состояния GREEN.

## Быстрый старт

### 1. Подготовка окружения

```bash
# Перейти в директорию E2E тестов
cd tests/e2e

# Создать файл .env.e2e на основе примера
cp .env.e2e.example .env.e2e

# Отредактировать .env.e2e при необходимости
# (по умолчанию значения должны работать)
```

### 2. Запуск инфраструктуры

```bash
# Использовать скрипт из корня проекта
./tools/testing/run_e2e.sh up

# Или напрямую через docker compose (или docker-compose)
docker compose -f tests/e2e/docker-compose.e2e.yml up -d
```

### 3. Запуск тестов

```bash
# Запуск всех обязательных сценариев
./tools/testing/run_e2e.sh test

# Или напрямую через Python
cd tests/e2e
python3 -m runner.e2e_runner scenarios/core/E01_bootstrap.yaml
```

## Структура проекта

```
tests/e2e/
├── docker-compose.e2e.yml    # Docker Compose конфигурация для E2E окружения
├── .env.e2e.example          # Пример переменных окружения
├── mosquitto.e2e.conf        # Конфигурация MQTT брокера
├── node-sim-config.yaml      # Конфигурация node-sim для E2E
├── requirements.txt          # Python зависимости для runner
├── runner/                   # E2E test runner
│   ├── e2e_runner.py         # Главный раннер
│   ├── api_client.py         # HTTP клиент для Laravel API
│   ├── ws_client.py          # WebSocket клиент для Reverb
│   ├── db_probe.py           # Проверки базы данных
│   ├── mqtt_probe.py         # Проверки MQTT
│   ├── assertions.py         # Кастомные assertions
│   └── reporting.py          # Генерация отчетов
├── scenarios/                # YAML сценарии тестов
│   ├── core/
│   ├── commands/
│   ├── alerts/
│   ├── snapshot/
│   ├── infrastructure/
│   ├── grow_cycle/
│   ├── automation_engine/
│   └── chaos/
└── reports/                 # Отчеты (генерируются автоматически)
    ├── junit.xml
    └── timeline.json
```

## Обязательные сценарии

Минимальный P0 набор (используется в smoke):
- `scenarios/core/E01_bootstrap.yaml` — telemetry в БД + ONLINE статус
- `scenarios/commands/E10_command_happy.yaml` — команда → DONE + WS + zone_events

Полный список сценариев и DoD: `../../docs/testing/E2E_SCENARIOS.md`.

## Инварианты пайплайна

### Команды
Статусы должны изменяться монотонно:
```
QUEUED → SENT → ACK → DONE/NO_EFFECT/ERROR/INVALID/BUSY/TIMEOUT
```
❌ Без откатов

### Ошибки
Ошибки должны быть обработаны одним из способов:
- alerts
- unassigned_node_errors
- DLQ

Ничего не теряется.

### Realtime
- Каждое событие имеет event_id
- Reconnect: snapshot содержит last_event_id
- `/events?after_id` догоняет gap

## Использование скрипта run_e2e.sh

```bash
# Запуск инфраструктуры
./tools/testing/run_e2e.sh up

# Остановка инфраструктуры
./tools/testing/run_e2e.sh down

# Перезапуск инфраструктуры
./tools/testing/run_e2e.sh restart

# Запуск тестов (требует запущенной инфраструктуры)
./tools/testing/run_e2e.sh test

# Полный цикл: запуск инфраструктуры + тесты
./tools/testing/run_e2e.sh all

# Просмотр логов
./tools/testing/run_e2e.sh logs [service_name]

# Очистка данных
./tools/testing/run_e2e.sh clean
```

## Запуск на реальной ноде

Для прогона на реальной ESP32-ноде используйте:

```bash
# Показать, какие сценарии будут запущены
tests/e2e/run_automation_engine_real_hardware.sh --set=full --list

# Каноничный AE3-Lite two-tank smoke на реальной test-node
tests/e2e/run_automation_engine_real_hardware.sh --set=ae3lite

# Полный real-hardware набор
tests/e2e/run_automation_engine_real_hardware.sh --set=full
```

По умолчанию `SCENARIO_SET=full`. Wrapper прогоняет все real-hardware entrypoints
из `automation_engine/`, `workflow/` и `ae3lite/`. Исторические имена наборов при этом
остаются отдельными YAML-файлами, но могут быть явно портированы на каноничные
AE3 сценарии через `scenario_ref` внутри самих файлов.

Ключевые AE3 real-hardware сценарии:

- `E101_ae3_two_tank_realhw_setup_ready` — каноничный end-to-end путь до `workflow_phase=ready`; именно этот тест доводит систему до состояния, где реальный полив разрешён.
- `E101_ae3_two_tank_realhw_ready_during_fill` — альтернативный happy-path, где `ready` достигается ещё на fill-path.
- `E103_ae3_recirculation_retry_limit_alert_resolve_ready_realhw` — recovery-сценарий, который после retry-limit снова доводит систему до `ready`.
- `E104_ae3_two_tank_realhw_hot_reload_correction_config` — strict hot-reload test активного correction loop; он проверяет, что pH/EC реально сходятся к target после live reconfiguration, но сам по себе не является каноничным тестом “полив разрешён”.
- `E106_ae3_two_tank_realhw_piggyback_ec_ph_cycle` — strict sequential observe-loop test в `prepare_recirculation_check`; перед recirculation-loop сценарий детерминированно seed-ит раствор вне target window, затем требует порядка `EC -> observe -> PH`, проверяет delayed peak/decay на telemetry samples и строгий выход pH/EC в target, но не финальный выход в `ready`.

Опциональные фильтры:

```bash
# Включать только сценарии по regex
E2E_SCENARIO_INCLUDE_REGEX='scenarios/(workflow|automation_engine)/' \
  tests/e2e/run_automation_engine_real_hardware.sh --set=full

# Исключать сценарии по regex
E2E_SCENARIO_EXCLUDE_REGEX='scenarios/chaos/' \
  tests/e2e/run_automation_engine_real_hardware.sh --set=full
```

## Отчеты

После выполнения тестов генерируются отчеты:

- **JUnit XML** (`reports/junit.xml`) - для CI/CD систем
- **JSON Timeline** (`reports/timeline.json`) - детальная информация о выполнении

JSON Timeline содержит:
- Все WebSocket сообщения (последние 50)
- Все MQTT сообщения (последние 50)
- Все API запросы и ответы
- Временные метки всех событий
- Результаты проверок

## Отладка

### Просмотр логов сервисов

```bash
# Все сервисы
docker compose -f tests/e2e/docker-compose.e2e.yml logs -f

# Конкретный сервис
docker compose -f tests/e2e/docker-compose.e2e.yml logs -f laravel
docker compose -f tests/e2e/docker-compose.e2e.yml logs -f history-logger
docker compose -f tests/e2e/docker-compose.e2e.yml logs -f node-sim
```

### Проверка состояния сервисов

```bash
# Статус всех сервисов
docker compose -f tests/e2e/docker-compose.e2e.yml ps

# Health check Laravel
curl http://localhost:8081/api/system/health

# Health check history-logger
curl http://localhost:9302/health
```

### Проверка базы данных

```bash
# Подключение к БД
docker compose -f tests/e2e/docker-compose.e2e.yml exec postgres psql -U hydro -d hydro_e2e

# Проверка таблиц
\dt

# Проверка команд
SELECT * FROM commands ORDER BY created_at DESC LIMIT 10;

# Проверка телеметрии
SELECT * FROM telemetry_last ORDER BY updated_at DESC LIMIT 10;
```

### Проверка MQTT

```bash
# Подписка на все топики
docker compose -f tests/e2e/docker-compose.e2e.yml exec mosquitto mosquitto_sub -h localhost -p 1883 -t "#" -v
```

## Требования

- Docker и Docker Compose
- Python 3.8+
- Доступные порты: 8081 (Laravel), 6002 (Reverb), 1884 (MQTT), 5433 (PostgreSQL), 6380 (Redis)

## Troubleshooting

### Сервисы не запускаются

1. Проверьте, что все порты свободны
2. Проверьте логи: `./tools/testing/run_e2e.sh logs`
3. Проверьте health endpoints

### Тесты падают

1. Проверьте, что все сервисы здоровы
2. Проверьте логи сервисов
3. Проверьте отчеты в `tests/e2e/reports/`
4. Убедитесь, что node-sim запущен и публикует телеметрию

### Проблемы с подключением к БД

1. Проверьте переменные окружения в `.env.e2e`
2. Убедитесь, что PostgreSQL запущен: `docker compose -f tests/e2e/docker-compose.e2e.yml ps postgres`
3. Проверьте подключение: `docker compose -f tests/e2e/docker-compose.e2e.yml exec postgres pg_isready -U hydro`

## Дополнительная документация

- [E2E_GUIDE.md](../../docs/testing/E2E_GUIDE.md) - Подробное руководство по E2E тестам
- [NODE_SIM.md](../../docs/testing/NODE_SIM.md) - Документация по симулятору узлов
