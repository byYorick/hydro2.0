# SCHEDULER_AUTOMATION_REFACTOR_PLAN.md

Дата: 2026-02-10

Compatible-With: Protocol 2.0, Backend >=3.0, Python >=3.0, Database >=3.0, Frontend >=3.0.

## 1. Цель

Перевести `scheduler` в роль чистого планировщика:
- только построение расписаний;
- отправка абстрактных задач в `automation-engine`;
- ожидание статусов `accepted/completed|failed|rejected|expired`.

Исполнение команд на узлы, safety-проверки, контроль параметров и коррекции должны выполняться только в `automation-engine`.

Детальный план исполнения для ИИ-агента: `doc_ai/04_BACKEND_CORE/SCHEDULER_AUTOMATION_AI_AGENT_ROADMAP_PLAN.md`.
Правило рефакторинга: обратная совместимость с legacy/deprecated контрактами не требуется; legacy endpoint-ы, alias-форматы и fallback-ветки удаляются при переходе на целевой контракт.

## 2. Результат аудита (факт на дату)

### 2.1 Что было в scheduler

- Формировал расписания из `effective-targets`.
- Отправлял device-level команды (`run_pump`, `light_on/off`) через `automation-engine /scheduler/command`.
- Делал safety-логику и инфраструктурный контроль (уровень воды, dry-run мониторинг, water-change orchestration).

### 2.2 Что было в automation-engine

- Имел endpoint `POST /scheduler/command` для device-level команд.
- Централизованно отправлял команды через `CommandBus` -> `history-logger`.
- Основная автоматизация параметров уже была внутри `ZoneAutomationService`.

### 2.3 Разрыв ответственности

- Scheduler выполнял часть автоматизации и safety, что конфликтует с целевой архитектурой.
- Не было task-level контракта `scheduler -> automation-engine` с жизненным циклом `accepted/completed`.

## 3. Выполненные изменения

### 3.1 Scheduler (planner-only)

- Удалено прямое управление устройствами и safety/аварийная логика.
- Добавлена отправка абстрактных задач через `POST /scheduler/task`.
- Добавлено ожидание статуса задачи через `GET /scheduler/task/{task_id}`.
- Поддержаны типы задач: `irrigation`, `lighting`, `ventilation`, `solution_change`, `mist`, `diagnostics`.
- Добавлены метрики task-статусов и диагностика ошибок task API.
- Добавлен опциональный single-leader режим (`SCHEDULER_LEADER_ELECTION=1`) через `pg advisory lock`
  с безопасным переходом в follower-mode при потере лидерского DB-соединения.
- Добавлен startup recovery scanner в `scheduler`:
  - при рестарте восстанавливает `accepted` snapshot-ы из `scheduler_logs` в `_ACTIVE_TASKS`;
  - затем дофинализирует их через reconcile до terminal `completed|failed|timeout|not_found`.
- Усилен anti-silent контур scheduler:
  - `accepted` snapshot пишется отдельно (`running -> accepted -> terminal`);
  - добавлены alerts/diagnostics для `task status timeout/http/not_found` и internal enqueue ошибок
    (`invalid_zone`, `unsupported_task_type`, `expired_before_dispatch`, `dispatch_failed`).

### 3.2 Automation-engine

- Добавлен task-level API:
  - `POST /scheduler/task`
  - `GET /scheduler/task/{task_id}`
- Введен mandatory deadline-contract:
  - `due_at` и `expires_at` обязательны для `POST /scheduler/task`;
  - добавлен fail-fast до запуска executor с terminal статусами `rejected|expired`.
- Добавлен исполнитель `scheduler_task_executor.py`:
  - маппинг абстрактных задач на исполнение через `CommandBus`;
  - fail-closed diagnostics: при недоступном `ZoneAutomationService` задача завершается `failed` с `diagnostics_service_unavailable`.
- Добавлен конфигурационный слой маппинга `config/scheduler_task_mapping.py`
  с override из `payload.config.execution` (без hardcode в executor).
- Добавлена персистентность task-снимков (`accepted/running/completed/failed`)
  через `scheduler_logs` с восстановлением статуса после рестарта.
- Добавлена регистрация `ZoneAutomationService` в API из `main.py`.
- Добавлены service health endpoint-ы:
  - `/health/live` (liveness),
  - `/health/ready` (readiness: `CommandBus + DB + bootstrap lease-store`).
- Bootstrap/heartbeat синхронизированы с readiness-gate:
  - при деградации readiness `scheduler/bootstrap` и `bootstrap/heartbeat` возвращают `wait`,
    что удерживает scheduler в safe-mode без dispatch.
- Добавлен startup recovery scanner:
  - при рестарте `automation-engine` задачи с latest snapshot `accepted|running` финализируются
    в terminal `failed` с `error_code=task_recovered_after_restart`, чтобы исключить зависшие lifecycle.
- Унифицирован API-level failure outcome для scheduler-task:
  - во всех terminal `failed` ветках гарантируются `result.action_required/decision/reason_code/error_code`;
  - добавлены нормализованные fallback-коды `command_bus_unavailable`, `execution_exception`, `task_execution_failed`.
- Laravel `SchedulerTaskController` синхронизирован с контрактом:
  - прокидывает `due_at/expires_at` в task payload;
  - timeline умеет извлекать `decision/reason_code/error_code/action_required` из `result`, если root-поля отсутствуют.
- UI `ZoneAutomationTab` синхронизирован с контрактом:
  - добавлен SLA-блок (`scheduled/due/expires`) с индикацией окна дедлайнов;
  - обновлены label mappings для `expired`, execution events и унифицированных `reason_code/error_code`.

### 3.3 Тесты

Добавлены/обновлены тесты:
- `backend/services/scheduler/test_main.py`
- `backend/services/automation-engine/test_api.py`
- `backend/services/automation-engine/test_scheduler_task_executor.py`
- `backend/laravel/tests/Feature/SchedulerTaskControllerTest.php`
- `backend/laravel/resources/js/Pages/Zones/Tabs/__tests__/ZoneAutomationTab.spec.ts`
- `tests/e2e/scheduler/scheduler_leader_failover_chaos.sh`
- `tests/e2e/scheduler/scheduler_restart_recovery_chaos.sh`
- `tests/e2e/scheduler/automation_engine_restart_recovery_chaos.sh`

CI hardening:
- chaos suite подключен как отдельный stage `scheduler-chaos` в `/.github/workflows/ci.yml`;
- все chaos-скрипты выполняются в одном job без ранней остановки;
- docker-логи публикуются в artifacts `scheduler-chaos-logs`.
- стабильность в docker/dev подтверждена 5 последовательными прогонами полного chaos-suite (2026-02-10).

## 4. План дальнейшей переработки (следующий этап)

1. Добавить startup-handshake (`/scheduler/bootstrap`, `/scheduler/bootstrap/heartbeat`) и safe-mode scheduler до `ready` (сделано).
2. Сделать `correlation_id` обязательным и реализовать persistent dedupe/idempotency в `automation-engine` (сделано).
3. Добавить decision-layer outcome в task-result (`action_required`, `decision`, `reason_code`, `error_code`) (сделано, включая fallback для API-level ошибок).
4. Реализовать internal enqueue для self-task (`automation-engine` -> `scheduler`) для отложенных проверок (сделано).
5. Добавить детализированные события задачи для фронтенда (task timeline), обновить backend/UI отображение lifecycle и SLA (backend+Laravel API+ZoneAutomationTab UI + browser e2e для SLA/timeline сделано).
6. Довести R2 failover до production-уровня: добавить integration/e2e multi-instance проверки anti-double-dispatch (закрыто: добавлен container-level chaos сценарий `tests/e2e/scheduler/scheduler_leader_failover_chaos.sh`).
7. Зафиксировать closed-loop правило: успех execute-команды считается только при ответе ноды со статусом `DONE`; остальные статусы (`NO_EFFECT/BUSY/INVALID/ERROR/TIMEOUT/SEND_FAILED`) трактуются как неуспех (с алертами `COMMAND_EFFECT_NOT_CONFIRMED`) (сделано).

## 5. Матрица ответственности после рефакторинга

- `scheduler`: расписания + task dispatch + ожидание task статуса.
- `automation-engine`: принятие задачи, оркестрация исполнения, команды узлам, автоматизация параметров, safety/коррекции.
- `history-logger`: приём команд и доставка в MQTT pipeline.

## 6. Наблюдаемость и SLO (R8)

SLI-метрики:
- `task_accept_to_terminal_latency`
- `task_deadline_violation_rate`
- `task_recovery_success_rate`
- `command_effect_confirm_rate`
- `scheduler_dispatch_skips_total{reason}`

Alert rules:
- `TaskAcceptToTerminalLatencyP95High`
- `TaskDeadlineViolationRateHigh`
- `CommandEffectConfirmRateLow`
- `TaskRecoverySuccessRateLow`

Файлы:
- `backend/configs/dev/prometheus/alerts.yml`
- `backend/services/scheduler/main.py`
- `backend/services/automation-engine/api.py`

Валидация:
- `promtool check rules backend/configs/dev/prometheus/alerts.yml` (через docker run/compose).
