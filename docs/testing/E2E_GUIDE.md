# E2E Test Guide - Руководство по E2E тестам

Руководство по написанию и запуску end-to-end тестов для системы Hydro 2.0.

## Быстрый старт

### 1. Установка зависимостей

```bash
cd tests/e2e
pip install -r requirements.txt
```

### 2. Запуск тестового окружения

```bash
# Запуск всех сервисов
docker-compose -f docker-compose.e2e.yml up -d

# Проверка статуса
docker-compose -f docker-compose.e2e.yml ps

# Просмотр логов
docker-compose -f docker-compose.e2e.yml logs -f
```

### 3. Запуск теста

```bash
# Запуск одного сценария
python -m runner.e2e_runner scenarios/E01_bootstrap.yaml

# Запуск с подробным выводом
python -m runner.e2e_runner scenarios/E01_bootstrap.yaml --verbose
```

## E2E Auth Bootstrap

Для автоматического получения токена для E2E тестов доступны два способа:

### 1. Artisan команда (рекомендуется)

```bash
# В контейнере Laravel
docker-compose -f docker-compose.e2e.yml exec laravel php artisan e2e:auth-bootstrap

# Или с параметрами
docker-compose -f docker-compose.e2e.yml exec laravel php artisan e2e:auth-bootstrap --email=e2e@test.local --role=admin
```

Команда создаёт пользователя `e2e@test.local` (если его нет) и выводит токен в stdout.

### 2. API endpoint (только в testing окружении)

```bash
curl -X POST http://localhost:8081/api/e2e/auth/token \
  -H "Content-Type: application/json" \
  -d '{"email":"e2e@test.local","role":"admin"}'
```

Ответ:
```json
{
  "status": "ok",
  "data": {
    "token": "...",
    "user": {
      "id": 1,
      "email": "e2e@test.local",
      "role": "admin"
    }
  }
}
```

**Примечание:** Оба метода автоматически используются в `run_e2e.sh` при запуске тестов.

## Переменные окружения

### Обязательные переменные

```bash
# Laravel API
LARAVEL_URL=http://localhost:8081
LARAVEL_API_TOKEN=dev-token-12345  # Автоматически получается через e2e:auth-bootstrap

# База данных
DB_CONNECTION=pgsql
DB_HOST=localhost
DB_PORT=5433
DB_DATABASE=hydro_e2e
DB_USERNAME=hydro
DB_PASSWORD=hydro_e2e
```

### Опциональные переменные

```bash
# MQTT
MQTT_HOST=localhost
MQTT_PORT=1884
MQTT_USER=                    # Опционально
MQTT_PASS=                    # Опционально

# WebSocket
WS_URL=ws://localhost:6002
REVERB_APP_KEY=local
REVERB_APP_SECRET=secret

# Отчеты
E2E_REPORT_DIR=./reports
E2E_TIMEOUT=300
E2E_RETRIES=3
```

### Пример .env файла

Создайте файл `.env` в директории `tests/e2e/`:

```bash
# .env
LARAVEL_URL=http://localhost:8081
LARAVEL_API_TOKEN=dev-token-12345
MQTT_HOST=localhost
MQTT_PORT=1884
WS_URL=ws://localhost:6002
DB_HOST=localhost
DB_PORT=5433
DB_DATABASE=hydro_e2e
DB_USERNAME=hydro
DB_PASSWORD=hydro_e2e
```

## Структура YAML сценария

### Базовая структура

```yaml
name: E01_bootstrap
description: |
  Краткое описание того, что проверяет этот тест

setup:
  node_sim:
    config:
      # Конфигурация симулятора узла
      mqtt:
        host: ${MQTT_HOST:-localhost}
        port: ${MQTT_PORT:-1883}
      node:
        gh_uid: gh-test-1
        zone_uid: zn-test-1
        node_uid: nd-ph-test-1
        node_type: ph
        mode: configured
  
  prerequisites:
    - database: nodes table exists
    - mqtt: broker is accessible
    - backend: Laravel is running

actions:
  - step: start_node_simulator
    type: start_simulator
    config_ref: node_sim.config
    wait_seconds: 3

assertions:
  - name: telemetry_in_db
    type: database_query
    query: |
      SELECT value FROM telemetry_last
      WHERE zone_id = (SELECT id FROM zones WHERE uid = 'zn-test-1')
    expected:
      - field: value
        operator: equals
        value: 6.5

cleanup:
  - step: stop_node_simulator
    type: stop_simulator
```

## Типы действий (Actions)

### start_simulator / stop_simulator

Запуск и остановка симулятора узла:

```yaml
- step: start_node_simulator
  type: start_simulator
  config_ref: node_sim.config  # Ссылка на конфигурацию из setup
  wait_seconds: 3              # Ожидание после запуска
```

### api_post / api_get / api_patch / api_delete

HTTP запросы к Laravel API:

```yaml
- step: send_command
  type: api_post
  endpoint: "/api/zones/{zone_id}/commands"
  payload:
    type: "pump_control"
    params:
      channel: "main_pump"
      action: "start"
  headers:                      # Опционально
    Authorization: "Bearer ${API_TOKEN}"
  wait_seconds: 2
  capture: command_response     # Сохранить ответ в переменную
```

### mqtt_publish

Публикация сообщения в MQTT:

```yaml
- step: publish_telemetry
  type: mqtt_publish
  topic: "hydro/gh-test-1/zn-test-1/nd-ph-test-1/ph_sensor/telemetry"
  payload:
    value: 6.5
    ts: ${TIMESTAMP_MS}
  qos: 1
  retain: false                 # Опционально
  wait_seconds: 2
```

### websocket_connect / websocket_disconnect

Подключение к WebSocket:

```yaml
- step: connect_websocket
  type: websocket_connect
  url: "${WS_URL:-ws://localhost:6001}"
  channel: "hydro.zones.{zone_id}"
  capture_connection: ws_connection  # Имя переменной для подключения
  wait_seconds: 2
```

### websocket_subscribe

Подписка на канал:

```yaml
- step: subscribe_ws
  type: websocket_subscribe
  channel: "private-commands.{zone_id}"
  connection: ws_connection    # Использовать существующее подключение
  wait_seconds: 1
```

### websocket_wait_event

Ожидание WebSocket события:

```yaml
- step: wait_for_event
  type: websocket_wait_event
  connection: ws_connection
  channel: "private-commands.{zone_id}"
  event_type: ".App\\Events\\CommandStatusUpdated"
  timeout: 10.0
  filter:                       # Опционально
    command.status: "DONE"
  capture: event_data           # Сохранить событие
```

### database_query

Выполнение SQL запроса:

```yaml
- step: check_command_status
  type: database_query
  query: |
    SELECT status FROM commands
    WHERE cmd_id = '${COMMAND_ID}'
  params:                       # Опционально
    cmd_id: ${COMMAND_ID}
  wait_seconds: 1
  capture: command_status
```

### wait

Ожидание указанного времени:

```yaml
- step: wait_processing
  type: wait
  seconds: 5
```

## Типы проверок (Assertions)

### database_query

Проверка данных в базе данных:

```yaml
- name: command_status_done
  type: database_query
  query: |
    SELECT status, result_code FROM commands
    WHERE cmd_id = '${COMMAND_ID}'
  expected:
    - field: status
      operator: equals
      value: "DONE"
    - field: result_code
      operator: equals
      value: 0
```

Поддерживаемые операторы:
- `equals` - равенство
- `not_equals` - неравенство
- `greater_than` - больше
- `less_than` - меньше
- `greater_than_or_equal` - больше или равно
- `less_than_or_equal` - меньше или равно
- `is_null` - значение NULL
- `is_not_null` - значение не NULL
- `contains` - содержит подстроку
- `in` - входит в список

### websocket_event

Проверка WebSocket события:

```yaml
- name: ws_command_status_updated
  type: websocket_event
  channel: "private-commands.{zone_id}"
  event_type: ".App\\Events\\CommandStatusUpdated"
  timeout: 10.0
  expected:
    - field: command.status
      operator: equals
      value: "DONE"
    - field: command.result_code
      operator: equals
      value: 0
```

### websocket_event_count

Проверка количества событий:

```yaml
- name: ws_events_count
  type: websocket_event_count
  channel: "private-commands.{zone_id}"
  event_type: ".App\\Events\\CommandStatusUpdated"
  timeout: 10.0
  filter:
    command.status: "DONE"
  expected:
    - field: count
      operator: equals
      value: 1
```

### json_assertion

Проверка JSON структуры:

```yaml
- name: snapshot_contains_data
  type: json_assertion
  source: snapshot_response
  path: data
  expected:
    - field: snapshot_id
      operator: is_not_null
    - field: last_event_id
      operator: greater_than
      value: 0
```

### compare_json

Сравнение двух JSON значений:

```yaml
- name: snapshot_updated
  type: compare_json
  source1: initial_snapshot
  source2: snapshot_after_reconnect
  path1: data.last_event_id
  path2: data.last_event_id
  operator: less_than  # snapshot_after > initial
```

## Переменные и подстановка

### Использование переменных

В YAML сценариях можно использовать переменные в формате `${VAR}`:

```yaml
topic: "hydro/${GH_UID}/${ZONE_UID}/${NODE_UID}/telemetry"
```

### Переменные окружения

Автоматически доступны все переменные окружения:

```yaml
endpoint: "${LARAVEL_URL}/api/zones/{zone_id}"
```

### Переменные из capture

Результаты действий сохраняются в переменные через `capture`:

```yaml
- step: send_command
  type: api_post
  endpoint: "/api/zones/{zone_id}/commands"
  capture: command_response

- step: use_command_id
  type: api_get
  endpoint: "/api/commands/${command_response.data.id}"
```

### Встроенные переменные

- `${TIMESTAMP_MS}` - текущая временная метка в миллисекундах
- `${TIMESTAMP_S}` - текущая временная метка в секундах

## Доступные E2E сценарии

### E01_bootstrap.yaml

**DoD**: telemetry в БД + online статус

Проверяет базовый bootstrap пайплайна:
- Публикация телеметрии через MQTT
- Сохранение телеметрии в БД
- Обновление статуса узла на ONLINE

### E02_command_happy.yaml

**DoD**: команда → DONE + WS событие + zone_events запись

Проверяет успешное выполнение команды:
- Отправка команды через API
- Обработка командой узла
- WebSocket события
- Запись в zone_events

### E03_duplicate_cmd_response.yaml

**DoD**: duplicate responses не ломают статус

Проверяет устойчивость к дубликатам ответов.

### E04_error_alert.yaml

**DoD**: error → alert ACTIVE + WS + dedup

Проверяет создание алертов из ошибок узлов.

### E05_unassigned_attach.yaml

**DoD**: temp error → unassigned → attach → alert

Проверяет сценарий присвоения непривязанного узла.

### E06_laravel_down_queue_recovery.yaml

**DoD**: laravel down → pending_alerts растёт → восстановление → доставка

Проверяет восстановление после падения Laravel.

### E07_ws_reconnect_snapshot_replay.yaml

**DoD**: snapshot last_event_id + replay закрывают gap

Проверяет механизм восстановления после разрыва WebSocket.

## Запуск тестов

### Запуск одного теста

```bash
cd tests/e2e
python -m runner.e2e_runner scenarios/E01_bootstrap.yaml
```

### Запуск всех тестов

```bash
cd tests/e2e
for scenario in scenarios/E*.yaml; do
    python -m runner.e2e_runner "$scenario"
done
```

### Запуск с параметрами

```bash
# Подробный вывод
python -m runner.e2e_runner scenarios/E01_bootstrap.yaml --verbose

# Сохранить отчет в другую директорию
E2E_REPORT_DIR=./my_reports python -m runner.e2e_runner scenarios/E01_bootstrap.yaml

# Увеличить таймаут
E2E_TIMEOUT=600 python -m runner.e2e_runner scenarios/E01_bootstrap.yaml
```

## Отчеты

### JUnit XML

После выполнения теста генерируется отчет в формате JUnit XML:

```bash
tests/e2e/reports/junit.xml
```

Можно использовать в CI/CD системах для визуализации результатов.

### JSON Timeline

Детальная информация о выполнении теста:

```bash
tests/e2e/reports/timeline.json
```

Содержит:
- Все WebSocket сообщения (последние 50)
- Все MQTT сообщения (последние 50)
- Все API запросы и ответы
- Временные метки всех событий
- Результаты проверок

### Пример чтения отчета

```python
import json

with open('tests/e2e/reports/timeline.json') as f:
    timeline = json.load(f)

# Просмотр WebSocket событий
for event in timeline['websocket_events']:
    print(f"{event['timestamp']}: {event['event_type']}")

# Просмотр MQTT сообщений
for msg in timeline['mqtt_messages']:
    print(f"{msg['timestamp']}: {msg['topic']} = {msg['payload']}")
```

## Отладка тестов

### Включение детального логирования

```bash
export LOG_LEVEL=DEBUG
python -m runner.e2e_runner scenarios/E01_bootstrap.yaml --verbose
```

### Проверка состояния сервисов

```bash
# Статус всех сервисов
docker-compose -f docker-compose.e2e.yml ps

# Логи Laravel
docker-compose -f docker-compose.e2e.yml logs laravel

# Логи MQTT брокера
docker-compose -f docker-compose.e2e.yml logs mosquitto

# Логи history-logger
docker-compose -f docker-compose.e2e.yml logs history-logger
```

### Проверка базы данных

```bash
# Подключение к БД
docker-compose -f docker-compose.e2e.yml exec postgres psql -U hydro -d hydro_e2e

# Проверка таблиц
\dt

# Проверка команд
SELECT * FROM commands ORDER BY created_at DESC LIMIT 10;
```

### Проверка MQTT

```bash
# Подписка на все топики
docker-compose -f docker-compose.e2e.yml exec mosquitto mosquitto_sub -h localhost -t "#" -v
```

## Написание новых тестов

### Шаблон нового теста

```yaml
name: EXX_test_name
description: |
  Описание того, что проверяет этот тест

setup:
  node_sim:
    config:
      mqtt:
        host: ${MQTT_HOST:-localhost}
        port: ${MQTT_PORT:-1883}
      node:
        gh_uid: gh-test-1
        zone_uid: zn-test-1
        node_uid: nd-test-1
        node_type: ph
        mode: configured
  
  prerequisites:
    - database: nodes table exists
    - mqtt: broker is accessible

actions:
  # Шаги теста
  
assertions:
  # Проверки результатов

cleanup:
  - step: stop_node_simulator
    type: stop_simulator
```

### Best Practices

1. **Используйте осмысленные имена шагов** - это упростит отладку
2. **Добавляйте wait_seconds** после действий, требующих обработки
3. **Проверяйте cleanup** - всегда останавливайте симуляторы
4. **Используйте переменные** для повторяющихся значений
5. **Добавляйте описания** к сложным проверкам
6. **Тестируйте одну вещь** - каждый тест должен проверять один сценарий

## Интеграция с CI/CD

### GitHub Actions пример

```yaml
- name: Run E2E tests
  run: |
    cd tests/e2e
    docker-compose -f docker-compose.e2e.yml up -d
    sleep 60  # Ожидание запуска сервисов
    python -m runner.e2e_runner scenarios/E01_bootstrap.yaml
  env:
    LARAVEL_URL: http://localhost:8081
    MQTT_HOST: localhost
    MQTT_PORT: 1884
```

## Типовые проблемы

См. [TROUBLESHOOTING.md](./TROUBLESHOOTING.md#e2e-tests) для решения типовых проблем.

## Дополнительные ресурсы

- [TESTING_OVERVIEW.md](./TESTING_OVERVIEW.md) - Общий обзор тестирования
- [NODE_SIM.md](./NODE_SIM.md) - Документация по симулятору узлов
- [TROUBLESHOOTING.md](./TROUBLESHOOTING.md) - Решение типовых проблем


