# E2E Сценарии - Полная документация

## Структура сценариев

Все E2E сценарии организованы по категориям в директории `tests/e2e/scenarios/`:

- `core/` - базовые сценарии (bootstrap, auth)
- `commands/` - тесты команд (happy path, failed, timeout, duplicate)
- `alerts/` - тесты алертов (error → alert, dedup, unassigned, DLQ)
- `snapshot/` - тесты snapshot и replay
- `infrastructure/` - readiness и bindings
- `grow_cycle/` - циклы выращивания
- `automation_engine/` - автоматизация управления
- `simulation/` - симуляции (live, digital twin)
- `chaos/` - хаос-тесты (деградация и восстановление)

## CORE

### E01_bootstrap.yaml
**DoD:** telemetry в БД + online статус

Проверяет базовый bootstrap пайплайна:
- Узел публикует телеметрию через MQTT
- Телеметрия сохраняется в БД (telemetry_last)
- Статус узла обновляется на ONLINE
- last_seen_at обновляется

### E02_auth_ws_api.yaml
**DoD:** токен получен, защищённый API доступен, WS channel subscribe проходит

Проверяет работу авторизации:
- Получение токена через AuthClient
- Вызов защищённого API endpoint с токеном
- Подключение к WebSocket с токеном
- Подписка на приватный канал
- Автоматическое обновление токена при 401
- Защита приватных каналов без токена

## COMMANDS

### E10_command_happy.yaml
**DoD:** команда → DONE + WS событие + zone_events запись

Проверяет успешный путь выполнения команды:
- Отправка команды через API
- Узел получает команду и отвечает ACK
- Узел выполняет команду и отвечает DONE
- Статус команды обновляется в БД
- WebSocket событие CommandStatusUpdated отправляется
- Запись в zone_events создается

### E11_command_failed.yaml
**DoD:** node-sim отвечает FAILED, DB status=FAILED + WS

Проверяет обработку неуспешной команды:
- Команда отправляется узлу
- Узел отвечает FAILED
- Статус команды в БД = FAILED
- WebSocket событие отправляется

### E12_command_timeout.yaml
**DoD:** node-sim не отвечает, проверка TIMEOUT

Проверяет обработку команды с таймаутом:
- Команда отправляется узлу
- Узел не отвечает
- Система устанавливает статус TIMEOUT
- При необходимости создается alert или zone_event

### E13_command_duplicate_response.yaml
**DoD:** duplicate responses не ломают статус

Проверяет устойчивость к дублирующимся ответам:
- Команда отправляется
- Узел отправляет DONE ответ дважды
- Статус команды остается DONE (не нарушается)

### E14_command_response_before_sent.yaml
**DoD:** быстрый response, stub/UPSERT не ломает финал

Проверяет обработку быстрого ответа:
- Узел отвечает на команду до того, как она была помечена как SENT
- Система корректно обрабатывает такой ответ (stub/UPSERT)
- Финальный статус команды остается корректным

## ALERTS

### E20_error_to_alert_realtime.yaml
**DoD:** error → alert ACTIVE + WS + dedup

Проверяет создание алерта при ошибке:
- Узел публикует ошибку через MQTT
- Алерт создается в БД со статусом ACTIVE
- WebSocket событие AlertCreated отправляется
- Повторные одинаковые ошибки не создают дубликаты

### E21_alert_dedup_count.yaml
**DoD:** 100 одинаковых errors → 1 alert, count=100

Проверяет механизм дедупликации алертов:
- Узел публикует 100 одинаковых ошибок
- Создается один ACTIVE alert
- Alert имеет count=100

### E22_unassigned_error_capture.yaml
**DoD:** temp error → unassigned_node_errors

Проверяет захват ошибок от непривязанных узлов:
- Узел в режиме preconfig публикует ошибку
- Ошибка сохраняется в unassigned_node_errors
- Ошибка не создает alert (узел не привязан)

### E23_unassigned_attach_on_registry.yaml
**DoD:** registry attach → alert, unassigned архивирован

Проверяет сценарий присвоения не назначенного узла:
- Узел публикует ошибку без привязки
- Ошибка регистрируется в unassigned_node_errors
- Узел привязывается к зоне через API
- Алерт создается после привязки

### E24_laravel_down_pending_alerts.yaml
**DoD:** laravel down → pending_alerts растёт → восстановление → доставка

Проверяет механизм восстановления после падения Laravel:
- Laravel останавливается
- Ошибки узлов продолжают поступать
- pending_alerts растет
- Laravel восстанавливается
- Все накопленные ошибки обрабатываются

### E25_dlq_replay.yaml
**DoD:** DLQ item → replay → доставлено

Проверяет механизм replay из DLQ:
- Создается DLQ item (алерт, который не удалось доставить)
- Выполняется replay
- Alert доставляется успешно

## SNAPSHOT

### E30_snapshot_contains_last_event_id.yaml
**DoD:** snapshot возвращает last_event_id

Проверяет, что snapshot API возвращает last_event_id:
- Получаем snapshot зоны через API
- Проверяем наличие поля last_event_id
- Проверяем, что last_event_id соответствует max(id) в zone_events

### E31_reconnect_replay_gap.yaml
**DoD:** snapshot last_event_id + replay закрывают gap

Проверяет механизм восстановления после разрыва WebSocket:
- Клиент подключен к WebSocket
- Происходит разрыв соединения
- Создаются события во время разрыва (gap)
- Клиент переподключается
- Клиент получает snapshot с last_event_id
- Клиент запрашивает события после last_event_id
- Gap закрыт

### E32_out_of_order_guard.yaml
**DoD:** client-side reconciliation по event_id корректен

Проверяет защиту от out-of-order событий:
- Получаем snapshot с last_event_id
- Запрашиваем события с after_id
- Проверяем, что система не возвращает старые события
- Проверяем порядок событий

## INFRASTRUCTURE

### E40_zone_readiness_fail.yaml
**DoD:** зона без bindings → 422

Проверяет проверку готовности зоны:
- Создается зона без требуемых bindings
- Попытка запустить grow-cycle возвращает 422 с причинами

### E41_zone_readiness_warn_start_anyway.yaml
**DoD:** missing nodes → warning, но start работает

Проверяет работу start при отсутствии некоторых узлов:
- Зона имеет bindings, но некоторые узлы offline
- Запуск grow-cycle работает с warning

### E42_bindings_role_resolution.yaml
**DoD:** bindings → команда в правильный топик

Проверяет разрешение bindings:
- Назначаются bindings (role → node/channel)
- Команда отправляется по role
- Команда попадает в правильный MQTT топик

## GROW CYCLE

### E50_create_cycle_planned.yaml
**DoD:** create plant + recipe + stage-map → PLANNED

Проверяет создание grow-cycle:
- Создается plant + recipe + stage-map
- Grow-cycle создается со статусом PLANNED

### E51_start_cycle_running.yaml
**DoD:** start cycle → RUNNING, zone_recipe_instance

Проверяет запуск grow-cycle:
- Запускается цикл
- Создается zone_recipe_instance
- Статус = RUNNING
- Стадия ACTIVE

### E52_stage_progress_timeline.yaml
**DoD:** симуляция времени → переход фаз

Проверяет прогресс стадий:
- Симулируется время/переход фаз
- Проверяется stage timeline + проценты

### E53_manual_advance_stage.yaml
**DoD:** advance stage → zone_event + WS

Проверяет ручное продвижение стадии:
- Advance stage
- zone_event создается
- WebSocket событие отправляется

### E54_pause_resume_harvest.yaml
**DoD:** pause/resume/harvest → закрытие цикла

Проверяет управление циклом:
- Pause/resume
- Harvest → закрытие цикла
- API snapshot отражает изменения

## AUTOMATION ENGINE

### E60_climate_control_happy.yaml
**DoD:** telemetry → AE → команды fan/vent/heater

Проверяет автоматическое управление климатом:
- Дается telemetry (t/rh/co2)
- Targets из active stage
- AE формирует команду (fan/vent/heater)
- node-sim выполняет
- Команды DONE + WS

### E61_fail_closed_corrections.yaml
**DoD:** stale telemetry → AE НЕ дозирует

Проверяет fail-closed поведение:
- Stale telemetry ph/ec
- AE НЕ дозирует
- Создается событие/alert "skipped"

### E62_controller_fault_isolation.yaml
**DoD:** исключение в контроллере → остальные работают

Проверяет изоляцию ошибок:
- Принудительно вызывается исключение в одном контроллере
- Остальные контроллеры работают
- zone_event controller_failed

### E63_backoff_on_errors.yaml
**DoD:** серия ошибок → degraded mode

Проверяет механизм backoff:
- Серия ошибок → AE увеличивает интервал/переходит в degraded
- Подтверждение через метрики/лог/zone_events

## SIMULATION

### E90_live_simulation_stop_commands.yaml
**DoD:** live-симуляция завершается, stop-команды отправлены

Проверяет live-симуляцию:
- Создается zone_simulations запись и завершается
- Мета real_duration_minutes задана
- После завершения отправляются set_relay и set_pwm

## CHAOS

### E70_mqtt_down_recovery.yaml
**DoD:** MQTT down 60s → команды TIMEOUT → восстановление

Проверяет восстановление после падения MQTT:
- MQTT down 60s
- Команды уходят в TIMEOUT
- После восстановления всё работает

### E71_db_flaky.yaml
**DoD:** DB ограничения → queues/DLQ фиксируют

Проверяет работу при проблемах с БД:
- Ограничиваются коннекты/вызываются ошибки
- Система не падает, queues/DLQ фиксируют

### E72_ws_down_snapshot_recover.yaml
**DoD:** WS down → snapshot+replay догоняют

Проверяет восстановление после падения WS:
- WS down
- Snapshot+replay догоняют

## Запуск сценариев

### Быстрый набор (CORE)
```bash
./tools/testing/run_e2e_core.sh
```

### Полный набор (без CHAOS)
```bash
./tools/testing/run_e2e.sh
```

### Хаос-тесты
```bash
./tools/testing/run_e2e_chaos.sh
```

## Fault Injection

Некоторые сценарии используют fault injection для симуляции сбоев:

```yaml
- step: stop_service
  type: fault.inject
  service: laravel
  action: stop
  duration_s: 60  # Автоматическое восстановление через 60 секунд

- step: restore_service
  type: fault.restore
  service: laravel
```

Поддерживаемые сервисы: `laravel`, `mosquitto`, `postgres`, `history-logger`, `automation-engine`, `redis`, `reverb`.

Поддерживаемые действия: `stop`, `start`, `pause`, `unpause`.

