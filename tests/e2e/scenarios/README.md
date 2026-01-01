# E2E Сценарии (P0) - Критичные инварианты пайплайна

Набор E2E сценариев для проверки критичных инвариантов пайплайна системы Hydro 2.0.

## Структура сценариев

Каждый сценарий описывается в YAML формате и содержит:

- **name**: Идентификатор сценария
- **description**: Описание того, что проверяется
- **setup**: Настройка окружения (симуляторы узлов, предварительные условия)
- **actions**: Последовательность действий для выполнения сценария
- **assertions**: Проверки результатов (БД, WebSocket, API)
- **cleanup**: Очистка после выполнения

## Сценарии (актуальная структура)

Сценарии организованы по категориям в `tests/e2e/scenarios/`:
- `core/` — базовые сценарии (bootstrap, auth)
- `commands/` — команды (happy/failed/timeout/duplicate)
- `alerts/` — алерты (error → alert, dedup, unassigned, DLQ)
- `snapshot/` — snapshot и replay
- `infrastructure/` — readiness и bindings
- `grow_cycle/` — циклы выращивания
- `automation_engine/` — автоматизация
- `chaos/` — хаос‑тесты

Полный список и DoD: `../../../docs/testing/E2E_SCENARIOS.md`.

Ключевые сценарии:
- `core/E01_bootstrap.yaml` — telemetry в БД + ONLINE статус
- `core/E02_auth_ws_api.yaml` — AuthClient + API + WS
- `commands/E10_command_happy.yaml` — команда → DONE + WS + zone_events
- `alerts/E20_error_to_alert_realtime.yaml` — error → alert + dedup
- `snapshot/E31_reconnect_replay_gap.yaml` — snapshot + replay

## Формат действий

### Типы действий

- `start_simulator`: Запуск симулятора узла
- `stop_simulator`: Остановка симулятора
- `publish_mqtt`: Публикация сообщения в MQTT
- `wait_for_mqtt`: Ожидание сообщения в MQTT топике
- `http_request`: HTTP запрос к API
- `websocket_connect`: Подключение к WebSocket
- `websocket_disconnect`: Отключение от WebSocket
- `wait`: Ожидание указанного времени
- `database_query`: Выполнение SQL запроса
- `service_control`: Управление сервисом (start/stop)

### Типы проверок (assertions)

- `database_query`: Проверка данных в БД
- `websocket_event`: Проверка WebSocket события
- `json_assertion`: Проверка JSON структуры
- `compare_json`: Сравнение JSON значений
- `http_request`: Проверка HTTP ответа

## Переменные окружения

Сценарии используют следующие переменные окружения:

- `MQTT_HOST`: Хост MQTT брокера (по умолчанию: localhost)
- `MQTT_PORT`: Порт MQTT брокера (по умолчанию: 1883)
- `MQTT_USER`: Пользователь MQTT (опционально)
- `MQTT_PASS`: Пароль MQTT (опционально)
- `LARAVEL_URL`: URL Laravel API (по умолчанию: http://localhost:8081)
- `WS_URL`: URL WebSocket сервера (по умолчанию: ws://localhost:6002)
- `API_TOKEN`: опционально (legacy), по умолчанию используется AuthClient

## Запуск сценариев

Сценарии должны выполняться через E2E runner (см. `tests/e2e/runner/`).

Пример:
```bash
python3 -m runner.e2e_runner scenarios/core/E01_bootstrap.yaml
```

## Требования

- Docker Compose с запущенными сервисами (Laravel, MQTT, PostgreSQL)
- Python зависимости для node_sim
- Доступ к БД для проверок
- WebSocket сервер (Laravel Reverb) запущен
