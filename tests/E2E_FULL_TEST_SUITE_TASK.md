Полный набор E2E тестов для полного тестирования системы (Node Emulator + API + DB + WS)
1) Цель задачи

Создать полный, воспроизводимый E2E тестовый набор, который проверяет систему целиком:

Node Emulator (node-sim) ↔ MQTT ↔ history-logger/mqtt-bridge ↔ Laravel ↔ Reverb/Echo ↔ Web (и контракт под Android)

корректность данных/команд/ошибок

устойчивость и восстановление после сбоев

grow-cycle (стадии, маппинг фаз), инфраструктура, readiness

automation-engine (управление климатом/поливом/коррекциями) в режиме e2e

2) Definition of Done (строгий)

Задача выполнена только если:

Поднимается стенд одной командой:

docker compose -f tests/e2e/docker-compose.e2e.yml up -d


Запуск полного набора тестов одной командой:

./tools/testing/run_e2e.sh


Формируется отчёт:

tests/e2e/reports/junit.xml

tests/e2e/reports/timeline.json

Набор включает:

базовые сценарии (happy path)

негативные/edge-case сценарии

сценарии деградации (fault injection)

проверку snapshot+events replay (event_id-first)

Все сценарии в CI (кроме “chaos/heavy”) проходят стабильно (10 прогонов подряд).

3) Входные допущения

Авторизация в E2E решена отдельным модулем (auth_client.py) и не требует ручного логина.

Node-sim публикует telemetry/status/error и отвечает на команды ACCEPTED/DONE/FAILED с cmd_id.

API возвращает snapshot(last_event_id) и events endpoint /events?after_id=....

4) Что именно нужно создать в репозитории
4.1 Структура тестов

Создать/довести:

tests/e2e/
  docker-compose.e2e.yml
  README.md
  runner/
    e2e_runner.py
    auth_client.py
    api_client.py
    ws_client.py
    db_probe.py
    mqtt_probe.py
    assertions.py
    reporting.py
  scenarios/
    core/
    grow_cycle/
    infrastructure/
    commands/
    alerts/
    snapshot/
    automation_engine/
    chaos/
  reports/  (генерируется)
tools/testing/
  run_e2e.sh
  run_e2e_core.sh
  run_e2e_chaos.sh
docs/testing/
  E2E_GUIDE.md
  E2E_SCENARIOS.md

4.2 Общие утилиты и принципы

Все сценарии описаны YAML

Каждый шаг логируется в timeline

Каждый сценарий:

создаёт изолированную тестовую зону (unique ids),

не зависит от выполнения другого теста,

убирает за собой ресурсы (или работает на отдельной тестовой БД).

5) Матрица E2E тестов (полный набор)

Ниже — список сценариев, которые обязаны быть реализованы.

A) CORE (минимальный “живой контур”)

core/E01_bootstrap.yaml

health endpoints ok

node-sim online

telemetry в БД

WS видит событие online/telemetry

core/E02_auth_ws_api.yaml

токен получен

защищённый API доступен

WS channel subscribe проходит

B) COMMANDS (команды и статусы)

commands/E10_command_happy.yaml

отправить команду pump ON

проверить: SENT→ACCEPTED→DONE

WS событие

запись в zone_events

commands/E11_command_failed.yaml

node-sim отвечает FAILED

DB status=FAILED + WS

commands/E12_command_timeout.yaml

node-sim drop response

проверить TIMEOUT (системный механизм)

alert/zone_event при необходимости

commands/E13_command_duplicate_response.yaml

node-sim отправляет DONE дважды

проверить идемпотентность (статус не “ломается”)

commands/E14_command_response_before_sent.yaml

симулировать “быстрый response”

убедиться: stub/UPSERT не ломает финал

C) ALERTS / ERRORS (ошибки, алерты, дедуп, DLQ)

alerts/E20_error_to_alert_realtime.yaml

publish error

создать ACTIVE alert

WS AlertCreated

zone_events запись

alerts/E21_alert_dedup_count.yaml

100 одинаковых errors за минуту

один ACTIVE alert, count=100

alerts/E22_unassigned_error_capture.yaml

temp error (preconfig)

запись в unassigned_node_errors

alerts/E23_unassigned_attach_on_registry.yaml

registry attach

создать alert

unassigned архивирован/очищен

zone_event unassigned_attached

alerts/E24_laravel_down_pending_alerts.yaml

остановить laravel (fault inject)

error → pending_alerts растёт

поднять laravel → доставка → alert появляется

если max_attempts → DLQ

alerts/E25_dlq_replay.yaml

создать DLQ item

replay → доставлено

D) SNAPSHOT + EVENTS REPLAY (reconnect discipline)

snapshot/E30_snapshot_contains_last_event_id.yaml

snapshot возвращает last_event_id

last_event_id соответствует zone_events max(id)

snapshot/E31_reconnect_replay_gap.yaml

disconnect WS client

создать события

reconnect:

snapshot(last_event_id)

events(after_id)

состояние догнано

snapshot/E32_out_of_order_guard.yaml

проверить, что client-side reconciliation по event_id корректен (не принимает старое)

E) INFRASTRUCTURE + BINDINGS + READINESS

infrastructure/E40_zone_readiness_fail.yaml

создать зону без required bindings

попытка start grow-cycle → 422 + причины

infrastructure/E41_zone_readiness_warn_start_anyway.yaml

missing online nodes → warning

start anyway работает

infrastructure/E42_bindings_role_resolution.yaml

назначить bindings (role→node/channel)

команда адресуется правильному топику

F) GROW CYCLE (стадии отдельно + маппинг фаз)

grow_cycle/E50_create_cycle_planned.yaml

создать plant + recipe + stage-map

create grow-cycle status=PLANNED

grow_cycle/E51_start_cycle_running.yaml

start cycle

создаётся zone_recipe_instance

status=RUNNING

stage ACTIVE

grow_cycle/E52_stage_progress_timeline.yaml

симулировать время/переход фаз

проверить stage timeline + проценты

grow_cycle/E53_manual_advance_stage.yaml

advance stage

zone_event + WS

grow_cycle/E54_pause_resume_harvest.yaml

pause/resume

harvest → закрытие цикла

API snapshot отражает изменения

G) AUTOMATION ENGINE (e2e управления)

automation_engine/E60_climate_control_happy.yaml

дать telemetry (t/rh/co2)

targets из active stage

AE формирует команду (fan/vent/heater)

node-sim выполняет

commands DONE + WS

automation_engine/E61_fail_closed_corrections.yaml

stale telemetry ph/ec

AE НЕ дозирует

создаёт событие/alert “skipped”

automation_engine/E62_controller_fault_isolation.yaml

принудительно вызвать исключение в одном контроллере (через config)

остальные контроллеры работают

zone_event controller_failed

automation_engine/E63_backoff_on_errors.yaml

серия ошибок → AE увеличивает интервал/переходит в degraded

подтверждение через метрики/лог/zone_events

H) CHAOS / DEGRADATION (тяжёлые, можно nightly)

chaos/E70_mqtt_down_recovery.yaml

MQTT down 60s

команды уходят в TIMEOUT

после восстановления всё работает

chaos/E71_db_flaky.yaml

ограничить коннекты/вызвать ошибки

system не падает, queues/DLQ фиксируют

chaos/E72_ws_down_snapshot_recover.yaml

WS down

snapshot+replay догоняют

6) Реализация fault-injection (обязательная часть)

В docker-compose.e2e.yml:

профили или команды:

stop/start laravel

stop/start mosquitto

pause/unpause postgres
Runner должен уметь шаг:

fault.inject(service, action, duration_s)

7) Требования к качеству тестов

Каждая проверка должна быть явной:

что ждём

где подтверждаем (DB/WS/MQTT)

таймауты управляемые через tests/e2e/timeouts.yaml

Каждая ошибка должна оставлять артефакты:

последние 50 WS событий

последние 50 MQTT сообщений

SQL snapshot ключевых таблиц (commands, alerts, zone_events, unassigned_node_errors)

Сценарии должны быть изолированы:

уникальные gh_uid/zone_uid/node_uid

без зависимости от порядка

8) Итоговые deliverables

ИИ-агент должен:

создать полный набор сценариев (A–H)

реализовать runner + отчёты

реализовать fault injection

обеспечить стабильность (10/10) core suite:

CORE + COMMANDS + ALERTS + SNAPSHOT + INFRA + GROW_CYCLE (без CHAOS)

CHAOS suite запускать отдельным скриптом nightly

9) Команды запуска (финальный UX)

Быстрый набор:

./tools/testing/run_e2e_core.sh


Полный набор:

./tools/testing/run_e2e.sh


Хаос:

./tools/testing/run_e2e_chaos.sh

10) Запреты

Нельзя хардкодить токены в сценариях

Нельзя отключать проверки ради “зелёного”

Нельзя подменять сервисы моками (кроме node-sim)

Нельзя делать тесты, которые требуют ручных шагов