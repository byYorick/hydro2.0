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

## Сценарии

### E01_bootstrap.yaml
**DoD**: telemetry в БД + online статус

Проверяет базовый bootstrap пайплайна:
- Узел публикует телеметрию через MQTT
- Телеметрия сохраняется в БД (telemetry_last)
- Статус узла обновляется на ONLINE
- last_seen_at обновляется

### E02_command_happy.yaml
**DoD**: команда → DONE + WS событие + zone_events запись

Проверяет успешный путь выполнения команды:
- Отправка команды через API
- Узел получает команду и отвечает ACCEPTED
- Узел выполняет команду и отвечает DONE
- Статус команды обновляется в БД
- WebSocket событие CommandCompleted отправляется
- Запись в zone_events создается

### E03_duplicate_cmd_response.yaml
**DoD**: duplicate responses не ломают статус

Проверяет устойчивость к дубликатам ответов:
- Узел отправляет команду
- Узел отвечает ACCEPTED (возможен дубликат)
- Узел отвечает DONE (возможен дубликат)
- Статус команды остается корректным (DONE)
- Не создаются дубликаты событий

### E04_error_alert.yaml
**DoD**: error → alert ACTIVE + WS + dedup

Проверяет создание алерта из ошибки узла:
- Узел публикует ошибку через MQTT
- Создается алерт со статусом ACTIVE
- Алерт отправляется через WebSocket
- Повторные ошибки дедуплицируются (обновляется count)

### E05_unassigned_attach.yaml
**DoD**: temp error → unassigned → attach → alert

Проверяет сценарий с непривязанным узлом:
- Узел в режиме preconfig публикует ошибку (temp-топик)
- Ошибка сохраняется в unassigned_nodes_errors
- Узел привязывается к зоне
- Алерт создается для зоны после привязки

### E06_laravel_down_queue_recovery.yaml
**DoD**: laravel down → pending_alerts растёт → восстановление → доставка

Проверяет механизм восстановления после падения Laravel:
- Laravel останавливается
- Ошибки узлов продолжают поступать
- pending_alerts растет
- Laravel восстанавливается
- pending_alerts обрабатывается и алерты доставляются

### E07_ws_reconnect_snapshot_replay.yaml
**DoD**: snapshot last_event_id + replay закрывают gap

Проверяет механизм восстановления после разрыва WebSocket:
- Клиент подключен к WebSocket
- Происходит разрыв соединения
- Создаются события во время разрыва (gap)
- Клиент переподключается
- Клиент получает snapshot с last_event_id
- Клиент запрашивает события после last_event_id (catch-up)
- Gap закрыт, все события получены

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
- `LARAVEL_URL`: URL Laravel API (по умолчанию: http://localhost:8080)
- `WS_URL`: URL WebSocket сервера (по умолчанию: ws://localhost:6001)
- `API_TOKEN`: Токен для аутентификации API

## Запуск сценариев

Сценарии должны выполняться через E2E runner (см. `tests/e2e/runner/`).

Пример:
```bash
python -m tests.e2e.runner run E01_bootstrap.yaml
```

## Требования

- Docker Compose с запущенными сервисами (Laravel, MQTT, PostgreSQL)
- Python зависимости для node_sim
- Доступ к БД для проверок
- WebSocket сервер (Laravel Reverb) запущен

