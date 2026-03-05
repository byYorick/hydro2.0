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
- `simulation/` — симуляции (live, digital twin)
- `chaos/` — хаос‑тесты
- `workflow/` — сценарии пошаговых workflow (clean/solution/recirculation/ready)

Полный список и DoD: `../../../docs/testing/E2E_SCENARIOS.md`.

Ключевые сценарии:
- `core/E01_bootstrap.yaml` — telemetry в БД + ONLINE статус
- `core/E02_auth_ws_api.yaml` — AuthClient + API + WS
- `commands/E10_command_happy.yaml` — команда → DONE + WS + zone_events
- `alerts/E20_error_to_alert_realtime.yaml` — error → alert + dedup
- `snapshot/E31_reconnect_replay_gap.yaml` — snapshot + replay
- `automation_engine/E61_fail_closed_corrections.yaml` — fail-closed логика коррекций
- `automation_engine/E64_effective_targets_only.yaml` — runtime только на effective targets
- `automation_engine/E65_phase_transition_api.yaml` — переходы фаз через API
- `automation_engine/E66_full_prod_path_zone_recipe_bind_and_run.yaml` — полный продовый путь (zone/plant/recipe/bind/start)
- `automation_engine/E68_full_prod_path_strict_ec_ph_corrections.yaml` — полный путь + строгие EC/pH коррекции на real node
- `automation_engine/E74_node_zone_mismatch_guard.yaml` — guard node/zone mismatch
- `workflow/E94_startup_to_ready_smoke.yaml` — startup -> READY smoke + проверки BUSY/TIMEOUT/alert lifecycle

## AE2-Lite совместимость

По состоянию на 2026-02-22 каноничный runtime AE2-Lite поддерживает только
`ae_test_hook action=publish_command` (через `history-logger /commands`).

AE2-Lite compatible automation-сценарии:
- `automation_engine/E61_fail_closed_corrections.yaml`
- `automation_engine/E64_effective_targets_only.yaml`
- `automation_engine/E65_phase_transition_api.yaml`
- `automation_engine/E66_full_prod_path_zone_recipe_bind_and_run.yaml`
- `automation_engine/E68_full_prod_path_strict_ec_ph_corrections.yaml`
- `automation_engine/E74_node_zone_mismatch_guard.yaml`

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
